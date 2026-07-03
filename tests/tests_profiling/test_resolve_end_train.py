# Unit test resolve_end_train

import pandas as pd
import pytest

from skforecast_ai.profiling import resolve_end_train


# Reference daily index: 100 observations starting 2023-01-01
_N = 100
_START = "2023-01-01"
_FREQ = "D"
_INDEX = pd.date_range(_START, periods=_N, freq=_FREQ)


# =============================================================================
# Tests: valid resolutions
# =============================================================================
def test_resolve_end_train_output_when_int():
    """
    Test that an integer test_size marks the last N observations as test:
    end_train is the observation just before the final N.
    """
    end_train = resolve_end_train(
        start_date=_START, frequency=_FREQ, n_observations=_N, test_size=20
    )

    assert end_train == str(_INDEX[_N - 20 - 1].date())


def test_resolve_end_train_output_when_float():
    """
    Test that a float test_size marks the last fraction as test.
    """
    end_train = resolve_end_train(
        start_date=_START, frequency=_FREQ, n_observations=_N, test_size=0.2
    )

    assert end_train == str(_INDEX[_N - 20 - 1].date())


def test_resolve_end_train_output_when_date_string():
    """
    Test that a date-string test_size (the first test timestamp) resolves
    end_train to the last training timestamp strictly before it.
    """
    test_start = _INDEX[80]
    end_train = resolve_end_train(
        start_date=_START,
        frequency=_FREQ,
        n_observations=_N,
        test_size=str(test_start.date()),
    )

    assert end_train == str(_INDEX[79].date())


def test_resolve_end_train_output_when_timestamp():
    """
    Test that a pandas Timestamp test_size behaves like a date string.
    """
    test_start = _INDEX[80]
    end_train = resolve_end_train(
        start_date=_START,
        frequency=_FREQ,
        n_observations=_N,
        test_size=test_start,
    )

    assert end_train == str(_INDEX[79].date())


# =============================================================================
# Tests: invalid inputs
# =============================================================================
def test_resolve_end_train_ValueError_when_int_out_of_range():
    """
    Test that an integer test_size not strictly smaller than the number of
    observations raises ValueError.
    """
    with pytest.raises(ValueError, match="Integer .test_size."):
        resolve_end_train(
            start_date=_START, frequency=_FREQ, n_observations=_N, test_size=1000
        )


def test_resolve_end_train_ValueError_when_float_out_of_range():
    """
    Test that a float test_size outside the open interval (0, 1) raises
    ValueError.
    """
    with pytest.raises(ValueError, match="Float .test_size."):
        resolve_end_train(
            start_date=_START, frequency=_FREQ, n_observations=_N, test_size=1.5
        )


def test_resolve_end_train_ValueError_when_date_outside_range():
    """
    Test that a date-string test_size outside the data range raises
    ValueError.
    """
    with pytest.raises(ValueError, match="Timestamp .test_size."):
        resolve_end_train(
            start_date=_START,
            frequency=_FREQ,
            n_observations=_N,
            test_size="2050-01-01",
        )


def test_resolve_end_train_TypeError_when_bool():
    """
    Test that a bool test_size is rejected (bool is a subclass of int).
    """
    with pytest.raises(TypeError, match="test_size"):
        resolve_end_train(
            start_date=_START, frequency=_FREQ, n_observations=_N, test_size=True
        )


def test_resolve_end_train_ValueError_when_no_frequency():
    """
    Test that resolution requires a datetime index with a known frequency.
    """
    with pytest.raises(ValueError, match="requires a datetime index"):
        resolve_end_train(
            start_date=_START, frequency=None, n_observations=_N, test_size=20
        )
