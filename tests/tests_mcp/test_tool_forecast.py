# Unit test tool forecast

import pandas as pd
import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai._utils import load_exog
from skforecast_ai.mcp import create_server

from ..fixtures_assistant import df_crossing_zero, df_single
from ..fixtures_csv_dialect import df_dialect, write_dialect
from ..fixtures_datasets import df_items_sales_long
from .fixtures_mcp import (
    DATA_VALUES_HINT,
    call,
    df_numeric_ids_exog,
    df_numeric_ids_future_exog,
    df_single_future_exog,
    content_of,
    csv_of,
    error_of,
    h2o_server,
    profile_and_plan,
    run_session,
    text_of,
    write_csv,
)


@pytest.mark.parametrize(
    "test_size", [None, 12, 0.059, "2007-07-01"], ids=lambda dt: f"test_size: {dt!r}"
)
def test_tool_forecast_output_matches_python_api(tmp_path, test_size):
    """
    Test that `forecast` runs the plan as the Python API does, in prediction
    mode and in evaluation mode (a count, a fraction or a date): same
    summary, predictions and metrics (written to CSV files), and script.
    """
    server, path = h2o_server(tmp_path)
    profile_id, plan_id = profile_and_plan(server, path)

    result = content_of(
        call(server, "forecast", {"plan_id": plan_id, "test_size": test_size})
    )
    code = content_of(call(server, "get_code", {"object_id": result["id"]}))["code"]

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="x")
    expected = assistant.forecast(
        data=path,
        profile=profile,
        plan=assistant.plan(profile=profile, steps=12),
        test_size=test_size,
    )

    assert result["kind"] == "forecast"
    assert result["links"] == {"profile_id": profile_id, "plan_id": plan_id}
    assert result["summary"] == expected.describe()
    assert text_of(result["files"]["predictions"]) == csv_of(expected.predictions)
    # Only an evaluation has metrics, and with them the notice that gives
    # the reference of MASE and the unit of MAPE, after the one that says it
    # is an evaluation. A forecast of the future of a plan the session never
    # measured says so.
    categories = [notice["category"] for notice in result["notices"]]
    if test_size is None:
        assert sorted(result["files"]) == ["predictions"]
        assert categories == ["UnmeasuredPlanNotice"]
    else:
        assert text_of(result["files"]["metrics"]) == csv_of(expected.metrics)
        assert categories == [
            "HoldoutEvaluationNotice", "MetricReferenceNotice", "MetricUnitNotice",
        ]
    assert code == expected.code


def test_tool_forecast_evaluation_plan_is_not_registered(tmp_path):
    """
    Test that the plan of an evaluation, which holds the split of the test
    set, is never registered as a plan, and that only the evaluation carries
    the notice that its dates are already in the data. The evaluation
    measures the plan, so the forecast of the future that follows carries no
    notice at all.
    """
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path)

    evaluation = content_of(
        call(server, "forecast", {"plan_id": plan_id, "test_size": 12})
    )
    future = content_of(call(server, "forecast", {"plan_id": plan_id}))
    objects = content_of(call(server, "list_objects", {"kind": "plan"}))["objects"]

    assert [o["id"] for o in objects] == [plan_id]
    assert [notice["category"] for notice in evaluation["notices"]] == [
        "HoldoutEvaluationNotice", "MetricReferenceNotice", "MetricUnitNotice",
    ]
    assert "2007-07-01 00:00:00 to 2008-06-01 00:00:00" in (
        evaluation["notices"][0]["message"]
    )
    assert future["notices"] == []


