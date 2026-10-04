# Unit test count_missing_timestamps

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import count_missing_timestamps


@pytest.mark.parametrize(
    "index, frequency, expected",
    [
        (None, "D", 0),
        (pd.date_range("2023-01-01", periods=1, freq="D"), "D", 0),
        (pd.date_range("2023-01-01", periods=5, freq="D"), None, 0),
        (pd.date_range("2023-01-01", periods=5, freq="D"), "not-a-frequency", 0),
        (pd.date_range("2023-01-01", periods=5, freq="D"), "D", 0),
        (pd.DatetimeIndex(["2023-01-01", "2023-01-02", "2023-01-05"]), "D", 2),
    ],
    ids=[
        "no index", "single row", "no frequency", "invalid frequency", "regular",
        "two missing",
    ],
)
def test_count_missing_timestamps_output(index, frequency, expected):
    """
    Test that the timestamps missing from the regular grid are counted, and
    that the count is 0 without an index, with a single row, and without a
    valid frequency.
    """
    assert count_missing_timestamps(index, frequency) == expected
