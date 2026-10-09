# Integration test: same input, same output

import pandas as pd
import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant

from tests.fixtures_assistant import df_multi_long, df_single


@pytest.mark.parametrize(
    "data, kwargs",
    [
        (df_single, {"target": "sales", "date_column": "date"}),
        (df_multi_long, {"target": "value", "date_column": "date", "series_id_column": "series_id"}),
        (df_single, {"target": "sales", "date_column": "date", "forecaster": "ForecasterEquivalentDate"}),
    ],
    ids=["single series", "multi series", "baseline"],
)
def test_forecast_workflow_is_deterministic(data, kwargs):
    """
    Test the first promise of the README: the same input always yields
    the same profile, plan, script and predictions, across two independent
    assistants and two separate runs.
    """
    first = ForecastingAssistant()
    second = ForecastingAssistant()

    profile_kwargs = {k: v for k, v in kwargs.items() if k != "forecaster"}
    profile_1 = first.profile(data=data.copy(), **profile_kwargs)
    profile_2 = second.profile(data=data.copy(), **profile_kwargs)
    plan_1 = first.plan(profile_1, steps=5, forecaster=kwargs.get("forecaster"))
    plan_2 = second.plan(profile_2, steps=5, forecaster=kwargs.get("forecaster"))
    result_1 = first.forecast(data=data.copy(), steps=5, test_size=5, **kwargs)
    result_2 = second.forecast(data=data.copy(), steps=5, test_size=5, **kwargs)

    assert profile_1.model_dump() == profile_2.model_dump()
    assert plan_1.model_dump() == plan_2.model_dump()
    assert result_1.code == result_2.code
    pd.testing.assert_frame_equal(result_1.predictions, result_2.predictions)
    pd.testing.assert_frame_equal(result_1.metrics, result_2.metrics)


def test_forecast_code_and_forecast_render_the_same_script():
    """
    Test that the script returned by forecast_code() is the script
    forecast() executes for the same inputs, so inspecting one and
    running the other can never diverge.
    """
    assistant = ForecastingAssistant()
    kwargs = dict(data=df_single, target="sales", date_column="date", steps=5, test_size=5)

    rendered = assistant.forecast_code(**kwargs).code
    executed = assistant.forecast(**kwargs).code

    assert rendered == executed


@pytest.mark.parametrize(
    "data, kwargs",
    [
        (df_single, {"target": "sales", "date_column": "date"}),
        (df_multi_long, {"target": "value", "date_column": "date", "series_id_column": "series_id"}),
    ],
    ids=["single series", "multi series"],
)
def test_forecast_workflow_is_deterministic_when_data_is_csv_path(
    tmp_path, data, kwargs
):
    """
    Test that the same CSV path always yields the same profile, plan,
    script and predictions, across two independent assistants, and that
    the script loads that path.
    """
    csv_path = tmp_path / "data.csv"
    data.to_csv(csv_path, index=False)
    first = ForecastingAssistant()
    second = ForecastingAssistant()

    profile_1 = first.profile(data=csv_path, **kwargs)
    profile_2 = second.profile(data=csv_path, **kwargs)
    plan_1 = first.plan(profile_1, steps=5)
    plan_2 = second.plan(profile_2, steps=5)
    result_1 = first.forecast(data=csv_path, steps=5, test_size=5, **kwargs)
    result_2 = second.forecast(data=csv_path, steps=5, test_size=5, **kwargs)

    assert profile_1.model_dump() == profile_2.model_dump()
    assert plan_1.model_dump() == plan_2.model_dump()
    assert result_1.code == result_2.code
    assert f"data = pd.read_csv({str(csv_path)!r})" in result_1.code
    pd.testing.assert_frame_equal(result_1.predictions, result_2.predictions)
    pd.testing.assert_frame_equal(result_1.metrics, result_2.metrics)


def test_code_methods_and_executing_methods_render_the_same_script_when_csv_path(
    tmp_path,
):
    """
    Test that, with a CSV path, forecast() and backtest() return the script
    of forecast_code() and backtest_code(): the executing methods profile
    the DataFrame read from the path, and still record the path.
    """
    csv_path = tmp_path / "sales.csv"
    df_single.to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    kwargs = dict(data=csv_path, target="sales", date_column="date")
    cv = TimeSeriesFold(steps=5, initial_train_size=60)

    forecast_code = assistant.forecast_code(**kwargs, steps=5, test_size=5).code
    forecast_run = assistant.forecast(**kwargs, steps=5, test_size=5)
    backtest_code = assistant.backtest_code(**kwargs, cv=cv).code
    backtest_run = assistant.backtest(**kwargs, cv=cv, show_progress=False)

    assert forecast_run.code == forecast_code
    assert backtest_run.code == backtest_code
    assert forecast_run.profile.data_profile.data_path == str(csv_path)
    assert backtest_run.profile.data_profile.data_path == str(csv_path)
