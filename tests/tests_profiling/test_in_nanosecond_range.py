# Unit test _in_nanosecond_range

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _in_nanosecond_range


@pytest.mark.parametrize(
    "dates",
    [
        pd.Series(pd.date_range("2020-01-01", periods=3, freq="D")),
        pd.Series(pd.date_range("2020-01-01", periods=3, freq="D", tz="UTC")),
        pd.Series([pd.Timestamp("1677-09-22"), pd.Timestamp("2262-04-11")]),
        pd.Series([], dtype="datetime64[ns]"),
    ],
    ids=["dates", "dates with a time zone", "first and last day", "empty"],
)
def test_in_nanosecond_range_output_is_True_when_dates_in_range(dates):
    """
    Test that dates pandas 2 holds, with or without a time zone, are in the
    range, up to its first and last whole days, and so is a column without
    dates.
    """
    assert _in_nanosecond_range(dates) is True


@pytest.mark.parametrize(
    "dates",
    [
        [pd.Timestamp("0001-01-01"), pd.Timestamp("0001-02-01")],
        [pd.Timestamp("1500-01-01"), pd.Timestamp("2020-01-01")],
        [pd.Timestamp("2020-01-01"), pd.Timestamp("2300-01-01")],
        [pd.Timestamp("0001-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")],
    ],
    ids=["year 1", "before the range", "after the range", "with a time zone"],
)
def test_in_nanosecond_range_output_is_False_when_dates_out_of_range(dates):
    """
    Test that dates before or after those pandas 2 holds (years 1677 to
    2262) are out of the range, as the days of the year 1 pandas 3 reads
    from the names of the months.
    """
    assert _in_nanosecond_range(pd.Series(dates, dtype=object)) is False