def test_tool_forecast_with_future_exog(tmp_path):
    """
    Test that the future exogenous values are read from `exog_path` as the
    CLI reads `--exog`, and that without them the error names `exog_path`.
    """
    path = write_csv(tmp_path, "sales.csv", df_single)
    exog_path = write_csv(tmp_path, "future.csv", df_single_future_exog)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, target="sales", steps=10)

    result = content_of(
        call(server, "forecast", {"plan_id": plan_id, "exog_path": exog_path})
    )
    missing = error_of(call(server, "forecast", {"plan_id": plan_id}), "forecast")

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="sales")
    expected = assistant.forecast(
        data=path,
        profile=profile,
        plan=assistant.plan(profile=profile, steps=10),
        exog=load_exog(exog_path, date_column="date"),
    )

    assert text_of(result["files"]["predictions"]) == csv_of(expected.predictions)
    assert missing["code"] == "invalid_argument"
    assert missing["field"] == "exog_path"


@pytest.mark.parametrize(
    "test_size, field",
    [
        ("12", "test_size"), (True, "test_size"), ("1e1", "test_size"),
        ("next month", "test_size"),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_tool_forecast_invalid_argument_when_test_size_is_text_or_bool(
    tmp_path, test_size, field
):
    """
    Test that a number written as text, a bool or text that is not a date
    as `test_size` is `invalid_argument` (text that is not a date reached
    pandas and came back as an `internal_error` without its reason).
    """
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path)

    error = error_of(
        call(server, "forecast", {"plan_id": plan_id, "test_size": test_size}),
        "forecast",
    )

    assert (error["code"], error["field"]) == ("invalid_argument", field)


def test_tool_forecast_exog_changed_while_forecasting(tmp_path, monkeypatch):
    """
    Test that an exogenous file that changes during the call is
    `data_changed` naming `exog_path`, and that nothing is registered.
    """
    path = write_csv(tmp_path, "sales.csv", df_single)
    exog_path = write_csv(tmp_path, "future.csv", df_single_future_exog)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, target="sales", steps=10)
    forecast = ForecastingAssistant.forecast

    def forecast_and_touch(self, *args, **kwargs):
        result = forecast(self, *args, **kwargs)
        with open(exog_path, "a") as handle:
            handle.write("2023-04-21,1.0\n")
        return result

    monkeypatch.setattr(ForecastingAssistant, "forecast", forecast_and_touch)

    error = error_of(
        call(server, "forecast", {"plan_id": plan_id, "exog_path": exog_path}),
        "forecast",
    )
    kinds = [o["kind"] for o in content_of(call(server, "list_objects", {}))["objects"]]

    assert (error["code"], error["field"]) == ("data_changed", "exog_path")
    assert error["hint"] == "Call the tool again once the file no longer changes."
    assert "forecast" not in kinds


def test_tool_forecast_file_too_large_for_exog_or_grown_data(tmp_path):
    """
    Test that a file of future exogenous values larger than `max_file_mb` is
    `file_too_large` on `exog_path`, and that a data file that grew beyond
    the limit after it was profiled is `data_changed` (it changed, and the
    tool takes no path to pass a smaller one) without being read again.
    """
    path = write_csv(tmp_path, "sales.csv", df_single)
    exog_path = write_csv(tmp_path, "future.csv", df_single_future_exog)
    with open(exog_path, "a", encoding="utf-8") as handle:
        handle.write("\n" * (1024 * 1024))
    server = create_server(
        allow_dir=tmp_path, output_dir=tmp_path / "out", max_file_mb=1
    )
    _, plan_id = profile_and_plan(server, path, target="sales", steps=10)

    exog_error = error_of(
        call(server, "forecast", {"plan_id": plan_id, "exog_path": exog_path}),
        "forecast",
    )
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n" * (1024 * 1024))
    data_error = error_of(
        call(server, "forecast", {"plan_id": plan_id, "test_size": 10}), "forecast"
    )

    assert (exog_error["code"], exog_error["field"]) == ("file_too_large", "exog_path")
    assert (data_error["code"], data_error["field"]) == ("data_changed", "data_path")
    assert data_error["hint"] == "Call `profile` again on the file as it is now."


