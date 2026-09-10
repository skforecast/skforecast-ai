# Unit test _check_frequency_is_set

import pandas as pd

from skforecast_ai.profiling.data_profile import _check_frequency_is_set


def test_check_frequency_is_set_output_when_frame_index_has_freq():
    """
    Test that the frame index is consulted when no representative
    datetime index is given.
    """
    data = pd.DataFrame({"y": [1, 2, 3]}, index=pd.date_range("2023-01-01", periods=3, freq="D"))

    assert _check_frequency_is_set(None, data) is True


def test_check_frequency_is_set_output_when_constructed_index_has_no_freq():
    """
    Test that a DatetimeIndex built from a column (never carrying `freq`)
    reports the frequency as not set.
    """
    data = pd.DataFrame({"y": [1, 2, 3]})
    index = pd.DatetimeIndex(["2023-01-01", "2023-01-02", "2023-01-03"])

    assert _check_frequency_is_set(index, data) is False
