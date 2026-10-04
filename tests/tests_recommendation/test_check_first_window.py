# Unit test check_first_window

import re

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.recommendation.backtesting import check_first_window

from ..tests_rendering.fixtures_rendering import (
    plan_single_differentiation,
    profile_single_no_exog,
)


def test_check_first_window_InvalidInputError_when_window_too_short():
    """
    Test that a first training window not longer than the window of the
    forecaster raises InvalidInputError with code 'insufficient_data' and
    field 'cv'.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=8, verbose=False)

    err_msg = re.escape(
        "The first training window of the strategy has 8 observations, and "
        "ForecasterRecursive needs at least 9 (more than its window size, 8), "
        "so skforecast would fail. Use a later `initial_train_size`, or a "
        "shorter horizon (`steps`), fewer lags or smaller window features."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        check_first_window(plan_single_differentiation, cv, profile_single_no_exog)

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "cv"


def test_check_first_window_output_when_window_long_enough():
    """
    Test that a first training window longer than the window of the
    forecaster passes.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=9, verbose=False)

    assert check_first_window(
        plan_single_differentiation, cv, profile_single_no_exog
    ) is None
