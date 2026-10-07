# Unit test warn_interval_residuals

import re

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation import warn_interval_residuals

from .fixtures_recommendation import (
    plan_h2o_interval_direct,
    plan_h2o_interval_recursive,
    plan_h2o_interval_stats,
    plan_h2o_no_interval,
    profile_h2o_complete,
)


def _create_strategy(plan, cv, data_profile):
    """Stand in for `create_cv()`, the caller of `warn_interval_residuals`."""
    warn_interval_residuals(plan, cv, data_profile)


def _cv(steps, initial_train_size):
    return TimeSeriesFold(
        steps              = steps,
        initial_train_size = initial_train_size,
        fold_stride        = 1,
        refit              = False,
        verbose            = False,
    )


def _message(n_rows, n_train):
    return re.escape(
        f"The first training window of the strategy leaves {n_rows} row(s) to "
        f"train on ({n_train} observations for a window size of 36), so the "
        f"prediction intervals are bootstrapped from {n_rows} residual(s). "
        f"skforecast spreads them over up to 10 bins, and a bin with a single "
        f"residual gives a lower bound equal to the upper one, with the "
        f"prediction outside: do not read those intervals. Use a later "
        f"`initial_train_size`, or fewer lags or smaller window features."
    )


@pytest.mark.parametrize(
    "plan, steps, n_train, n_rows",
    [
        (plan_h2o_interval_recursive, 1, 40, 4),
        (plan_h2o_interval_recursive, 1, 37, 1),
        (plan_h2o_interval_recursive, 1, 55, 19),
        (plan_h2o_interval_direct, 3, 40, 2),
    ],
    ids=["recursive_4_rows", "recursive_1_row", "recursive_19_rows", "direct_2_rows"],
)
def test_warn_interval_residuals_UserWarning_when_few_training_rows(
    plan, steps, n_train, n_rows
):
    """
    Test that a bootstrapped-interval plan whose first training window leaves
    1 to 19 rows warns, attributed to the caller of the caller of the helper
    (the caller of `create_cv()`). A direct forecaster loses `steps - 1`
    more rows.
    """
    with pytest.warns(UserWarning, match=_message(n_rows, n_train)) as record:
        _create_strategy(plan, _cv(steps, n_train), profile_h2o_complete)

    assert len(record) == 1
    assert record[0].filename == __file__


@pytest.mark.parametrize(
    "plan, steps, n_train",
    [
        (plan_h2o_interval_recursive, 1, 56),
        (plan_h2o_interval_recursive, 1, 100),
        (plan_h2o_interval_recursive, 1, 36),
        (plan_h2o_interval_recursive, 1, 20),
        (plan_h2o_interval_direct, 3, 38),
        (plan_h2o_no_interval, 1, 40),
        (plan_h2o_interval_stats, 1, 40),
    ],
    ids=[
        "20_rows",
        "many_rows",
        "no_rows",
        "window_shorter_than_forecaster",
        "direct_no_rows",
        "no_interval",
        "stats",
    ],
)
def test_warn_interval_residuals_no_warning_when_no_case(plan, steps, n_train):
    """
    Test that there is no warning (warnings are errors in this suite) with 20
    rows or more, when the window leaves no rows (`warn_first_window` reports
    it), without interval and for a forecaster with native intervals.
    """
    _create_strategy(plan, _cv(steps, n_train), profile_h2o_complete)


def test_warn_interval_residuals_no_warning_when_interval_not_bootstrapped():
    """
    Test that there is no warning when the intervals of the plan are not
    bootstrapped (conformal).
    """
    plan = plan_h2o_interval_recursive.model_copy(
        update={"interval_method": "conformal"}
    )

    _create_strategy(plan, _cv(1, 40), profile_h2o_complete)


def test_warn_interval_residuals_no_warning_when_strategy_cannot_be_split():
    """
    Test that a strategy that cannot be split on the data returns without
    warning (`build_cv()` reports it).
    """
    _create_strategy(
        plan_h2o_interval_recursive, _cv(1, 500), profile_h2o_complete
    )
