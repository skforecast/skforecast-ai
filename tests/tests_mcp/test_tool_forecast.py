# Unit test tool forecast

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai._utils import load_exog
from skforecast_ai.mcp import create_server

from ..fixtures_assistant import df_single
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
    if test_size is None:
        assert sorted(result["files"]) == ["predictions"]
    else:
        assert text_of(result["files"]["metrics"]) == expected.metrics.to_csv()
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
    [("12", "test_size"), (True, "test_size"), ("1e1", "test_size")],
    ids=lambda dt: f"{dt!r}",
)
def test_tool_forecast_invalid_argument_when_test_size_is_text_or_bool(
    tmp_path, test_size, field
):
    """
    Test that a number written as text or a bool as `test_size` is
    `invalid_argument`.
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
