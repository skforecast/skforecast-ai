# Unit test date_positions

import numpy as np
import pandas as pd

from skforecast_ai._dates import date_positions


def test_date_positions_output_sorts_like_dates_with_missing_last():
    """
    Test that the positions sort like the dates, with the missing dates
    after every other date.
    """
    dates = pd.DatetimeIndex(["2023-01-03", None, "2023-01-01", "2023-01-02"])

    positions = date_positions(dates)

    np.testing.assert_array_equal(np.argsort(positions, kind="stable"), [2, 3, 0, 1])
    assert positions[1] == np.iinfo(np.int64).max


def test_date_positions_output_when_time_zone_aware():
    """
    Test that time zone aware dates are compared in UTC: 02:00 in Madrid in
    winter (UTC+1) is 01:00 UTC, before 01:30 UTC.
    """
    dates = pd.DatetimeIndex(
        [
            pd.Timestamp("2023-01-01 02:00", tz="Europe/Madrid"),
            pd.Timestamp("2023-01-01 00:30", tz="Europe/Madrid"),
        ]
    ).tz_convert("UTC")

    positions = date_positions(dates)

    np.testing.assert_array_equal(
        positions,
        np.array(
            [
                pd.Timestamp("2023-01-01 01:00", tz="UTC").value,
                pd.Timestamp("2022-12-31 23:30", tz="UTC").value,
            ]
        ),
    )