def test_tool_forecast_without_exog_when_plan_does_not_use_them(tmp_path):
    """
    Test that a plan built with `use_exog=false` forecasts data with
    exogenous columns without `exog_path`, as the Python API does, with a
    notice that says they were left out, and that passing `exog_path` to it
    is an `invalid_argument` without the hint about the file of the user:
    the argument is the agent's to drop.
    """
    path = write_csv(tmp_path, "sales.csv", df_single)
    exog_path = write_csv(tmp_path, "future.csv", df_single_future_exog)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(
        server, path, target="sales", steps=10, use_exog=False
    )

    result = content_of(call(server, "forecast", {"plan_id": plan_id}))
    given = error_of(
        call(server, "forecast", {"plan_id": plan_id, "exog_path": exog_path}),
        "forecast",
    )

    assistant = ForecastingAssistant()
    profile = assistant.profile(path, target="sales")
    expected = assistant.forecast(
        data=path,
        profile=profile,
        plan=assistant.plan(profile=profile, steps=10, use_exog=False),
    )

    assert text_of(result["files"]["predictions"]) == csv_of(expected.predictions)
    assert [notice["category"] for notice in result["notices"]] == [
        "UnmeasuredPlanNotice", "ExogLeftOutNotice"
    ]
    assert (given["code"], given["field"]) == ("invalid_argument", "exog_path")
    assert given["message"] == (
        "`exog` was provided but the plan does not use exogenous variables "
        "(`plan.use_exog` is False). Remove `exog`."
    )
    assert given["hint"] is None


def test_tool_forecast_invalid_argument_when_future_exog_is_missing(tmp_path):
    """
    Test that a plan with exogenous variables carries a notice about their
    future values, and that forecasting it without `exog_path` is
    `invalid_argument` with a hint that leaves those values to the user:
    the message of the library offers `test_size`, and an agent without the
    hint writes the file itself or reports the evaluation as the forecast.
    """
    path = write_csv(tmp_path, "sales.csv", df_single)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, target="sales", steps=10)

    plan = content_of(call(server, "describe_object", {"object_id": plan_id}))
    error = error_of(call(server, "forecast", {"plan_id": plan_id}), "forecast")

    assert [notice["category"] for notice in plan["notices"]] == ["FutureExogNotice"]
    assert (error["code"], error["field"]) == ("invalid_argument", "exog_path")
    assert error["message"] == (
        "`exog` is required for future prediction because the data contains "
        "exogenous variables. Provide future exogenous values covering the "
        "forecast horizon, or pass `test_size` to run in evaluation mode "
        "instead."
    )
    assert error["hint"] == (
        "Only the user has the future values: never write, copy or estimate "
        "them yourself. Ask the user for a CSV file with them, or build the "
        "plan again with `use_exog: false` and tell the user the exogenous "
        "variables were left out. Measure that new plan before forecasting, "
        "on the same folds with `backtest(cv_id, plan_id)`, and report its "
        "accuracy, not that of the plan with exogenous variables. Do not pass "
        "`test_size`: it evaluates dates already in the data, which is not "
        "the forecast the user asked for."
    )


