# Unit test warn_interval_residuals

import re

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation import warn_interval_residuals

from .fixtures_recommendation import (
    plan_h2o_interval_baseline,
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


def _message(n_rows, n_train, window_size, features=True):
    advice = ", or fewer lags or smaller window features" if features else ""
    return re.escape(
        f"The first training window of the strategy leaves {n_rows} row(s) to "
        f"train on ({n_train} observations for a window size of "
        f"{window_size}), so the prediction intervals are estimated from "
        f"{n_rows} residual(s). skforecast spreads them over up to 10 bins, "
        f"and below 10 residuals per bin (100 rows) the intervals tend to be "
        f"too narrow; with a single residual in a bin the lower bound equals "
        f"the upper one. Read them with caution, or use a later "
        f"`initial_train_size`{advice}."
    )


@pytest.mark.parametrize(
    "plan, steps, n_train, n_rows, window_size, features",
    [
        (plan_h2o_interval_recursive, 1, 40, 4, 36, True),
        (plan_h2o_interval_recursive, 1, 37, 1, 36, True),
        (plan_h2o_interval_recursive, 1, 135, 99, 36, True),
        (plan_h2o_interval_direct, 3, 40, 2, 36, True),
        (plan_h2o_interval_direct, 3, 137, 99, 36, True),
        (plan_h2o_interval_baseline, 1, 50, 38, 12, False),
        (plan_h2o_interval_baseline, 1, 111, 99, 12, False),
    ],
    ids=[
        "recursive_4_rows",
        "recursive_1_row",
        "recursive_99_rows",
        "direct_2_rows",
        "direct_99_rows",
        "baseline_38_rows",
        "baseline_99_rows",
    ],
)
def test_warn_interval_residuals_UserWarning_when_few_training_rows(
    plan, steps, n_train, n_rows, window_size, features
):
    """
    Test that a plan with bootstrapped (lag forecasters) or conformal
    (baseline) intervals whose first training window leaves 1 to 99 rows
    warns, attributed to the caller of the caller of the helper (the caller
    of `create_cv()`). A direct forecaster loses `steps - 1` more rows, and
    the baseline message does not advise fewer lags.
    """
    warn_msg = _message(n_rows, n_train, window_size, features)
    with pytest.warns(UserWarning, match=warn_msg) as record:
        _create_strategy(plan, _cv(steps, n_train), profile_h2o_complete)

    assert len(record) == 1
    assert record[0].filename == __file__


def test_warn_interval_residuals_UserWarning_when_conformal_lag_forecaster():
    """
    Test that a lag forecaster with conformal intervals warns as with
    bootstrapped ones.
    """
    plan = plan_h2o_interval_recursive.model_copy(
        update={"interval_method": "conformal"}
    )

    with pytest.warns(UserWarning, match=_message(4, 40, 36)):
        _create_strategy(plan, _cv(1, 40), profile_h2o_complete)


@pytest.mark.parametrize(
    "plan, steps, n_train",
    [
        (plan_h2o_interval_recursive, 1, 136),
        (plan_h2o_interval_recursive, 1, 150),
        (plan_h2o_interval_recursive, 1, 36),
        (plan_h2o_interval_recursive, 1, 20),
        (plan_h2o_interval_direct, 3, 138),
        (plan_h2o_interval_direct, 3, 38),
        (plan_h2o_interval_baseline, 1, 112),
        (plan_h2o_interval_baseline, 1, 12),
        (plan_h2o_no_interval, 1, 40),
        (plan_h2o_interval_stats, 1, 40),
    ],
    ids=[
        "100_rows",
        "many_rows",
        "no_rows",
        "window_shorter_than_forecaster",
        "direct_100_rows",
        "direct_no_rows",
        "baseline_100_rows",
        "baseline_no_rows",
        "no_interval",
        "stats",
    ],
)
def test_warn_interval_residuals_no_warning_when_no_case(plan, steps, n_train):
    """
    Test that there is no warning (warnings are errors in this suite) with 100
    rows or more, when the window leaves no rows (`warn_first_window` reports
    it), without interval and for a forecaster with native intervals.
    """
    _create_strategy(plan, _cv(steps, n_train), profile_h2o_complete)


def test_warn_interval_residuals_no_warning_when_strategy_cannot_be_split():
    """
    Test that a strategy that cannot be split on the data returns without
    warning (`build_cv()` reports it).
    """
    _create_strategy(
        plan_h2o_interval_recursive, _cv(1, 500), profile_h2o_complete
    )
