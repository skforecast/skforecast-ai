# Unit test _infer_aware_long_frequency

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import (
    _infer_aware_long_frequency,
    _long_series_dates,
)


def _local_and_utc(dates: pd.DatetimeIndex) -> tuple[dict, dict]:
    """Return the dates of two identical series in local time and in UTC."""
    return _series_local_and_utc({"a": dates, "b": dates})


def _series_local_and_utc(series: dict) -> tuple[dict, dict]:
    """Return the dates of each series in local time and in UTC."""
    dates = pd.DatetimeIndex(np.concatenate([index.asi8 for index in series.values()]))
    dates = dates.tz_localize("UTC").tz_convert("Europe/Madrid")
    ids = pd.Series(np.repeat(list(series), [len(index) for index in series.values()]))
    local = _long_series_dates(dates, ids)
    utc = _long_series_dates(dates.tz_convert("UTC"), ids)
    return local, utc


def test_infer_aware_long_frequency_InvalidInputError_when_fixed_local_hours():
    """
    Test that dates at the same local hours (00:00 and 12:00) across the
    change to summer time raise the error of the UTC reading, which says
    that the timestamps are in UTC, instead of a 12-hour frequency on which
    `asfreq` would drop the rows after the change.
    """
    dates = pd.date_range("2023-03-10", "2023-04-02", freq="12h").tz_localize(
        "Europe/Madrid"
    )

    err_msg = re.escape(
        "2 series, such as 'a', have timestamps off the '12h' grid, for example "
        "2023-03-26 10:00:00. Every series of long-format data must have the "
        "same frequency on the same grid: correct or drop those timestamps, or "
        "forecast those series separately. The timestamps are in UTC: pandas "
        "puts a step shorter than a day on a grid in UTC, so dates at the same "
        "local hours change step across a daylight saving time change."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        _infer_aware_long_frequency(*_local_and_utc(dates))

    assert exc_info.value.field == "data"


@pytest.mark.parametrize(
    "series, err_msg",
    [
        (
            {
                "h0": pd.date_range(
                    "2023-01-01", "2023-06-30 23:00", freq="h", tz="Europe/Madrid"
                ),
                "w": pd.date_range(
                    "2023-01-01", "2023-06-25", freq="W-SUN", tz="Europe/Madrid"
                ),
            },
            "The series do not share one frequency: 'h' (series 'h0'), 'W-SUN' "
            "(series 'w').",
        ),
        (
            {
                **{
                    f"d{i}": pd.date_range(
                        "2023-01-01", "2023-06-30", freq="D", tz="UTC"
                    ).tz_convert("Europe/Madrid")
                    for i in range(3)
                },
                "w": pd.date_range(
                    "2023-01-01", "2023-06-30", freq="W-SUN", tz="UTC"
                ).tz_convert("Europe/Madrid"),
            },
            "The series do not share one frequency: 'D' (series 'd0'), 'W-SUN' "
            "(series 'w'). Every series of long-format data must have the same "
            "frequency; forecast the series of each frequency separately.",
        ),
    ],
    ids=["weekly_among_hourly", "weekly_among_days_at_utc_midnight"],
)
def test_infer_aware_long_frequency_InvalidInputError_when_frequencies_differ(
    series, err_msg
):
    """
    Test that a weekly series at local midnight among hourly ones raises,
    although its steps of 167 to 169 hours in UTC hide it there, and that
    with days and a week at UTC midnight (wrong in local time, where the
    hour moves) the error that blames the fewest dates is raised, without
    the note on UTC.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)):
        _infer_aware_long_frequency(*_series_local_and_utc(series))


@pytest.mark.parametrize(
    "dates, expected",
    [
        (pd.date_range("2023-03-24", "2023-03-28", freq="2h", tz="Europe/Madrid"),
         ("2h", 0)),
        (pd.date_range("2023-03-24", "2023-03-28", freq="12h", tz="Europe/Madrid"),
         ("12h", 0)),
        (pd.date_range("2023-03-20", "2023-04-02", freq="D", tz="Europe/Madrid"),
         ("D", 0)),
        (pd.date_range("2023-03-24", "2023-03-28", freq="12h").tz_localize(
            "Europe/Madrid"), (None, 0)),
        (pd.date_range("2023-01-01", "2023-06-30", freq="D", tz="UTC").tz_convert(
            "Europe/Madrid"), ("24h", 0)),
        (pd.date_range("2023-01-01", "2023-06-30", freq="W-SUN", tz="UTC").tz_convert(
            "Europe/Madrid"), ("168h", 0)),
    ],
    ids=["two_hours", "twelve_hours", "days", "short_fixed_local_hours",
         "days_at_utc_midnight", "weeks_at_utc_midnight"],
)
def test_infer_aware_long_frequency_output(dates, expected):
    """
    Test that time zone aware dates across the change to summer time are
    read in UTC for steps shorter than a day (2 and 12 hours, as pandas
    makes them, with no missing timestamp) and in local time for days
    (midnight every day), that a few dates at the same local hours (regular
    in local time only, too few to raise in UTC) have no frequency, as
    `asfreq` would put them on a grid in UTC, and that days and
    weeks at the same UTC hour (01:00 then 02:00 in local time) are given
    in hours, which pandas keeps in UTC.
    """
    assert _infer_aware_long_frequency(*_local_and_utc(dates)) == expected


def test_infer_aware_long_frequency_output_when_no_utc_dates_or_too_few():
    """
    Test that without dates in UTC (beyond the range of nanoseconds) the
    local reading decides, and that two dates per series, too few for any
    reading, have no frequency.
    """
    daily = pd.date_range("2023-01-01", periods=40).asi8
    two = pd.DatetimeIndex(["2023-01-01", "2023-01-05"]).asi8

    assert _infer_aware_long_frequency({"a": daily}, None) == ("D", 0)
    assert _infer_aware_long_frequency({"a": two}, {"a": two}) == (None, 0)
