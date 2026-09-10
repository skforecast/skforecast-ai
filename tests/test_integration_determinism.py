# Integration test: same input, same output

import pandas as pd
import pytest

from skforecast_ai import ForecastingAssistant

from tests.fixtures_assistant import df_multi_long, df_single


@pytest.mark.parametrize(
    "data, kwargs",
    [
        (df_single, {"target": "sales", "date_column": "date"}),
        (df_multi_long, {"target": "value", "date_column": "date", "series_id_column": "series_id"}),
    ],
    ids=["single series", "multi series"],
)
def test_forecast_workflow_is_deterministic(data, kwargs):
    """
    Test the first promise of the README: the same input always yields
    the same profile, plan, script and predictions, across two independent
    assistants and two separate runs.
    """
    first = ForecastingAssistant()
    second = ForecastingAssistant()

    profile_1 = first.profile(data=data.copy(), **kwargs)
    profile_2 = second.profile(data=data.copy(), **kwargs)
    plan_1 = first.plan(profile_1, steps=5)
    plan_2 = second.plan(profile_2, steps=5)
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
