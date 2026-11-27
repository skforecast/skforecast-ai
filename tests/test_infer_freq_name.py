# Unit test infer_freq_name

import re

import pandas as pd
import pytest

from skforecast_ai._dates import infer_freq_name


@pytest.mark.parametrize(
    "frequency",
    ["D", "h", "15min", "W-SUN", "MS", "ME", "YS-JAN", "B"],
    ids=lambda frequency: f"{frequency}",
)
def test_infer_freq_name_output(frequency):
    """
    Test that the frequency is its name, as `pandas.infer_freq` gives it,
    without the warning of pandas 3.1 that a future version returns the
    offset (warnings are errors in the suite).
    """
    index = pd.date_range("2020-01-01", periods=10, freq=frequency)

    assert infer_freq_name(index) == frequency


def test_infer_freq_name_output_is_None_when_no_frequency():
    """
    Test that dates without a regular step have no frequency.
    """
    index = pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-05"])

    assert infer_freq_name(index) is None


def test_infer_freq_name_ValueError_when_fewer_than_three_dates():
    """
    Test that fewer than three dates raise the error of `pandas.infer_freq`.
    """
    index = pd.DatetimeIndex(["2020-01-01", "2020-01-02"])

    err_msg = re.escape("Need at least 3 dates to infer frequency")
    with pytest.raises(ValueError, match=err_msg):
        infer_freq_name(index)