def test_tool_forecast_invalid_argument_when_foundation_series_ends_early(
    tmp_path, monkeypatch
):
    """
    Test that evaluating a ForecasterFoundation plan on long data where one
    series ends before the test split is `invalid_argument` before any
    script runs (it was `execution_failed` after the metrics of the script
    failed), naming the series and its dates.
    """

    def _not_called(*args, **kwargs):
        raise AssertionError("run_forecast must not be called")

    monkeypatch.setattr("skforecast_ai.assistant.run_forecast", _not_called)
    # The backend of the foundation model is not installed in CI, and its
    # check comes first.
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: True
    )
    data = df_items_sales_long.loc[
        (df_items_sales_long["series"] != "item_2")
        | (df_items_sales_long["date"] <= "2012-04-19")
    ]
    path = write_csv(tmp_path, "items.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    profile = content_of(
        call(
            server,
            "profile",
            {
                "data_path": path,
                "target": "value",
                "date_column": "date",
                "series_id_column": "series",
            },
        )
    )
    plan = content_of(
        call(
            server,
            "plan",
            {
                "profile_id": profile["id"],
                "steps": 7,
                "forecaster": "ForecasterFoundation",
            },
        )
    )

    error = error_of(
        call(server, "forecast", {"plan_id": plan["id"], "test_size": 7}),
        "forecast",
    )

    assert error["code"] == "invalid_argument"
    assert error["message"] == (
        "The target has missing values in the test split ('item_2': 7 value(s), "
        "such as '2012-04-23', '2012-04-24', '2012-04-25', '2012-04-26', "
        "'2012-04-27' and 2 more). skforecast cannot compute the metrics on "
        "them, whatever the estimator. Impute the target, or evaluate on dates "
        "without missing values. Series without any value in the test split "
        "('item_2') end before it: remove them from the data, or evaluate on "
        "dates they reach."
    )
    assert error["field"] == "data_path"


def test_tool_forecast_invalid_argument_with_hint_when_final_rows_have_no_target(
    tmp_path,
):
    """
    Test that forecasting data whose last rows have no target value is
    `invalid_argument` on `data_path` with the hint of the server that
    leaves the values to the user: the message says to drop the rows, which
    an agent does without asking.
    """
    data = df_single.drop(columns="promo")
    data.loc[data.index[-3:], "sales"] = float("nan")
    path = write_csv(tmp_path, "tail.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, target="sales", steps=10)

    error = error_of(call(server, "forecast", {"plan_id": plan_id}), "forecast")

    assert (error["code"], error["field"]) == ("invalid_argument", "data_path")
    assert error["message"] == (
        "The data has no target value after 2023-04-07: drop its last 3 "
        "row(s) (2023-04-08 to 2023-04-10), so that it ends with the last "
        "value of the target."
    )
    assert error["hint"] == DATA_VALUES_HINT


def test_tool_forecast_invalid_argument_with_hint_when_future_exog_has_missing_values(
    tmp_path,
):
    """
    Test that a file of future exogenous values with a missing value, for
    an estimator that cannot use it, is `invalid_argument` on `exog_path`
    with a hint that leaves the file to the user.
    """
    future = df_single_future_exog.copy()
    future.iloc[2, 1] = float("nan")
    path = write_csv(tmp_path, "sales.csv", df_single)
    exog_path = write_csv(tmp_path, "future.csv", future)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(
        server, path, target="sales", steps=10, estimator="Ridge"
    )

    error = error_of(
        call(server, "forecast", {"plan_id": plan_id, "exog_path": exog_path}),
        "forecast",
    )

    assert (error["code"], error["field"]) == ("invalid_argument", "exog_path")
    assert error["message"] == (
        "`exog` has missing values in the rows to forecast ('promo': 1 "
        "value(s), such as '2023-04-13'). ForecasterRecursive with Ridge "
        "cannot use them, so its predictions would be missing. "
        "Either they are filled in, or the plan uses an estimator that "
        "accepts missing values (such as 'RandomForestRegressor')."
    )
    assert error["hint"] == (
        "The file of future values is the user's: tell them what the message "
        "says and let them correct it. Never write or change those values "
        "yourself."
    )


def test_tool_forecast_invalid_argument_with_hint_when_future_exog_has_no_date_column(
    tmp_path,
):
    """
    Test that a file of future exogenous values without the date column of
    the data, which fails before the forecast runs, is `invalid_argument`
    on `exog_path` with the hint that leaves the file to the user.
    """
    future = df_single_future_exog.rename(columns={"date": "day"})
    path = write_csv(tmp_path, "sales.csv", df_single)
    exog_path = write_csv(tmp_path, "future.csv", future)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, target="sales", steps=10)

    error = error_of(
        call(server, "forecast", {"plan_id": plan_id, "exog_path": exog_path}),
        "forecast",
    )

    assert (error["code"], error["field"]) == ("invalid_argument", "exog_path")
    assert error["message"] == (
        f"The exog CSV '{exog_path}' has no column 'date'; its columns are "
        f"['day', 'promo']."
    )
    assert error["hint"] == (
        "The file of future values is the user's: tell them what the message "
        "says and let them correct it. Never write or change those values "
        "yourself."
    )


