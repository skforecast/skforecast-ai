# Unit test _finer_than_a_day

import pytest

from skforecast_ai.profiling.data_profile import _finer_than_a_day


@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("30min", True),
        ("h", True),
        ("12h", True),
        ("D", False),
        ("2D", False),
        ("bh", False),
        ("B", False),
        ("MS", False),
        (None, False),
    ],
    ids=["half_hour", "hour", "half_day", "day", "two_days", "business_hour",
         "business_day", "month_start", "none"],
)
def test_finer_than_a_day_output(frequency, expected):
    """
    Test that only a fixed step shorter than a day counts as finer than a
    day: business hours follow the calendar, as days and months do.
    """
    assert _finer_than_a_day(frequency) is expected
