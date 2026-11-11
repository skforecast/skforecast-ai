# Unit test closed_weekdays

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import closed_weekdays

_YEAR = pd.date_range("2023-01-02", periods=364, freq="D")


@pytest.mark.parametrize(
    "dates, frequency, expected",
    [
        (_YEAR[_YEAR.dayofweek != 6], "D", [6]),
        (_YEAR[_YEAR.dayofweek < 5].delete([3, 40]), "D", [5, 6]),
        (_YEAR[_YEAR.dayofweek < 4], "B", [4]),
        (_YEAR, "D", []),
        (_YEAR[:10].delete([6]), "D", []),
        (_YEAR[_YEAR.dayofweek != 6], "W-MON", []),
        (_YEAR[_YEAR.dayofweek != 6], None, []),
    ],
    ids=[
        "closed on sundays", "weekends and gaps on other days",
        "business days closed on fridays", "open every day",
        "one sunday in ten days", "weekly", "no frequency",
    ],
)
def test_closed_weekdays_output(dates, frequency, expected):
    """
    Test closed_weekdays returns the days of the week without any date when
    the range holds at least two of each, whatever the other gaps: Sundays,
    weekends of daily data with two weekdays also missing, and Fridays of
    business days (whose grid has no weekend). An empty list for data open
    every day, a single Sunday in ten days, or a frequency coarser than a
    day or unknown.
    """
    result = closed_weekdays(dates, frequency)
    assert result == expected
