# Unit test llm_min_train_size skforecast_ai.llm.refinement

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.llm.refinement import llm_min_train_size

from tests.fixtures_datasets import df_h2o

assistant = ForecastingAssistant()
profile = assistant.profile(data=df_h2o, target="x")


@pytest.mark.parametrize(
    "plan_arguments, expected",
    [
        ({"steps": 12}, 48),
        ({"steps": 12, "forecaster": "ForecasterDirect"}, 48),
        ({"steps": 12, "lags": 3, "window_features": []}, 15),
        ({"steps": 12, "forecaster": "ForecasterStats"}, 24),
        ({"steps": 3, "forecaster": "ForecasterEquivalentDate"}, 15),
    ],
    ids=["recursive", "direct", "recursive_small_window", "stats", "baseline"],
)
def test_llm_min_train_size_output_when_rule_minimum_fits(plan_arguments, expected):
    """
    Test that the minimum given to the LLM is the one the rules reserve for
    the forecaster (its window of 36 plus the 12 steps, the window of 3
    plus the steps, twice the steps without a window, the offset of 12 plus
    the 3 steps) when it leaves two folds in the 204 observations.
    """
    plan = assistant.plan(profile, **plan_arguments)

    assert llm_min_train_size(profile, plan) == expected


@pytest.mark.parametrize(
    "plan_arguments, expected",
    [
        ({"steps": 60, "lags": 12}, 84),
        ({"steps": 80, "forecaster": "ForecasterStats"}, 44),
    ],
    ids=["recursive", "stats"],
)
def test_llm_min_train_size_output_never_above_the_room_for_two_folds(
    plan_arguments, expected
):
    """
    Test that with a long horizon the minimum is lowered to the largest
    size that leaves two folds (204 - 2 * 60 and 204 - 2 * 80), so it never
    exceeds the maximum the LLM is given: the rules reserved 96 and 160.
    """
    plan = assistant.plan(profile, **plan_arguments)

    assert llm_min_train_size(profile, plan) == expected


def test_llm_min_train_size_output_leaves_two_training_rows():
    """
    Test that with one step the minimum is two more than the window of 36,
    not one: a window plus one observation trains on a single row, which
    an estimator such as LightGBM does not fit.
    """
    plan = assistant.plan(profile, steps=1, estimator="Ridge")

    assert llm_min_train_size(profile, plan) == 38
