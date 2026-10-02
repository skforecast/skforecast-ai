# Unit test _check_long_frequency

import numpy as np
import pandas as pd

from skforecast_ai.profiling.data_profile import (
    _check_long_frequency,
    _own_frequencies,
)

_BUSINESS = pd.bdate_range("2023-01-02", periods=20)
_DAILY = pd.date_range("2023-01-02", periods=26)


def _check(series_dates: dict, frequency: str) -> tuple:
    """Run the check on the dates of each series, as nanoseconds."""
    series_dates = {name: dates.asi8 for name, dates in series_dates.items()}
    return _check_long_frequency(
        series_dates = series_dates,
        all_dates    = np.concatenate(list(series_dates.values())),
        own          = _own_frequencies(series_dates),
        frequency    = frequency,
    )


def test_check_long_frequency_output_when_series_fit():
    """
    Test that series on the grid return the missing timestamps within the
    range of each series, summed (6 weekend days and 1 missing day), and no
    message.
    """
    result = _check({"b": _BUSINESS, "d": _DAILY.delete([3])}, "D")

    assert result == (7, None, [], 0, False)


def test_check_long_frequency_output_when_series_of_another_frequency():
    """
    Test that a daily series off the grid of business days is of another
    frequency: the message names both, the daily frequency is returned to
    try, and its 25 dates are blamed.
    """
    result = _check({"b": _BUSINESS, "d": _DAILY.delete([3])}, "B")

    assert result == (
        None,
        "The series do not share one frequency: 'B' (series 'b'), 'D' (series "
        "'d'). Every series of long-format data must have the same frequency; "
        "forecast the series of each frequency separately.",
        ["D"],
        25,
        True,
    )


def test_check_long_frequency_output_when_stray_timestamp():
    """
    Test that a daily series with one row at noon has a timestamp off the
    grid: the message names it and the row, no frequency is returned to
    try, and its 27 dates are blamed.
    """
    stray = _DAILY.insert(5, pd.Timestamp("2023-01-06 12:00"))

    result = _check({"a": _DAILY, "b": stray}, "D")

    assert result == (
        None,
        "Series 'b' has timestamps off the 'D' grid, for example 2023-01-06 "
        "12:00:00. Every series of long-format data must have the same "
        "frequency on the same grid: correct or drop those timestamps, or "
        "forecast those series separately.",
        [],
        27,
        False,
    )
