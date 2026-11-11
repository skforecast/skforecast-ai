# Unit test _local_index

import pandas as pd
import pytest

from skforecast_ai.recommendation.backtesting import _local_index, _position_to_date


def test_local_index_output_without_time_zone():
    """
    Test that without a time zone the index is the regular grid from the
    start date.
    """
    result = _local_index("2023-03-26", 5, "h", None)

    pd.testing.assert_index_equal(
        result, pd.date_range("2023-03-26", periods=5, freq="h")
    )


@pytest.mark.parametrize(
    "start_date, expected",
    [
        (
            "2023-03-26",
            ["2023-03-26 00:00", "2023-03-26 01:00", "2023-03-26 03:00",
             "2023-03-26 04:00"],
        ),
        (
            "2023-10-29 01:00",
            ["2023-10-29 01:00", "2023-10-29 02:00", "2023-10-29 02:00",
             "2023-10-29 03:00"],
        ),
    ],
    ids=["spring: 02:00 skipped", "autumn: 02:00 repeated"],
)
def test_local_index_output_across_a_daylight_saving_change(start_date, expected):
    """
    Test that with a time zone the index holds the local times of the zone,
    which skip an hour in spring and repeat one in autumn.
    """
    result = _local_index(start_date, 4, "h", "Europe/Madrid")

    pd.testing.assert_index_equal(result, pd.DatetimeIndex(expected), exact=False)


def test_local_index_output_regular_grid_when_time_zone_is_unknown():
    """
    Test that a zone pandas cannot use gives the regular grid.
    """
    result = _local_index("2023-03-26", 3, "h", "Not/AZone")

    pd.testing.assert_index_equal(
        result, pd.date_range("2023-03-26", periods=3, freq="h")
    )


def test_position_to_date_output_with_time_zone():
    """
    Test that the date of a position is the local time at that position:
    the third hour of 2023-03-26 in Madrid is 03:00, and 02:00 without zone.
    """
    assert _position_to_date(3, "2023-03-26", "h") == "2023-03-26 02:00:00"
    assert (
        _position_to_date(3, "2023-03-26", "h", "Europe/Madrid")
        == "2023-03-26 03:00:00"
    )
