# Unit test tool forecast

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai._utils import load_exog
from skforecast_ai.mcp import create_server

from ..fixtures_assistant import df_single
from ..fixtures_datasets import df_items_sales_long
from .fixtures_mcp import (
    call,
    df_single_future_exog,
    content_of,
    error_of,
    h2o_server,
    profile_and_plan,
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
    assert text_of(result["files"]["predictions"]) == expected.predictions.to_csv()
    # Only an evaluation has metrics, and with them the notice that gives
    # the reference of MASE.
    categories = [notice["category"] for notice in result["notices"]]
    if test_size is None:
        assert sorted(result["files"]) == ["predictions"]
        assert categories == []
    else:
        assert text_of(result["files"]["metrics"]) == expected.metrics.to_csv()
        assert categories == ["MetricReferenceNotice"]
    assert code == expected.code


def test_tool_forecast_evaluation_plan_is_not_registered(tmp_path):
    """
    Test that the plan of an evaluation, which holds the split of the test
    set, is never registered as a plan.
    """
    server, path = h2o_server(tmp_path)
    _, plan_id = profile_and_plan(server, path)

    content_of(call(server, "forecast", {"plan_id": plan_id, "test_size": 12}))
    objects = content_of(call(server, "list_objects", {"kind": "plan"}))["objects"]

    assert [o["id"] for o in objects] == [plan_id]


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

    assert text_of(result["files"]["predictions"]) == expected.predictions.to_csv()
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
    is an `invalid_argument`.
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

    assert text_of(result["files"]["predictions"]) == expected.predictions.to_csv()
    assert [notice["category"] for notice in result["notices"]] == [
        "ExogLeftOutNotice"
    ]
    assert (given["code"], given["field"]) == ("invalid_argument", "exog_path")


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
        "variables were left out. Do not pass `test_size`: it evaluates dates "
        "already in the data, which is not the forecast the user asked for."
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
