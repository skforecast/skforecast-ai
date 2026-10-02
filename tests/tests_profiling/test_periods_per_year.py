# Unit test _periods_per_year

import numpy as np
import pytest

from skforecast_ai.profiling.data_profile import _periods_per_year


@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("h", 8760.0),
        ("bh", 2087.0),
        ("D", 365.0),
        ("B", 260.9),
        ("W-SUN", 52.175),
        ("MS", 12.0),
        ("ME", 12.0),
        ("QS-OCT", 4.0),
        ("5YS-JAN", 0.2),
    ],
    ids=["hour", "business_hour", "day", "business_day", "week", "month_start",
         "month_end", "quarter", "five_years"],
)
def test_periods_per_year_output(frequency, expected):
    """
    Test the number of timestamps of fixed and calendar frequencies in a
    year, counted over forty years for calendar ones (so steps of several
    years count too), which ranks a finer frequency first (month start and
    month end tie).
    """
    assert np.isclose(_periods_per_year(frequency), expected)
