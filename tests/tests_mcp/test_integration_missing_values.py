# Integration test: the rule of the missing values through the MCP server

import anyio
import numpy as np
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
        "exogenous values and, for the target, avoids the error of a test fold "
        "predicted from a missing value, not that of a test fold that holds "
        "one: if you switch to it, say in your answer that you changed the "
        "estimator and why." + NO_BACKTEST
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
            "The target has missing values, and `backtest()` of this plan "
            "checks every test fold before running: it raises, naming the "
            "dates, when a test fold holds one, since the metrics cannot be "
            "computed on it whatever the estimator. Impute the target to "
            "backtest every fold.",
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
