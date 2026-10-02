# Unit test _is_clearly_date

import datetime

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _is_clearly_date


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2012-01-13", True),
        ("13/01/2012", True),
        ("01/13/2012 10:00 PM", True),
        ("1991-07", True),
        ("2012.01.13", True),
        ("Sat, 28 Mar 2020 01:00:00 +0100 (CET)", True),
        (pd.Timestamp("2012-01-13"), True),
        (datetime.date(2012, 1, 13), True),
        ("09:30", False),
        ("01:30 hrs", False),
        ("4.17.21", False),
        ("2019/1", False),
        ("1990", False),
        ("1/6/20 0:00", False),
        (2012, False),
    ],
    ids=[
        "iso", "day_first", "am_pm", "year_month", "dotted", "rfc_2822",
        "timestamp", "date", "time_of_day", "duration", "version", "code",
        "year", "two_digit_year", "number",
    ],
)
def test_is_clearly_date_output(value, expected):
    """
    Test that a value is clearly a date when it is a date object or text
    with a day or month and a year of four digits, and not when it is a
    time of day, a duration, a code, a year alone, a version number, a date
    with a two-digit year or a number.
    """
    assert _is_clearly_date(value) is expected
