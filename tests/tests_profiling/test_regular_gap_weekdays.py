# Unit test regular_gap_weekdays

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import regular_gap_weekdays

# A year of days from a Monday (2023-01-02 to 2023-12-31), and the days of a
# shop closed on Sundays.
_YEAR = pd.date_range("2023-01-02", periods=364, freq="D")
_NO_SUNDAYS = _YEAR[_YEAR.dayofweek != 6]
_HOURS = pd.date_range("2023-01-02", periods=24 * 28, freq="h")


def _as_nanoseconds(*indexes: pd.DatetimeIndex) -> dict:
    """Return indexes as the dates of the series of long-format data."""
    return {
        f"s{number}": index.as_unit("ns").asi8
        for number, index in enumerate(indexes)
    }


@pytest.mark.parametrize(
    "dates, frequency, expected",
    [
        (_NO_SUNDAYS, "D", [6]),
        (_NO_SUNDAYS.as_unit("s").tz_localize("Europe/Madrid"), "D", [6]),
        (_YEAR[_YEAR.dayofweek != 2], "D", [2]),
        (_YEAR[_YEAR.dayofweek < 5], "D", [5, 6]),
        (_YEAR[_YEAR.dayofweek < 4], "B", [4]),
        (_HOURS[_HOURS.dayofweek != 6], "h", [6]),
        (_as_nanoseconds(_NO_SUNDAYS, _NO_SUNDAYS[:100]), "D", [6]),
        (_as_nanoseconds(_NO_SUNDAYS, _YEAR[_YEAR.dayofweek < 5]), "D", [5, 6]),
        (_as_nanoseconds(_NO_SUNDAYS, _YEAR), "D", [6]),
    ],
    ids=[
        "closed on sundays", "time zone aware", "closed on wednesdays",
        "closed on weekends", "business days closed on fridays",
        "hours closed on sundays", "long format", "shop and office",
        "long format with a series open every day",
    ],
)
def test_regular_gap_weekdays_output_when_gaps_fall_on_closed_days(
    dates, frequency, expected
):
    """
    Test regular_gap_weekdays returns the days of the week of the missing
    timestamps when they all fall on days without any date: Sundays of a
    shop (also time zone aware and in seconds), Wednesdays, weekends of
    daily data, Fridays of business days, Sundays of hourly data, and in
    long format the days missing in each series, from its own range (a
    shop and an office give Saturdays and Sundays; a series open every day
    has no gaps).
    """
    result = regular_gap_weekdays(dates, frequency)
    assert result == expected


@pytest.mark.parametrize(
    "dates, frequency",
    [
        (_YEAR[np.sort(np.random.default_rng(0).choice(364, 300, replace=False))],
         "D"),
        (_NO_SUNDAYS.delete([30, 100]), "D"),
        (_YEAR.delete([10]), "D"),
        (_YEAR, "D"),
        (_YEAR[:10].delete([6]), "D"),
        (_HOURS[(_HOURS.dayofweek != 6) & (_HOURS.hour >= 8)], "h"),
        (pd.date_range("2023-01-01", periods=40, freq="W-SUN").delete([5]), "W-SUN"),
        (_NO_SUNDAYS, None),
        (_as_nanoseconds(_NO_SUNDAYS, _YEAR.delete([10])), "D"),
    ],
    ids=[
        "days missing at random", "sundays and two other days", "one day",
        "no gaps", "one sunday in ten days", "hours closed at night",
        "weekly", "no frequency", "long format with a day missing at random",
    ],
)
def test_regular_gap_weekdays_output_when_gaps_are_not_closed_days(dates, frequency):
    """
    Test regular_gap_weekdays returns an empty list when the gaps are not
    days of the week without any date: days missing at random, Sundays and
    two other days, a single missing day, no gap, a single Sunday in a range
    of ten days (a closed day must come back), hours missing on every day,
    a frequency coarser than a day or none, and long-format data where one
    series misses a day at random.
    """
    result = regular_gap_weekdays(dates, frequency)
    assert result == []
