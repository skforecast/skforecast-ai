# Unit test _has_date_part

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _has_date_part


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2012-01-13 10:00", True),
        ("1/6/20 0:00", True),
        ("06-Jan-20", True),
        ("1991Q3", True),
        (pd.Timestamp("2012-01-13"), True),
        ("09:30", False),
        ("9:30 PM", False),
    ],
    ids=[
        "iso", "two_digit_year", "month_name", "quarter", "timestamp",
        "time_of_day", "time_am_pm",
    ],
)
def test_has_date_part_output(value, expected):
    """
    Test that a value holds a date unless it is only a time of day, also
    with a two-digit year, and that text dateutil cannot read counts as a
    date.
    """
    assert _has_date_part(value) is expected
