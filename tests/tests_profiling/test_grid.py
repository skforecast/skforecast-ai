# Unit test _grid

import numpy as np
import pandas as pd

from skforecast_ai.profiling.data_profile import _grid


def test_grid_output_when_fixed_frequency():
    """
    Test that the grid of a fixed frequency is the phase shared by most
    dates, counted over every date: three dates at half past the hour and
    one on the hour give the half hour, in nanoseconds.
    """
    dates = pd.DatetimeIndex([
        "2023-01-01 00:30", "2023-01-01 01:30", "2023-01-01 02:00",
        "2023-01-01 02:30",
    ]).asi8

    offset, grid = _grid(dates, "h")

    assert offset == pd.tseries.frequencies.to_offset("h")
    assert grid == pd.Timedelta(minutes=30).value


def test_grid_output_when_business_days():
    """
    Test that the grid of business days runs from the first to the last
    date, without the weekend.
    """
    dates = pd.DatetimeIndex(["2023-01-02", "2023-01-04", "2023-01-09"]).asi8

    offset, grid = _grid(dates, "B")

    assert offset == pd.tseries.frequencies.to_offset("B")
    np.testing.assert_array_equal(
        grid,
        pd.DatetimeIndex([
            "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05",
            "2023-01-06", "2023-01-09",
        ]).asi8,
    )


def test_grid_output_when_business_hours():
    """
    Test that the grid of business hours starts at the opening hour of the
    first day, even when the first date is in the afternoon, so every hour
    of the working day lies on it.
    """
    dates = pd.DatetimeIndex([
        "2023-01-02 13:00", "2023-01-02 16:00", "2023-01-03 09:00",
    ]).asi8

    offset, grid = _grid(dates, "bh")

    assert offset == pd.tseries.frequencies.to_offset("bh")
    np.testing.assert_array_equal(
        grid,
        pd.DatetimeIndex([
            "2023-01-02 09:00", "2023-01-02 10:00", "2023-01-02 11:00",
            "2023-01-02 12:00", "2023-01-02 13:00", "2023-01-02 14:00",
            "2023-01-02 15:00", "2023-01-02 16:00", "2023-01-03 09:00",
        ]).asi8,
    )


def test_grid_output_when_multiple_of_calendar_frequency():
    """
    Test that the grid of every second week is the one of the two weekly
    grids that most dates lie on, not the one of the first date.
    """
    dates = np.concatenate([
        pd.date_range("2020-01-05", periods=3, freq="2W-SUN").asi8,
        pd.date_range("2020-01-12", periods=4, freq="2W-SUN").asi8,
        pd.date_range("2020-01-12", periods=4, freq="2W-SUN").asi8,
    ])

    offset, grid = _grid(dates, "2W-SUN")

    assert offset == pd.tseries.frequencies.to_offset("2W-SUN")
    np.testing.assert_array_equal(
        grid,
        pd.DatetimeIndex(
            ["2020-01-12", "2020-01-26", "2020-02-09", "2020-02-23"]
        ).asi8,
    )


def test_grid_output_when_first_date_before_time_of_most_dates():
    """
    Test that the grid of business days at 09:00, the time of most dates,
    starts on the first business day of the data, although its first date
    (08:00) comes before that time.
    """
    dates = pd.DatetimeIndex(
        ["2023-01-02 08:00", "2023-01-03 09:00", "2023-01-04 09:00"]
    ).asi8

    _, grid = _grid(dates, "B")

    np.testing.assert_array_equal(
        grid,
        pd.DatetimeIndex(
            ["2023-01-02 09:00", "2023-01-03 09:00", "2023-01-04 09:00"]
        ).asi8,
    )


def test_grid_output_when_no_date_on_multiple_of_calendar_frequency():
    """
    Test that the grid of every second month start keeps every month start
    when no date lies on it (dates in the middle of the month).
    """
    dates = pd.DatetimeIndex(["2023-01-15", "2023-03-15"]).asi8

    _, grid = _grid(dates, "2MS")

    np.testing.assert_array_equal(
        grid, pd.DatetimeIndex(["2023-02-01", "2023-03-01"]).asi8
    )
