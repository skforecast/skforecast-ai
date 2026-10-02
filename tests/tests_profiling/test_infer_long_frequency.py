# Unit test _infer_long_frequency

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import _infer_long_frequency


def _as_nanoseconds(series_dates: dict) -> dict:
    """Return the dates of each series as nanoseconds since the epoch."""
    return {name: pd.DatetimeIndex(dates).asi8 for name, dates in series_dates.items()}


_DAILY = pd.date_range("2023-01-01", periods=21, freq="D")
_BUSINESS = pd.date_range("2023-01-02", periods=15, freq="B")
_WEEKLY = pd.date_range("2023-01-01", periods=10, freq="W-SUN")
_HOURLY = pd.date_range("2023-01-01", periods=48, freq="h")
_BUSINESS_HOURS = pd.date_range("2023-01-02 09:00", periods=40, freq="bh")
# 59 business days with a holiday, 40 days, and 80 business days.
_BUSINESS_HOLIDAY = pd.bdate_range("2023-01-02", periods=60).delete(30)
_DAILY_40 = pd.date_range("2023-03-01", periods=40, freq="D")
_BUSINESS_80 = pd.bdate_range("2023-01-02", periods=80)
# Two days out of five over 497 days: no window of 10 dates is regular.
_SPARSE = pd.date_range("2020-01-01", periods=500, freq="D")[
    np.sort(np.r_[0:500:5, 1:500:5])
]
# 104 Sundays and one Monday.
_WEEKS_AND_MONDAY = pd.date_range("2020-01-05", periods=104, freq="W-SUN")
_WEEKS_AND_MONDAY = _WEEKS_AND_MONDAY.insert(
    50, _WEEKS_AND_MONDAY[49] + pd.Timedelta(days=1)
)
# A shop open from Monday to Saturday over 13 weeks.
_MON_SAT = pd.date_range("2023-01-02", "2023-03-31", freq="D")
_MON_SAT = _MON_SAT[_MON_SAT.dayofweek != 6]
# 11 series of two days out of five, each on other days, so that only the
# dates of every series together give the frequency.
_MANY_SPARSE = {
    f"s{k}": pd.date_range("2020-01-01", periods=200, freq="D")[
        np.sort(np.r_[k % 5:200:5, (k + 1) % 5:200:5])
    ]
    for k in range(11)
}