def test_tool_forecast_invalid_argument_without_hint_when_exog_path_and_test_size(
    tmp_path,
):
    """
    Test that `exog_path` together with `test_size` is `invalid_argument`
    on `exog_path` without the hint about the file of the user: nothing is
    wrong in the file, the agent passed an argument an evaluation does not
    take.
    """
    path = write_csv(tmp_path, "sales.csv", df_single)
    exog_path = write_csv(tmp_path, "future.csv", df_single_future_exog)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, target="sales", steps=10)

    error = error_of(
        call(
            server,
            "forecast",
            {"plan_id": plan_id, "exog_path": exog_path, "test_size": 10},
        ),
        "forecast",
    )

    assert (error["code"], error["field"]) == ("invalid_argument", "exog_path")
    assert error["message"] == (
        "`exog` is only used for future prediction (`test_size=None`). In "
        "evaluation mode the test-set exogenous values are taken from the "
        "train/test split, so `exog` must not be provided."
    )
    assert error["hint"] is None


def test_tool_forecast_on_semicolon_file_matches_the_comma_file(tmp_path):
    """
    Test that `plan` and `forecast` on a ';' file with a decimal comma give
    the predictions of the same data in a comma file, and that the script of
    the forecast reads the file with its dialect.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    comma_path = write_csv(tmp_path, "us.csv", df_dialect)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, target="y", steps=3)
    _, comma_plan_id = profile_and_plan(server, comma_path, target="y", steps=3)

    result = content_of(call(server, "forecast", {"plan_id": plan_id}))
    expected = content_of(call(server, "forecast", {"plan_id": comma_plan_id}))
    code = content_of(call(server, "get_code", {"object_id": result["id"]}))

    assert text_of(result["files"]["predictions"]) == text_of(
        expected["files"]["predictions"]
    )
    assert f"data = pd.read_csv({path!r}, sep=';', decimal=',')\n" in code["code"]


def test_tool_forecast_with_future_exog_in_a_semicolon_file(tmp_path):
    """
    Test that the future exogenous values are read from an `exog_path` with
    ';' and a decimal comma, giving the predictions of the comma file.
    """
    path = write_csv(tmp_path, "sales.csv", df_single)
    exog_path = write_csv(tmp_path, "future.csv", df_single_future_exog)
    semicolon_path = str(tmp_path / "future_eu.csv")
    df_single_future_exog.to_csv(semicolon_path, sep=";", decimal=",", index=False)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, target="sales", steps=10)

    result = content_of(
        call(server, "forecast", {"plan_id": plan_id, "exog_path": semicolon_path})
    )
    expected = content_of(
        call(server, "forecast", {"plan_id": plan_id, "exog_path": exog_path})
    )

    assert text_of(result["files"]["predictions"]) == text_of(
        expected["files"]["predictions"]
    )


def test_tool_forecast_data_changed_when_gzip_file_was_modified(tmp_path):
    """
    Test that a '.csv.gz' file rewritten after it was profiled is
    `data_changed` and nothing runs.
    """
    path = write_dialect(tmp_path, df_dialect, "gz_semicolon_comma")
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(server, path, target="y", steps=3)
    df_dialect.assign(y=df_dialect["y"] + 1).to_csv(
        path, sep=";", decimal=",", index=False
    )

    error = error_of(call(server, "forecast", {"plan_id": plan_id}), "forecast")

    assert error["code"] == "data_changed"
    assert error["field"] == "data_path"
    assert error["message"] == (
        f"The file {path!r} changed since it was profiled, so its profile and "
        f"the objects built from it no longer describe it. Nothing was run."
    )


def test_tool_forecast_output_when_series_ids_are_numbers(tmp_path):
    """
    Test that `forecast` runs on long-format data whose series ids are
    numbers ('001', '1', '10'), with the future exogenous variables of
    `exog_path` read with the same ids as text, as the Python API does.
    Before, it failed as `execution_failed` with `KeyError: 1` inside
    skforecast (skforecast issue #1357).
    """
    path = write_csv(tmp_path, "stores.csv", df_numeric_ids_exog)
    exog_path = write_csv(tmp_path, "future.csv", df_numeric_ids_future_exog)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    arguments = {"target": "value", "series_id_column": "series_id"}
    profile = content_of(call(server, "profile", {"data_path": path, **arguments}))
    plan = content_of(
        call(server, "plan", {"profile_id": profile["id"], "steps": 7})
    )

    result = content_of(
        call(server, "forecast", {"plan_id": plan["id"], "exog_path": exog_path})
    )

    assistant = ForecastingAssistant()
    expected_profile = assistant.profile(path, **arguments)
    expected = assistant.forecast(
        data=path,
        profile=expected_profile,
        plan=assistant.plan(profile=expected_profile, steps=7),
        exog=load_exog(exog_path, date_column="date", series_id_column="series_id"),
    )
    predictions = pd.read_csv(
        result["files"]["predictions"], index_col=0, dtype={"level": str}
    )

    assert expected.plan.use_exog is True
    assert result["summary"] == expected.describe()
    assert text_of(result["files"]["predictions"]) == csv_of(expected.predictions)
    assert sorted(predictions["level"].unique()) == ["001", "1", "10"]


def test_tool_forecast_notice_of_undefined_mape_when_target_crosses_zero(tmp_path):
    """
    Test that MAPE requested on a target that crosses zero gets, in the
    response of `forecast`, the notice that it has no meaning instead of its
    unit, which needs the profile of the data.
    """
    path = write_csv(tmp_path, "profit.csv", df_crossing_zero)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    _, plan_id = profile_and_plan(
        server, path, target="profit", steps=6,
        metric="mean_absolute_percentage_error",
    )

    result = content_of(
        call(server, "forecast", {"plan_id": plan_id, "test_size": 6})
    )
    assert [n["category"] for n in result["notices"]] == ["HoldoutEvaluationNotice", "MetricUndefinedNotice"]
    assert result["notices"][-1]["message"].startswith(
        "`mean_absolute_percentage_error` has no meaning on this data"
    )


UNMEASURED_MESSAGE = (
    "No `backtest`, `compare` or `forecast` with `test_size` in this session "
    "measured this plan (the same decisions, with any interval or metric), so "
    "this forecast has no measure of accuracy. Say so, and before presenting "
    "it as reliable measure it: "
    "`create_cv` with this `plan_id`, then `backtest` or `compare`. Never give "
    "the accuracy of another plan as that of this forecast."
)


def _categories(result: dict) -> list[str]:
    """
    Categories of the notices of a response.
    """

    return [notice["category"] for notice in result["notices"]]


def test_tool_forecast_unmeasured_notice_until_the_plan_is_backtested(tmp_path):
    """
    Test that a forecast of the future of a plan no backtest measured carries
    the `UnmeasuredPlanNotice`, and that once a backtest of that plan ran the
    same forecast carries none.
    """
    server, path = h2o_server(tmp_path)

    async def steps(client):
        profile = content_of(
            await client.call_tool("profile", {"data_path": path, "target": "x"})
        )
        plan = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 12})
        )
        before = content_of(
            await client.call_tool("forecast", {"plan_id": plan["id"]})
        )
        cv = content_of(await client.call_tool("create_cv", {"plan_id": plan["id"]}))
        content_of(await client.call_tool("backtest", {"cv_id": cv["id"]}))
        after = content_of(
            await client.call_tool("forecast", {"plan_id": plan["id"]})
        )
        return before, after

    before, after = run_session(server, steps)

    assert before["notices"] == [
        {
            "source": "runtime",
            "category": "UnmeasuredPlanNotice",
            "message": UNMEASURED_MESSAGE,
            "count": 1,
        }
    ]
    assert after["notices"] == []


@pytest.mark.parametrize(
    "rebuild",
    ["plan", "refine_plan"],
    ids=lambda dt: f"rebuild: {dt}",
)
def test_tool_forecast_no_unmeasured_notice_when_plan_rebuilt_with_interval(
    tmp_path, rebuild
):
    """
    Test that a plan built again with the decisions of a backtested plan plus
    an interval (with `plan` or with `refine_plan`), which has another id,
    counts as measured: the interval does not change the point predictions.
    """
    server, path = h2o_server(tmp_path)

    async def steps(client):
        profile = content_of(
            await client.call_tool("profile", {"data_path": path, "target": "x"})
        )
        plan = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 12})
        )
        cv = content_of(await client.call_tool("create_cv", {"plan_id": plan["id"]}))
        content_of(await client.call_tool("backtest", {"cv_id": cv["id"]}))
        if rebuild == "plan":
            arguments = {
                "profile_id": profile["id"], "steps": 12, "interval": [0.1, 0.9],
            }
        else:
            arguments = {
                "plan_id": plan["id"], "overrides": {"interval": [0.1, 0.9]},
            }
        rebuilt = content_of(await client.call_tool(rebuild, arguments))
        forecast = content_of(
            await client.call_tool("forecast", {"plan_id": rebuilt["id"]})
        )
        return plan, rebuilt, forecast

    plan, rebuilt, forecast = run_session(server, steps)

    assert rebuilt["id"] != plan["id"]
    assert "UnmeasuredPlanNotice" not in _categories(forecast)


def test_tool_forecast_unmeasured_notice_when_another_plan_was_measured(tmp_path):
    """
    Test that a backtest of one plan does not count for another: a plan
    refined with another estimator, and the same decisions on another
    profile of the data, still carry the `UnmeasuredPlanNotice`. The plan
    with the estimator chosen by the user also carries the
    `EstimatorNotRecommendedNotice`.
    """
    server, path = h2o_server(tmp_path)

    async def steps(client):
        profile = content_of(
            await client.call_tool("profile", {"data_path": path, "target": "x"})
        )
        plan = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 12})
        )
        cv = content_of(await client.call_tool("create_cv", {"plan_id": plan["id"]}))
        content_of(await client.call_tool("backtest", {"cv_id": cv["id"]}))
        refined = content_of(
            await client.call_tool(
                "refine_plan",
                {
                    "plan_id": plan["id"],
                    "overrides": {"estimator": "RandomForestRegressor"},
                },
            )
        )
        other_estimator = content_of(
            await client.call_tool("forecast", {"plan_id": refined["id"]})
        )
        other_profile = content_of(
            await client.call_tool("profile", {"data_path": path, "target": "x"})
        )
        same_plan = content_of(
            await client.call_tool(
                "plan", {"profile_id": other_profile["id"], "steps": 12}
            )
        )
        other_data = content_of(
            await client.call_tool("forecast", {"plan_id": same_plan["id"]})
        )
        return other_estimator, other_data

    other_estimator, other_data = run_session(server, steps)

    assert sorted(_categories(other_estimator)) == [
        "EstimatorNotRecommendedNotice",
        "UnmeasuredPlanNotice",
    ]
    assert _categories(other_data) == ["UnmeasuredPlanNotice"]


def test_tool_forecast_no_unmeasured_notice_for_any_candidate_of_compare(tmp_path):
    """
    Test that `compare` measures every candidate that ran, not only the
    winner: neither the plan of the winner nor a plan built again with the
    decisions of another candidate (ForecasterDirect) carries the
    `UnmeasuredPlanNotice`.
    """
    server, path = h2o_server(tmp_path)

    async def steps(client):
        profile = content_of(
            await client.call_tool("profile", {"data_path": path, "target": "x"})
        )
        plan = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 12})
        )
        cv = content_of(await client.call_tool("create_cv", {"plan_id": plan["id"]}))
        comparison = content_of(
            await client.call_tool("compare", {"cv_id": cv["id"]})
        )
        direct = content_of(
            await client.call_tool(
                "refine_plan",
                {
                    "plan_id": plan["id"],
                    "overrides": {"forecaster": "ForecasterDirect"},
                },
            )
        )
        best = content_of(
            await client.call_tool(
                "forecast", {"plan_id": comparison["links"]["best_plan_id"]}
            )
        )
        other = content_of(
            await client.call_tool("forecast", {"plan_id": direct["id"]})
        )
        return comparison, best, other

    comparison, best, other = run_session(server, steps)

    assert "ForecasterDirect" in comparison["summary"]
    assert "UnmeasuredPlanNotice" not in _categories(best)
    assert "UnmeasuredPlanNotice" not in _categories(other)


def test_tool_forecast_evaluation_says_it_is_a_holdout_without_unmeasured_notice(
    tmp_path,
):
    """
    Test that a forecast with `test_size` of a plan never measured gets no
    `UnmeasuredPlanNotice` (it is a measure itself), that its summary, the
    context `ask()` reads, says in words that it is a hold-out evaluation on
    dates already in the data and not the future, and that it measures the
    plan for the forecast of the future that follows.
    """
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path)

    result = content_of(
        call(server, "forecast", {"plan_id": plan_id, "test_size": 12})
    )
    future = content_of(call(server, "forecast", {"plan_id": plan_id}))

    assert _categories(result) == [
        "HoldoutEvaluationNotice", "MetricReferenceNotice", "MetricUnitNotice",
    ]
    assert (
        "<evaluation_metrics>\n"
        "Hold-out evaluation, not a forecast of the future: the model was "
        "trained on the data up to 2007-06-01 and predicted the next 12 steps, "
        "whose dates are already in the data. These metrics score those "
        "predictions against the observed values.\n"
    ) in result["summary"]
    assert future["notices"] == []


def test_tool_forecast_no_unmeasured_notice_when_plan_refined_with_another_metric(
    tmp_path,
):
    """
    Test that a backtested plan refined with another metric counts as
    measured (the metric does not change the predictions), and that a plan
    measured only by a forecast with `test_size` of another plan does not.
    """
    server, path = h2o_server(tmp_path)

    async def steps(client):
        profile = content_of(
            await client.call_tool("profile", {"data_path": path, "target": "x"})
        )
        plan = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 12})
        )
        cv = content_of(await client.call_tool("create_cv", {"plan_id": plan["id"]}))
        content_of(await client.call_tool("backtest", {"cv_id": cv["id"]}))
        refined = content_of(
            await client.call_tool(
                "refine_plan",
                {
                    "plan_id": plan["id"],
                    "overrides": {"metric": "mean_squared_error"},
                },
            )
        )
        other_metric = content_of(
            await client.call_tool("forecast", {"plan_id": refined["id"]})
        )
        other = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 6})
        )
        content_of(
            await client.call_tool(
                "forecast", {"plan_id": other["id"], "test_size": 6}
            )
        )
        other_horizon = content_of(
            await client.call_tool(
                "plan", {"profile_id": profile["id"], "steps": 3}
            )
        )
        unmeasured = content_of(
            await client.call_tool("forecast", {"plan_id": other_horizon["id"]})
        )
        return refined, other_metric, unmeasured

    refined, other_metric, unmeasured = run_session(server, steps)

    assert "- Primary metric: mean_squared_error" in refined["summary"]
    assert other_metric["notices"] == []
    assert _categories(unmeasured) == ["UnmeasuredPlanNotice"]
