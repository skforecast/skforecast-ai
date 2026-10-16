# Unit test day_month_formats

import pytest

from skforecast_ai._dates import day_month_formats


@pytest.mark.parametrize(
    "date_format, expected",
    [
        ("%d/%m/%Y", ("%m/%d/%Y", "%d/%m/%Y")),
        ("%m/%d/%Y", ("%m/%d/%Y", "%d/%m/%Y")),
        ("%d.%m.%Y", ("%m.%d.%Y", "%d.%m.%Y")),
        ("%m-%d-%Y %H:%M", ("%m-%d-%Y %H:%M", "%d-%m-%Y %H:%M")),
    ],
    ids=["day_first", "month_first", "points", "with_time"],
)
def test_day_month_formats_output(date_format, expected):
    """
    Test that a format that writes the day and the month as numbers before
    the year gives its two orders, month first and then day first, whichever
    order the format has, keeping the separators and the time.
    """
    assert day_month_formats(date_format) == expected


@pytest.mark.parametrize(
    "date_format",
    ["%Y-%m-%d", "%Y/%d/%m", "%d %b %Y", "%B %Y", "%d/%m/%y", None],
    ids=["iso", "year_first_day_before_month", "month_name", "no_day",
         "two_digit_year", "none"],
)
def test_day_month_formats_output_when_order_is_not_in_question(date_format):
    """
    Test that a format whose year comes first (ISO 8601), one with the name
    of the month, one without a day, one with a two digit year (no `%Y`) and
    no format at all give None: their reading has no other order.
    """
    assert day_month_formats(date_format) is None
