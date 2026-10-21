# Integration test: the rule of the missing values through the MCP server

import anyio
import numpy as np
import pandas as pd
from mcp import Client

from skforecast_ai.mcp import create_server

from ..fixtures_datasets import df_items_sales_wide
from .fixtures_mcp import (
    DATA_VALUES_HINT,
    content_of,
    df_h2o_csv,
    error_of,
    write_csv,
)

LEAVE = (
    "are data of the user: do not fill in, drop or write any of them "
    "yourself, in their file or in a copy of it, unless they asked for "
    "exactly that. Ask before you do."
)
RUN = (
    " `backtest` checks every test fold before running anything and names "
    "the dates that make it fail: run it before changing the plan or asking "
    "the user about the values."
)
NO_BACKTEST = (
    " If you forecast without a backtest, say in your answer that the "
    "forecast has no measure of error and why."
)
IN_TEST_FOLD = (
    "The target has 1 missing value(s) in test fold 5 of 6 (2007-10-01 "
    "00:00:00), counting the missing timestamps that asfreq() restores. "
    "skforecast cannot compute the metrics on them, whatever the estimator. "
    "Impute the target, or evaluate on dates without missing values."
)


def _monthly_data():
    """
    Return the last 120 months of h2o with the target missing at the
    positions 20 and 111 (counting from 0; 2007-10-01, inside the folds of
    the default strategy of 6 steps) and an exogenous column 'promo' missing
    at 30 and 115.
    """
    data = df_h2o_csv.iloc[-120:].reset_index(drop=True)
    data.loc[[20, 111], "x"] = np.nan
    data["promo"] = np.arange(120.0)
    data.loc[[30, 115], "promo"] = np.nan

    return data


def test_server_workflow_when_target_and_exog_have_missing_values(tmp_path):
    """
    Test the flow of the server on a target with a missing value inside a
    test fold and an exogenous column with missing values (V16 and V11 of
    the MCP audit):

    - `plan` advises only what works: the estimator of the rules
      (RandomForestRegressor, for 120 observations), filling the values in
      after asking the user, or leaving the column out; never
      `dropna_from_series`, which the plan already sets.
    - `create_cv` leaves the values to the user, says that `backtest`
      checks the folds before running, and offers that estimator without
      promising that it lets every fold run; the library warns about the
      target and the column apart.
    - `backtest` names the date and the fold, says that no estimator avoids
      it, and carries the hint that leaves the values to the user.
    - With the estimator the notice named, `create_cv` offers no other one
      and the column is no longer a problem, and `backtest` fails the same
      way: what the notice did not promise.
    """
    path = write_csv(tmp_path, "monthly.csv", _monthly_data())
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def flow():
        async with Client(server) as client:
            profile = content_of(
                await client.call_tool(
                    "profile",
                    {"data_path": path, "target": "x", "exog_columns": ["promo"]},
                )
            )
            plan = content_of(
                await client.call_tool(
                    "plan", {"profile_id": profile["id"], "steps": 6}
                )
            )
            cv = content_of(
                await client.call_tool("create_cv", {"plan_id": plan["id"]})
            )
            backtest = error_of(
                await client.call_tool("backtest", {"cv_id": cv["id"]}), "backtest"
            )
            refined = content_of(
                await client.call_tool(
                    "refine_plan",
                    {
                        "plan_id": plan["id"],
                        "overrides": {"estimator": "RandomForestRegressor"},
                    },
                )
            )
            cv_refined = content_of(
                await client.call_tool("create_cv", {"plan_id": refined["id"]})
            )
            backtest_refined = error_of(
                await client.call_tool("backtest", {"cv_id": cv_refined["id"]}),
                "backtest",
            )
            return plan, cv, backtest, cv_refined, backtest_refined

    plan, cv, backtest, cv_refined, backtest_refined = anyio.run(flow)

    advice = [
        line for line in plan["summary"].splitlines() if "[informational]" in line
    ]
    assert advice == [
        "  - [informational] The target has missing values: ForecasterRecursive "
        "with Ridge cannot predict from them, and `dropna_from_series` only "
        "drops the training rows that read one. An estimator that accepts "
        "missing values (such as 'RandomForestRegressor') predicts from them. A "
        "missing value on a date that a backtest or `test_size` scores fails "
        "with any estimator. Imputing the target, after asking the user, avoids "
        "these errors. The exogenous column 'promo' has missing values: "
        "ForecasterRecursive with Ridge cannot predict from them, and "
        "`dropna_from_series` only drops the training rows that have one. An "
        "estimator that accepts missing values (such as 'RandomForestRegressor') "
        "predicts from them; otherwise, fill them in the data, after asking the "
        "user, or leave it out of `exog_columns` when profiling."
    ]
    notices = {
        notice["category"]: [
            other["message"] for other in cv["notices"]
            if other["category"] == notice["category"]
        ]
        for notice in cv["notices"]
    }
    assert notices["MissingValuesNotice"] == [
        "The missing values of the target and the exogenous columns " + LEAVE
        + RUN + " Without touching the data, switching with `refine_plan` and "
        "a new `create_cv` to an estimator that accepts missing values (such "
        "as 'RandomForestRegressor') lets the plan predict from the missing "
        "exogenous values and, for the target, avoids the error of a fold "
        "predicted from a missing value, not of a fold that holds one: if you "
        "switch to it, say in your answer that you changed the estimator and "
        "why." + NO_BACKTEST
    ]
    assert [message[:44] for message in notices["UserWarning"]] == [
        "The target has missing values, and `backtest",
        "The exogenous column 'promo' has missing val",
    ]
    assert (backtest["code"], backtest["field"]) == ("invalid_argument", "data_path")
    assert backtest["message"] == IN_TEST_FOLD
    assert backtest["hint"] == DATA_VALUES_HINT

    assert [
        (notice["category"], notice["message"]) for notice in cv_refined["notices"]
    ] == [
        (
            "MissingValuesNotice",
            "The missing values of the target " + LEAVE + RUN + NO_BACKTEST,
        ),
        (
            "UserWarning",
            "The target has missing values, and `backtest()` checks every test "
            "fold before running: it raises, naming the dates, when a test fold "
            "holds one, whatever the estimator, since no metric is computed on "
            "it. Impute the target to backtest every fold.",
        ),
    ]
    assert backtest_refined["message"] == IN_TEST_FOLD
    assert backtest_refined["hint"] == DATA_VALUES_HINT