@pytest.mark.parametrize(
    "series_dates, err_msg",
    [
        (
            {"a": _DAILY, "b": _WEEKLY},
            "The series do not share one frequency: 'D' (series 'a'), 'W-SUN' "
            "(series 'b').",
        ),
        (
            {"b": _WEEKLY, "a": _DAILY},
            "The series do not share one frequency: 'D' (series 'a'), 'W-SUN' "
            "(series 'b').",
        ),
        (
            {
                "a": pd.date_range("2023-01-01", periods=12, freq="MS"),
                "b": pd.date_range("2023-01-31", periods=12, freq="ME"),
            },
            "The series do not share one frequency: 'ME' (series 'b'), 'MS' "
            "(series 'a').",
        ),
        (
            {"a": _DAILY, "b": _DAILY[::2]},
            "The series do not share one frequency: 'D' (series 'a'), '2D' "
            "(series 'b').",
        ),
        (
            {
                "w": pd.date_range("2023-01-01", periods=60, freq="W-SUN"),
                **{
                    f"d{i}": pd.date_range("2023-01-01", periods=60).delete([3, 7])
                    for i in range(5)
                },
            },
            "The series do not share one frequency: 'D' (series 'd0'), 'W-SUN' "
            "(series 'w').",
        ),
        (
            {
                "b1": pd.bdate_range("2023-01-02", periods=300),
                "b2": pd.bdate_range("2023-01-02", periods=300),
                "w": pd.date_range("2023-01-02", periods=60, freq="W-MON")[
                    [i for i in range(60) if i % 3 != 2]
                ],
            },
            "The series do not share one frequency: 'B' (series 'b1'), 'W-MON' "
            "(series 'w').",
        ),
        (
            {
                "a": pd.date_range("2020-01-01", "2021-12-31"),
                "m": pd.date_range("2020-01-01", "2021-12-01", freq="MS").delete(
                    [4, 11, 17]
                ),
            },
            "The series do not share one frequency: 'D' (series 'a'), 'MS' "
            "(series 'm').",
        ),
        (
            {
                "a": pd.date_range("2020-01-01", "2021-12-31"),
                "w": _WEEKS_AND_MONDAY,
            },
            "The series do not share one frequency: 'D' (series 'a'), 'W-SUN' "
            "(series 'w').",
        ),
    ],
    ids=[
        "weekly_after_daily", "weekly_first", "month_start_and_end",
        "alternate_days", "longer_weekly_among_daily_with_gaps",
        "weeks_with_gaps_among_business_days", "months_with_gaps_among_daily",
        "weekly_with_stray_monday_among_daily",
    ],
)
def test_infer_long_frequency_InvalidInputError_when_frequencies_differ(
    series_dates, err_msg
):
    """
    Test that series of a coarser frequency (weekly among daily, every
    other day among daily, weeks with gaps among business days, told by
    steps that are all multiples of five business days and named as weeks)
    or on another grid of the same period (month start and month end)
    raise, in any order of the series, naming the series of another
    frequency also when it is the longest one; months with gaps among days,
    and weeks with a stray Monday among days, raise too.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)):
        _infer_long_frequency(_as_nanoseconds(series_dates))


@pytest.mark.parametrize(
    "series_dates, err_msg",
    [
        (
            {"a": _DAILY, "b": _DAILY.insert(5, pd.Timestamp("2023-01-05 12:00"))},
            "Series 'b' has timestamps off the 'D' grid, "
            "for example 2023-01-05 12:00:00.",
        ),
        (
            {"a": _DAILY, "b": _DAILY + pd.Timedelta("12h")},
            "Series 'b' has timestamps off the 'D' grid, "
            "for example 2023-01-01 12:00:00.",
        ),
        (
            {
                "a": _DAILY,
                "b": pd.DatetimeIndex(["2023-01-01", "2023-01-01 06:00"]),
                "c": pd.DatetimeIndex(["2023-01-02 01:00", "2023-01-02 07:00"]),
            },
            "2 series, such as 'b', have timestamps off the 'D' grid, "
            "for example 2023-01-01 06:00:00.",
        ),
        (
            {
                "a": pd.date_range("2023-01-01", periods=12, freq="MS"),
                "b": pd.DatetimeIndex(["2023-01-15", "2023-02-01", "2023-03-01"]),
            },
            "Series 'b' has timestamps off the 'MS' grid, "
            "for example 2023-01-15.",
        ),
        (
            {
                "a": _HOURLY,
                "b": _HOURLY,
                "c": pd.date_range("2022-12-31 00:30", periods=80, freq="h"),
            },
            "Series 'c' has timestamps off the 'h' grid, "
            "for example 2022-12-31 00:30:00.",
        ),
        (
            {
                "short": pd.date_range("2020-01-05", periods=12, freq="2W-SUN"),
                "long": pd.date_range("2020-01-12", periods=100, freq="2W-SUN"),
                "long2": pd.date_range("2020-01-12", periods=100, freq="2W-SUN"),
            },
            "Series 'short' has timestamps off the '2W-SUN' grid, "
            "for example 2020-01-05.",
        ),
        (
            {"shop": _MON_SAT, "office": _MON_SAT[_MON_SAT.dayofweek < 5]},
            "Series 'shop' has timestamps off the 'B' grid, "
            "for example 2023-01-07.",
        ),
        (
            {"office": _MON_SAT[_MON_SAT.dayofweek < 5], "shop": _MON_SAT},
            "Series 'shop' has timestamps off the 'B' grid, "
            "for example 2023-01-07.",
        ),
        (
            {
                **{
                    f"b{i}": pd.bdate_range("2020-01-01", periods=250)
                    for i in range(3)
                },
                "odd": pd.bdate_range("2020-01-01", periods=250).insert(
                    112, pd.Timestamp("2020-06-06")
                ),
            },
            "Series 'odd' has timestamps off the 'B' grid, "
            "for example 2020-06-06.",
        ),
    ],
    ids=[
        "extra_timestamp", "shifted_series", "short_series", "mid_month_start",
        "longest_series_shifted", "every_second_week_on_other_weeks",
        "monday_to_saturday_and_business_days",
        "business_days_and_monday_to_saturday", "saturday_in_business_days",
    ],
)
def test_infer_long_frequency_InvalidInputError_when_timestamps_off_grid(
    series_dates, err_msg
):
    """
    Test that timestamps off the grid of the shared frequency, at the phase
    of most dates, raise and name the series off it: an extra timestamp, a
    series shifted by half a day, short series, a series starting in the
    middle of a month, a shifted series longer than the others, a short
    series every second week on the other weeks, a shop open on Saturdays
    next to an office open on business days (in either order), and one
    Saturday in a series of business days, which is not taken for daily
    data.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)):
        _infer_long_frequency(_as_nanoseconds(series_dates))


