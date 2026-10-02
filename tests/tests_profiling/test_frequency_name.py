# Unit test _frequency_name

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _frequency_name

_to_offset = pd.tseries.frequencies.to_offset


@pytest.mark.parametrize(
    "start, offset, expected",
    [
        ("2023-01-02", _to_offset("B") * 5, "W-MON"),
        ("2023-01-01", _to_offset("h") * 24, "D"),
        ("2023-01-01", _to_offset("D") * 2, "2D"),
        ("2020-01-01", _to_offset("MS") * 3, "QS-OCT"),
        ("2020-01-01", _to_offset("MS") * 12, "YS-JAN"),
    ],
    ids=["five_business_days", "twenty_four_hours", "two_days", "three_months",
         "twelve_months"],
)
def test_frequency_name_output(start, offset, expected):
    """
    Test that a multiple of a frequency gets the name pandas gives to its
    dates: weeks for five business days, a day for 24 hours, quarters and
    years for months.
    """
    assert _frequency_name(pd.Timestamp(start), offset) == expected