def test_server_backtest_when_missing_values_leave_no_training_row(tmp_path):
    """
    Test that a backtest whose first training window has no row that reads
    no missing value (the target missing at the positions 13 and 50 of 120
    months, and a rolling mean of 36) fails before running, with the
    remedies and the hint of the missing values, instead of the
    `execution_failed` of "All samples have been removed due to NaNs" (c_06
    of the MCP audit).
    """
    data = df_h2o_csv.iloc[-120:].reset_index(drop=True)
    data.loc[[13, 50], "x"] = np.nan
    path = write_csv(tmp_path, "monthly.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def flow():
        async with Client(server) as client:
            profile = content_of(
                await client.call_tool("profile", {"data_path": path, "target": "x"})
            )
            plan = content_of(
                await client.call_tool(
                    "plan", {"profile_id": profile["id"], "steps": 12}
                )
            )
            cv = content_of(
                await client.call_tool(
                    "create_cv",
                    {"plan_id": plan["id"], "initial_train_size": 84, "refit": False},
                )
            )
            return error_of(
                await client.call_tool("backtest", {"cv_id": cv["id"]}), "backtest"
            )

    backtest = anyio.run(flow)

    assert (backtest["code"], backtest["field"]) == ("invalid_argument", "data_path")
    assert backtest["message"] == (
        "Every training row of the backtest from 1998-07-01 to 2005-06-01 reads "
        "a missing value of the target (2 value(s), such as '1999-08-01', "
        "'2002-09-01'): ForecasterRecursive with Ridge drops the rows whose "
        "lags, window features or target read one (`dropna_from_series`), so "
        "skforecast would have no row to train on. An estimator that accepts "
        "missing values (such as 'RandomForestRegressor') trains on them; "
        "otherwise, use shorter lags and window features, which read fewer "
        "values, or fill in the missing values, after asking the user."
    )
    assert backtest["hint"] == DATA_VALUES_HINT


def test_server_backtest_when_missing_values_drop_a_series_from_every_fold(tmp_path):
    """
    Test that a series of items_sales whose last window before every fold
    has a missing value fails the backtest of a plan with Ridge before
    running, with the message of the missing values, the estimator of the
    rules for 360 observations (LGBMRegressor) and the hint that leaves the
    values to the user: skforecast left it out of every fold without a
    warning.
    """
    data = df_items_sales_wide.reset_index()
    data.loc[list(range(80, 117, 3)), "item_1"] = np.nan
    path = write_csv(tmp_path, "wide.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def flow():
        async with Client(server) as client:
            profile = content_of(
                await client.call_tool(
                    "profile",
                    {"data_path": path, "target": ["item_1", "item_2", "item_3"]},
                )
            )
            plan = content_of(
                await client.call_tool(
                    "plan",
                    {
                        "profile_id": profile["id"],
                        "steps": 3,
                        "estimator": "Ridge",
                        "lags": 5,
                        "window_features": [],
                    },
                )
            )
            cv = content_of(
                await client.call_tool(
                    "create_cv",
                    {"plan_id": plan["id"], "initial_train_size": 84, "refit": False},
                )
            )
            backtest = error_of(
                await client.call_tool("backtest", {"cv_id": cv["id"]}), "backtest"
            )
            return cv, backtest

    cv, backtest = anyio.run(flow)

    assert [notice["category"] for notice in cv["notices"]] == []
    assert (backtest["code"], backtest["field"]) == ("invalid_argument", "data_path")
    assert backtest["message"] == (
        "Some series cannot be forecast in any fold of the backtest: the 5 "
        "values before every fold they could be forecast in have a missing "
        "value ('item_1': 13 value(s), such as '2012-03-21', '2012-03-24', "
        "'2012-03-27', '2012-03-30', '2012-04-02' and 8 more), and "
        "ForecasterRecursiveMultiSeries with Ridge cannot predict from them. "
        "skforecast leaves them out of those folds without a warning, so they "
        "would get no predictions and no metrics, and the average across "
        "series would leave them out. An estimator that accepts missing values "
        "(such as 'LGBMRegressor') predicts from them; otherwise, fill them in "
        "the data, after asking the user, or remove those series."
    )
    assert backtest["hint"] == DATA_VALUES_HINT


def test_server_backtest_when_exogenous_values_are_missing_in_a_test_fold(tmp_path):
    """
    Test that a missing value of an exogenous column in a row that a test
    fold predicts (2006-11-01) fails the backtest of a plan with Ridge
    before running, naming the column and the date, with the hint that
    leaves the values to the user, instead of the `execution_failed` of
    "Input contains NaN"; `create_cv` says that `backtest` checks the folds
    of the exogenous columns too. The one in the training rows is not read.
    """
    data = df_h2o_csv.iloc[-120:].reset_index(drop=True)
    data["promo"] = np.arange(120.0)
    data.loc[[10, 100], "promo"] = np.nan
    path = write_csv(tmp_path, "monthly.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def flow():
        async with Client(server) as client:
            profile = content_of(
                await client.call_tool(
                    "profile",
                    {"data_path": path, "target": "x", "exog_columns": ["promo"]},
                )
            )
            plan = content_of(
                await client.call_tool(
                    "plan", {"profile_id": profile["id"], "steps": 12}
                )
            )
            cv = content_of(
                await client.call_tool(
                    "create_cv",
                    {"plan_id": plan["id"], "initial_train_size": 84, "refit": False},
                )
            )
            backtest = error_of(
                await client.call_tool("backtest", {"cv_id": cv["id"]}), "backtest"
            )
            return cv, backtest

    cv, backtest = anyio.run(flow)

    notices = {notice["category"]: notice["message"] for notice in cv["notices"]}
    assert RUN in notices["MissingValuesNotice"]
    assert "`backtest()` checks every test fold before running and raises" in (
        notices["UserWarning"]
    )
    assert (backtest["code"], backtest["field"]) == ("invalid_argument", "data_path")
    assert backtest["message"] == (
        "The forecaster reads missing values of the exogenous variables to "
        "predict 1 of the 3 test folds ('promo': 1 value(s), such as "
        "'2006-11-01'). ForecasterRecursive with Ridge cannot use them, so its "
        "predictions would be missing. Either they are filled in, after asking "
        "the user, or the plan uses an estimator that accepts missing values "
        "(such as 'RandomForestRegressor'), or the column is left out of "
        "`exog_columns` when profiling."
    )
    assert backtest["hint"] == DATA_VALUES_HINT


def test_server_forecast_when_missing_values_leave_no_training_row(tmp_path):
    """
    Test that a forecast whose training rows all read a missing value of
    the target (positions 13, 48, 83 and 93 of 120 months, and a rolling
    mean of 36) fails before running, in prediction mode and with
    `test_size`, with the remedies and the hint of the missing values,
    instead of the `execution_failed` of "All samples have been removed due
    to NaNs".
    """
    data = df_h2o_csv.iloc[-120:].reset_index(drop=True)
    data.loc[[13, 48, 83, 93], "x"] = np.nan
    path = write_csv(tmp_path, "monthly.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def flow():
        async with Client(server) as client:
            profile = content_of(
                await client.call_tool("profile", {"data_path": path, "target": "x"})
            )
            plan = content_of(
                await client.call_tool(
                    "plan", {"profile_id": profile["id"], "steps": 12}
                )
            )
            future = error_of(
                await client.call_tool("forecast", {"plan_id": plan["id"]}),
                "forecast",
            )
            holdout = error_of(
                await client.call_tool(
                    "forecast", {"plan_id": plan["id"], "test_size": 12}
                ),
                "forecast",
            )
            return future, holdout

    future, holdout = anyio.run(flow)

    for error, end in ((future, "2008-06-01"), (holdout, "2007-06-01")):
        assert (error["code"], error["field"]) == ("invalid_argument", "data_path")
        assert error["message"] == (
            f"Every training row of the forecast from 1998-07-01 to {end} reads "
            f"a missing value of the target (4 value(s), such as '1999-08-01', "
            f"'2002-07-01', '2005-06-01', '2006-04-01'): ForecasterRecursive "
            f"with Ridge drops the rows whose lags, window features or target "
            f"read one (`dropna_from_series`), so skforecast would have no row "
            f"to train on. An estimator that accepts missing values (such as "
            f"'RandomForestRegressor') trains on them; otherwise, use shorter "
            f"lags and window features, which read fewer values, or fill in "
            f"the missing values, after asking the user."
        )
        assert error["hint"] == DATA_VALUES_HINT


def test_server_backtest_when_multivariate_window_has_missing_value(tmp_path):
    """
    Test that a missing value of a series that is not the level of
    ForecasterDirectMultiVariate ('item_2', 2012-04-07), in the window of two
    test folds, fails the backtest with Ridge before running: skforecast
    never leaves a series out of that window, so the predictions of the
    level were missing and its metrics left them out without a warning.
    """
    data = df_items_sales_wide.reset_index()
    data.loc[97, "item_2"] = np.nan
    path = write_csv(tmp_path, "wide.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def flow():
        async with Client(server) as client:
            profile = content_of(
                await client.call_tool(
                    "profile",
                    {"data_path": path, "target": ["item_1", "item_2", "item_3"]},
                )
            )
            plan = content_of(
                await client.call_tool(
                    "plan",
                    {
                        "profile_id": profile["id"],
                        "steps": 3,
                        "forecaster": "ForecasterDirectMultiVariate",
                        "estimator": "Ridge",
                        "lags": 5,
                        "window_features": [],
                    },
                )
            )
            cv = content_of(
                await client.call_tool(
                    "create_cv",
                    {"plan_id": plan["id"], "initial_train_size": 84, "refit": False},
                )
            )
            return error_of(
                await client.call_tool("backtest", {"cv_id": cv["id"]}), "backtest"
            )

    backtest = anyio.run(flow)

    assert (backtest["code"], backtest["field"]) == ("invalid_argument", "data_path")
    assert backtest["message"] == (
        "The forecaster reads missing values of the target to predict 2 of the "
        "12 test folds ('item_2': 1 value(s), such as '2012-04-07'). "
        "ForecasterDirectMultiVariate with Ridge cannot use them, so its "
        "predictions would be missing. Either they are filled in, or the plan "
        "uses an estimator that accepts missing values (such as "
        "'RandomForestRegressor')."
    )
    assert backtest["hint"] == DATA_VALUES_HINT


def test_server_create_cv_names_closed_days_of_the_profile(tmp_path):
    """
    Test that `create_cv` on daily data of a shop closed on Sundays names
    the Sundays in the advice of the closed days, from the profile
    (`closed_weekdays`), instead of a condition on the missing dates.
    """
    dates = pd.date_range("2023-01-02", periods=140, freq="D")
    data = pd.DataFrame({"date": dates, "y": 10 + np.sin(np.arange(140))})
    data = data.loc[data["date"].dt.dayofweek != 6]
    path = write_csv(tmp_path, "shop.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def flow():
        async with Client(server) as client:
            profile = content_of(
                await client.call_tool("profile", {"data_path": path, "target": "y"})
            )
            plan = content_of(
                await client.call_tool(
                    "plan",
                    {"profile_id": profile["id"], "steps": 7, "estimator": "Ridge"},
                )
            )
            return content_of(
                await client.call_tool("create_cv", {"plan_id": plan["id"]})
            )

    cv = anyio.run(flow)

    warning = [
        notice["message"] for notice in cv["notices"]
        if notice["category"] == "UserWarning"
    ]
    assert len(warning) == 1
    assert warning[0].endswith(
        "If the business is closed on Sundays, fill them with 0 in the data, "
        "after asking the user, or impute the target to backtest every fold."
    )
