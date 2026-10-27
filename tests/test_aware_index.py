# Unit test aware_index

import pandas as pd
import pytest

from skforecast_ai._dates import aware_index


def test_aware_index_output_with_time_zone():
    """
    Test that with a time zone the index holds the dates in that zone, with
    the UTC offset of each one across the spring daylight saving change.
    """
    result = aware_index("2023-03-26", 4, "h", "Europe/Madrid")

    expected = pd.DatetimeIndex(
        ["2023-03-25 23:00", "2023-03-26 00:00", "2023-03-26 01:00",
         "2023-03-26 02:00"],
        tz="UTC",
    ).tz_convert("Europe/Madrid")
    pd.testing.assert_index_equal(result, expected, exact=False)
    assert [str(date) for date in result] == [
        "2023-03-26 00:00:00+01:00", "2023-03-26 01:00:00+01:00",
        "2023-03-26 03:00:00+02:00", "2023-03-26 04:00:00+02:00",
    ]


@pytest.mark.parametrize("time_zone", [None, "Not/AZone"], ids=["none", "unknown"])
def test_aware_index_output_None_without_a_usable_time_zone(time_zone):
    """
    Test that there is no index without a time zone or with one pandas
    cannot use.
    """
    assert aware_index("2023-03-26", 3, "h", time_zone) is None
