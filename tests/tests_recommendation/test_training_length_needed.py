# Unit test training_length_needed

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.recommendation.backtesting import training_length_needed

from .fixtures_recommendation import forecasting_profile_h2o, window_12_kwargs


@pytest.mark.parametrize(
    "plan_arguments, expected",
    [
        ({"steps": 6, **window_12_kwargs}, (13, "more than its window size, 12")),
        (
            {"steps": 6, **window_12_kwargs, "forecaster": "ForecasterDirect"},
            (18, "its window size, 12, plus the 6 steps it is trained to predict"),
        ),
        ({"steps": 6, "forecaster": "ForecasterStats"}, None),
    ],
    ids=["recursive", "direct", "stats"],
)
def test_training_length_needed_output(plan_arguments, expected):
    """
    Test that a recursive forecaster needs more observations than its
    window, a direct one the window plus `steps`, and that a forecaster
    without a window has no minimum.
    """
    plan = ForecastingAssistant().plan(forecasting_profile_h2o, **plan_arguments)

    assert training_length_needed(plan) == expected
