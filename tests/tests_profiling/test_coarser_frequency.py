# Unit test _coarser_frequency

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import (
    _COARSER_EVIDENCE,
    _coarser_frequency,
)

_WEEKLY = pd.date_range("2023-01-01", periods=30, freq="W-SUN")
# 60 Sundays and one Monday after the first 30 dates.
_WEEKS_AND_MONDAY = pd.date_range("2023-01-01", periods=60, freq="W-SUN")
_WEEKS_AND_MONDAY = _WEEKS_AND_MONDAY.insert(
    40, _WEEKS_AND_MONDAY[39] + pd.Timedelta(days=1)
)


def _sparse(steps: list[int]) -> pd.DatetimeIndex:
    """Return dates from 2023-01-01 separated by `steps` days."""
    days = np.cumsum([0] + steps)
    return pd.Timestamp("2023-01-01") + pd.to_timedelta(days, unit="D")


@pytest.mark.parametrize(
    "dates, own_frequency, expected",
    [
        (pd.date_range("2023-01-01", periods=40), None, None),
        (_WEEKLY[:9], None, None),
        (_WEEKLY, "W-SUN", "W-SUN"),
        (_WEEKLY.delete([10]), None, "W-SUN"),
        (_WEEKLY[[0, 1, 2, 4, 5, 7, 8, 10, 11, 13, 14, 16]], None, "W-SUN"),
        (_sparse([2, 4, 2, 6, 2, 4, 8, 2, 2, 4, 2]), None, None),
        (_sparse([2, 4, 6, 2, 4, 6, 8, 2, 4, 6, 2, 8, 4, 2, 6, 4, 2, 8, 6, 2, 4]),
         None, "2D"),
        (pd.date_range("2020-01-01", "2021-12-01", freq="MS").delete([4, 11, 17]),
         None, "MS"),
        (pd.date_range("2020-01-31", "2021-12-31", freq="ME").delete([4, 11, 17]),
         None, "ME"),
        (_WEEKS_AND_MONDAY, "W-SUN", "W-SUN"),
        (pd.date_range("2016-01-01", periods=30, freq="QS-JAN").delete([3]),
         None, "QS-OCT"),
    ],
    ids=["consecutive_days", "short", "own_frequency", "inferred_with_gaps",
         "steps_of_whole_weeks", "few_even_steps", "many_even_steps",
         "month_starts_with_gaps", "month_ends_with_gaps",
         "own_frequency_and_stray_day", "quarters_with_gaps"],
)
def test_coarser_frequency_output(dates, own_frequency, expected):
    """
    Test the coarser frequency of a single series on a daily grid: none
    with two consecutive days or fewer than 10 dates, its own frequency
    (also with a stray day after a Sunday later on), month starts or month
    ends with gaps (quarters named as quarters), or the step all its steps
    are multiples of (whole weeks, named as weeks; even steps only from 21
    dates, as fewer even steps may be chance).
    """
    offset = pd.tseries.frequencies.to_offset("D")
    positions = (dates.asi8 - dates.asi8[0]) // offset.nanos

    result = _coarser_frequency(
        dates         = dates.asi8,
        positions     = positions,
        own_frequency = own_frequency,
        offset        = offset,
        frequency     = "D",
        evidence      = _COARSER_EVIDENCE,
    )

    assert result == expected