@pytest.mark.parametrize(
    "series_dates, expected",
    [
        ({"a": _DAILY, "b": _DAILY}, ("D", 0)),
        ({"a": _DAILY, "b": _DAILY.delete([2, 3])}, ("D", 2)),
        ({"a": _DAILY.delete([5]), "b": _DAILY.delete([5]), "c": _DAILY}, ("D", 2)),
        ({"a": _DAILY[:2], "b": _DAILY}, ("D", 0)),
        ({"a": _DAILY[10:], "b": _DAILY[:15]}, ("D", 0)),
        ({"a": _DAILY, "b": _BUSINESS}, ("D", 4)),
        ({"a": _BUSINESS, "b": _DAILY}, ("D", 4)),
        ({"a": _BUSINESS, "b": _BUSINESS, "c": _BUSINESS[1:5]}, ("B", 0)),
        ({"a": _DAILY[[0, 2, 3, 7, 8]], "b": _DAILY[[1, 4, 9]]}, (None, 0)),
        ({"a": _BUSINESS_HOURS, "b": _BUSINESS_HOURS}, ("bh", 0)),
        ({"a": _DAILY, "b": _WEEKLY[:3]}, ("D", 12)),
        (
            {"a": _DAILY.delete([3]), "b": _DAILY.delete([12]), "c": _WEEKLY[:3]},
            ("D", 14),
        ),
        ({"a": _DAILY, "b": _DAILY[[0, 4, 8, 20]]}, ("D", 17)),
        (
            {
                "a": _BUSINESS_HOLIDAY,
                "b": _BUSINESS_HOLIDAY,
                "c": pd.date_range("2023-01-10", periods=4, freq="D"),
            },
            ("B", 2),
        ),
        ({"a": _DAILY_40.delete([5]), "b": _BUSINESS_80}, ("D", 31)),
        ({"b": _BUSINESS_80, "a": _DAILY_40.delete([5])}, ("D", 31)),
        ({"a": _DAILY_40.delete([5]), "b": _BUSINESS_80.delete([40])}, ("D", 32)),
        (
            {
                "a": _DAILY_40.delete([30]),
                "b": _DAILY_40.delete([30]),
                "c": pd.bdate_range("2023-03-01", "2023-04-09"),
            },
            ("D", 12),
        ),
        ({"a": _DAILY_40.delete([5]), "b": _SPARSE}, ("D", 298)),
        (_MANY_SPARSE, ("D", 1293)),
        (
            {
                "a": pd.bdate_range("2023-01-02", periods=40).append(
                    pd.date_range("2023-03-01", periods=200, freq="D")
                ),
            },
            ("D", 18),
        ),
        (
            {
                "a": pd.date_range("2020-01-01", periods=30, freq="D").append(
                    pd.date_range("2020-02-02", periods=20, freq="W-SUN")
                ),
            },
            (None, 0),
        ),
        (
            {
                "a": pd.date_range("2021-01-01", periods=30, freq="2h").append(
                    pd.date_range("2021-01-04", periods=300, freq="h")
                ),
            },
            ("h", 42),
        ),
    ],
    ids=[
        "same", "gaps_summed", "same_gap_in_every_series", "short_series_on_grid",
        "staggered", "business_days_after_daily", "business_days_first",
        "short_business_series", "none_inferred",
        "business_hours", "short_weekly_series",
        "short_weekly_series_among_daily_with_gaps", "sparse_short_series",
        "business_days_with_holidays_and_short_series",
        "daily_with_gaps_and_longer_business_days", "longer_business_days_first",
        "daily_with_gaps_and_business_days_with_holidays",
        "daily_with_gaps_and_lone_business_series", "sparse_longest_series",
        "many_sparse_series", "business_days_then_daily", "daily_then_weekly",
        "every_two_hours_then_hourly",
    ],
)
def test_infer_long_frequency_output(series_dates, expected):
    """
    Test the shared frequency and the missing timestamps counted within the
    range of each series and summed: the frequency of most dates wins, the
    finer one on a tie whatever the order, and a series on its grid with
    dates one step apart (business days among daily ones) counts as gaps,
    as does a series with fewer than 10 dates, which does not tell a
    frequency of its own (three dates a week apart). Business hours keep
    their grid, business days with holidays stay business days next to a
    short series of four days, daily series with gaps stay daily next to
    longer or regular business-day series, and the frequency comes from the
    next series with gaps when the longest one is too sparse to give it, or
    from the dates of every series when none of the 10 longest gives it. A
    series of business days then daily dates, or of dates every two hours
    then hourly, is of the finer frequency with gaps, and a series of daily
    then weekly dates has no frequency (its first dates do not hold for the
    rest, as for a single series).
    """
    assert _infer_long_frequency(_as_nanoseconds(series_dates)) == expected


def test_infer_long_frequency_output_when_no_series():
    """
    Test that data without series has no frequency and no missing
    timestamps.
    """
    assert _infer_long_frequency({}) == (None, 0)
