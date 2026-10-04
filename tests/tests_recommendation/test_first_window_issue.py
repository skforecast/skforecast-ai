# Unit test first_window_issue

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation.backtesting import first_window_issue

from ..tests_rendering.fixtures_rendering import (
    plan_baseline,
    plan_foundation,
    plan_single_differentiation,
    plan_single_direct,
    profile_single_no_exog,
)


@pytest.mark.parametrize(
    "plan, initial_train_size, expected",
    [
        (
            plan_single_differentiation, 8,
            "The first training window of the strategy has 8 observations, and "
            "ForecasterRecursive needs at least 9 (more than its window size, "
            "8), so skforecast would fail",
        ),
        (plan_single_differentiation, 9, None),
        (
            plan_baseline, 7,
            "The first training window of the strategy has 7 observations, and "
            "ForecasterEquivalentDate needs at least 8 (more than its window "
            "size, 7), so skforecast would fail",
        ),
        (plan_baseline, 8, None),
        (
            plan_single_direct, 11,
            "The first training window of the strategy has 11 observations, "
            "and ForecasterDirect needs at least 12 (its window size, 7, plus "
            "the 5 steps it is trained to predict), so skforecast would fail",
        ),
        (plan_single_direct, 12, None),
        (plan_foundation, 2, None),
    ],
    ids=["window_equal", "window_shorter", "baseline_equal",
         "baseline_shorter", "direct_too_short", "direct_enough", "foundation"],
)
def test_first_window_issue_output(plan, initial_train_size, expected):
    """
    Test that a first training window not longer than the window of the
    forecaster is an issue (skforecast needs more observations than its
    window size, and a direct forecaster at least its window size plus
    `steps`), that one observation more is not, and that a foundation
    model, whose window is not checked, has none.
    """
    cv = TimeSeriesFold(
        steps              = 5,
        initial_train_size = initial_train_size,
        verbose            = False,
    )

    assert first_window_issue(plan, cv, profile_single_no_exog) == expected


def test_first_window_issue_output_when_initial_train_size_is_a_date():
    """
    Test that a date `initial_train_size` is placed on the dates of the
    profile (daily, from 2023-01-01): '2023-01-08' leaves 8 observations,
    the window of the plan.
    """
    profile = profile_single_no_exog.model_copy(update={"start_date": "2023-01-01"})
    cv = TimeSeriesFold(steps=5, initial_train_size="2023-01-08", verbose=False)

    assert first_window_issue(plan_single_differentiation, cv, profile) == (
        "The first training window of the strategy has 8 observations, and "
        "ForecasterRecursive needs at least 9 (more than its window size, 8), "
        "so skforecast would fail"
    )
