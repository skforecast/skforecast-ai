# Unit test short_year_format

import pytest

from skforecast_ai._dates import short_year_format


@pytest.mark.parametrize(
    "value, expected",
    [
        ("01/02/18", "%m/%d/%y"),
        ("1.2.18", "%m.%d.%y"),
        ("13-01-18", "%m-%d-%y"),
        (" 01/02/18 ", "%m/%d/%y"),
        ("01/02/18 10:30", "%m/%d/%y %H:%M"),
        ("01/02/18 10:30:15", "%m/%d/%y %H:%M:%S"),
        ("01/02/18T10:30", "%m/%d/%yT%H:%M"),
    ],
    ids=[
        "slashes", "points", "dashes", "spaces around", "with time",
        "with seconds", "T before time",
    ],
)
def test_short_year_format_output(value, expected):
    """
    Test that a date with the day and the month before a year of two digits
    gives its format with the month first, keeping the separator and the
    time.
    """
    assert short_year_format(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "01/02/2018", "2018-01-02", "18-01-02x", "01/02-18", "1/2/3",
        "4.17.21.1", 20180102, None,
    ],
    ids=[
        "four digit year", "iso", "trailing text", "two separators",
        "one digit year", "four parts", "integer", "none",
    ],
)
def test_short_year_format_output_when_not_a_short_year_date(value):
    """
    Test that values that are not a date with a year of two digits after
    the day and the month give None.
    """
    assert short_year_format(value) is None
