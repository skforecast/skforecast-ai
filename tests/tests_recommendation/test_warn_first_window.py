# Unit test warn_first_window

import re

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation.backtesting import warn_first_window

from ..tests_rendering.fixtures_rendering import (
    plan_single_differentiation,
    profile_single_no_exog,
)


def _create_strategy(plan, cv, data_profile):
    """Stand in for `create_cv()`, the caller of `warn_first_window`."""
    warn_first_window(plan, cv, data_profile)


def test_warn_first_window_UserWarning_when_window_too_short():
    """
    Test that a strategy whose first training window is not longer than the
    window of the forecaster warns that its backtest raises, attributed to
    the caller of the caller of the helper (the caller of `create_cv()`).
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=8, verbose=False)

    warn_msg = re.escape(
        "The first training window of the strategy has 8 observations, and "
        "ForecasterRecursive needs at least 9 (more than its window size, 8), "
        "so skforecast would fail: `backtest()` of this plan with this "
        "strategy raises. The strategy can still serve the candidates of "
        "`compare()` with a smaller window; use a later `initial_train_size`, "
        "or a shorter horizon, to backtest this plan."
    )
    with pytest.warns(UserWarning, match=warn_msg) as record:
        _create_strategy(plan_single_differentiation, cv, profile_single_no_exog)

    assert record[0].filename == __file__


def test_warn_first_window_no_warning_when_window_long_enough():
    """
    Test that there is no warning when the first training window is longer
    than the window of the forecaster (warnings are errors in this suite).
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=9, verbose=False)

    _create_strategy(plan_single_differentiation, cv, profile_single_no_exog)
