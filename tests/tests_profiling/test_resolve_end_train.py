# Unit test resolve_end_train

import re

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
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


def test_resolve_end_train_TypeError_when_unsupported_type():
    """
    Test that a `test_size` of an unsupported type (for example a list)
    raises TypeError naming the accepted types.
    """
    with pytest.raises(TypeError, match="must be an int, float, str or Timestamp, got list"):
        resolve_end_train(
            start_date="2023-01-01", frequency="D", n_observations=100, test_size=[10]
        )


def test_resolve_end_train_InvalidInputError_when_text_is_not_a_date():
    """
    Test that a text `test_size` that is not a date raises with the field
    'test_size' instead of the raw error of pandas.
    """
    err_msg = re.escape(
        "`test_size` is text that is not a date: 'abc'. Pass an integer, a "
        "fraction in (0, 1) or the first date of the test set, such as "
        "'2023-03-01'."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        resolve_end_train(
            start_date=_START, frequency=_FREQ, n_observations=_N, test_size="abc"
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "test_size"


def test_resolve_end_train_InvalidInputError_hint_when_no_frequency():
    """
    Test that the error of a missing datetime index with a known frequency
    carries the field 'test_size' and a hint.
    """
    err_msg = re.escape(
        "`test_size` requires a datetime index with a known frequency. Set the "
        "index frequency (e.g. `data.asfreq(...)`) before forecasting."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        resolve_end_train(
            start_date=_START, frequency=None, n_observations=_N, test_size=20
        )

    assert exc_info.value.field == "test_size"
    assert exc_info.value.hint == (
        "Give the data a datetime index with a regular frequency, or a date "
        "column whose dates follow one."
    )
