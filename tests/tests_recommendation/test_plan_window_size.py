# Unit test plan_window_size

import pytest

from skforecast_ai.recommendation.backtesting import plan_window_size

from ..tests_rendering.fixtures_rendering import (
    plan_baseline,
    plan_foundation,
    plan_single_differentiation,
    plan_single_recursive_no_exog,
    plan_single_with_window_features,
    plan_statistical,
)


@pytest.mark.parametrize(
    "plan, expected",
    [
        (plan_single_recursive_no_exog, 7),
        (
            plan_single_with_window_features.model_copy(update={
                "forecaster_kwargs": {
                    "lags": 3,
                    "window_features": [
                        {"stats": ["mean", "std"], "window_size": [5, 14]}
                    ],
                }
            }),
            14,
        ),
        (plan_single_differentiation, 8),
        (plan_baseline, 7),
        (plan_statistical, None),
        (plan_foundation, None),
    ],
    ids=["lags", "window features", "differentiation", "baseline", "stats",
         "foundation"],
)
def test_plan_window_size_output(plan, expected):
    """
    Test that the window size is the largest lag or window feature plus the
    differentiation order for a machine learning forecaster, the offsets for
    the baseline, and None for ForecasterStats and ForecasterFoundation.
    """
    assert plan_window_size(plan) == expected
