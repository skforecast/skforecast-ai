# Unit test _in_hours

import pytest

from skforecast_ai.profiling.data_profile import _in_hours


@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("D", "24h"),
        ("7D", "168h"),
        ("W-SUN", "168h"),
        ("2W-MON", "336h"),
        ("h", "1h"),
        ("30min", None),
        ("MS", None),
        ("B", None),
        (None, None),
    ],
    ids=["day", "seven_days", "week", "two_weeks", "hour", "half_hour",
         "month_start", "business_day", "none"],
)
def test_in_hours_output(frequency, expected):
    """
    Test that days and weeks are given as a number of hours, and that steps
    that are not whole hours or not fixed (months, business days) give None.
    """
    assert _in_hours(frequency) == expected
