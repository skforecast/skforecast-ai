# Unit test detect_gaps

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import (
    count_missing_timestamps,
    detect_gaps,
)


@pytest.mark.parametrize(
    "index, frequency, expected",
    [
        (None, "D", False),
        (pd.date_range("2023-01-01", periods=1, freq="D"), "D", False),
        (pd.date_range("2023-01-01", periods=5, freq="D"), None, False),
        (pd.date_range("2023-01-01", periods=5, freq="D"), "not-a-frequency", False),
        (pd.date_range("2023-01-01", periods=5, freq="D"), "D", False),
        (pd.DatetimeIndex(["2023-01-01", "2023-01-02", "2023-01-04"]), "D", True),
    ],
    ids=["no index", "single row", "no frequency", "invalid frequency", "regular", "gap"],
)
def test_detect_gaps_output(index, frequency, expected):
    """
    Test that gaps are reported only when a frequency is known, the index
    has at least two rows, and timestamps are missing within the range.
    """
    assert detect_gaps(index, frequency) is expected


@pytest.mark.parametrize(
    "index, frequency, expected",
    [
        (None, "D", 0),
        (pd.date_range("2023-01-01", periods=5, freq="D"), None, 0),
        (pd.date_range("2023-01-01", periods=5, freq="D"), "D", 0),
        (pd.DatetimeIndex(["2023-01-01", "2023-01-02", "2023-01-05"]), "D", 2),
    ],
    ids=["no index", "no frequency", "regular", "two missing"],
)
def test_count_missing_timestamps_output(index, frequency, expected):
    """
    Test that the timestamps missing from the regular grid are counted, and
    that the count is 0 when no index or frequency is known.
    """
    assert count_missing_timestamps(index, frequency) == expected
