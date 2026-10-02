# Unit test _missing_read

import numpy as np
import pytest

from skforecast_ai._last_window import _missing_read

from tests.fixtures_last_window import plan_single_baseline, plan_single_ridge


def _window(missing: list[int], length: int = 10) -> np.ndarray:
    """Return a window of `length` values, missing at `missing` (1 is the last)."""
    return np.isin(np.arange(1, length + 1), missing)


@pytest.mark.parametrize(
    "missing, expected",
    [([], []), ([2], []), ([2, 4, 9], [4]), ([3, 4, 5], [3, 4, 5])],
    ids=["none", "not_read", "one_read", "all_read"],
)
def test_missing_read_output(missing, expected):
    """
    Test that the missing values returned are those at the positions read:
    the lags of `plan_single_ridge` read positions 1, 3, 4 and 5, and its
    rolling mean of 3 skips missing values unless all 3 are missing.
    """
    positions = np.array([1, 3, 4, 5])

    result = _missing_read(
        _window(missing), positions, 0, plan_single_ridge, inverse=True
    )

    assert result == (expected, False)


def test_missing_read_output_when_window_feature_values_all_missing():
    """
    Test that a rolling statistic whose differenced values are all missing
    reads them: with order 1, a missing value at position 2 makes the
    differenced values 1 and 2 missing, which a rolling mean of 2 reads.
    """
    plan = plan_single_ridge.model_copy(update={"forecaster_kwargs": {
        "lags": [5],
        "window_features": [{"stats": ["mean"], "window_size": 2}],
        "differentiation": 1,
    }})

    result = _missing_read(_window([2]), np.array([1, 5, 6]), 1, plan, inverse=True)

    assert result == ([2], False)


def test_missing_read_output_when_window_shorter_than_positions():
    """
    Test that positions beyond the values of the series (a short series)
    are not read as missing.
    """
    result = _missing_read(
        _window([2], length=3), np.array([2, 7]), 0, plan_single_ridge,
        inverse=True,
    )

    assert result == ([2], False)


def test_missing_read_output_when_baseline():
    """
    Test that ForecasterEquivalentDate reads only its equivalent dates, with
    no window features.
    """
    result = _missing_read(
        _window([1, 6]), np.array([5, 6, 7]), 0, plan_single_baseline,
        inverse=True,
    )

    assert result == ([6], False)


@pytest.mark.parametrize(
    "inverse, expected", [(True, ([2], True)), (False, ([], False))],
    ids=["predicted", "not_predicted"],
)
def test_missing_read_output_when_differentiation_inverse(inverse, expected):
    """
    Test that the inverse of the differentiation reads the last `order`
    values of a series it predicts (`inverse`), and not of the other series
    of ForecasterDirectMultiVariate, whose lags (3) do not read position 2.
    """
    plan = plan_single_ridge.model_copy(update={"forecaster_kwargs": {
        "lags": [3], "differentiation": 2,
    }})

    result = _missing_read(_window([2]), np.array([3, 4, 5]), 2, plan, inverse=inverse)

    assert result == expected


def test_missing_read_output_when_window_feature_longer_than_window():
    """
    Test that a window feature longer than the values given (a short
    series) neither fails nor reads them as all missing.
    """
    plan = plan_single_ridge.model_copy(update={"forecaster_kwargs": {
        "lags": [2],
        "window_features": [{"stats": ["mean"], "window_size": 3}],
        "differentiation": 1,
    }})

    result = _missing_read(
        _window([2, 3], length=3), np.array([1, 2, 3]), 1, plan, inverse=True
    )

    assert result == ([2, 3], False)
