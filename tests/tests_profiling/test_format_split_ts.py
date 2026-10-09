# Unit test _format_split_ts

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _format_split_ts


@pytest.mark.parametrize(
    "ts, expected",
    [
        (pd.Timestamp("2023-03-01"), "2023-03-01"),
        (pd.Timestamp("2023-03-01 23:00:00"), "2023-03-01 23:00:00"),
    ],
    ids=["midnight: date only", "with time: full timestamp"],
)
def test_format_split_ts_output(ts, expected):
    """
    Test that a midnight boundary is rendered as a date and any other
    boundary as a full timestamp.
    """
    assert _format_split_ts(ts) == expected


@pytest.mark.parametrize(
    "ts, expected",
    [
        (pd.Timestamp("2023-06-02"), "2023-06-02 00:00:00"),
        (pd.Timestamp("2023-06-02", tz="Europe/Madrid"), "2023-06-02 00:00:00+02:00"),
        (pd.Timestamp("2023-06-02 05:00:00"), "2023-06-02 05:00:00"),
    ],
    ids=["midnight", "midnight with time zone", "with time"],
)
def test_format_split_ts_output_when_with_time(ts, expected):
    """
    Test that with `with_time=True` (sub-daily data) the time is written also
    at midnight, with the time zone of a tz-aware timestamp.
    """
    assert _format_split_ts(ts, with_time=True) == expected
