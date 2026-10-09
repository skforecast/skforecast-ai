# Unit test _longest_series

import pandas as pd

from skforecast_ai.profiling.data_profile import _longest_series


def test_longest_series_output():
    """
    Test that the series with the most dates is returned and that, on a
    tie, the one that starts first, then the one that ends first, then the
    first by name is, whatever the order of the names.
    """
    dates = pd.date_range("2023-01-01", periods=40)
    series_dates = {
        "x": dates[5:].asi8,
        "y": dates[:35].asi8,
        "z": dates[[0, *range(2, 36)]].asi8,
        "b": dates[1:31].asi8,
        "a": dates[1:31].asi8,
    }

    assert _longest_series(series_dates, ["x", "y", "z"]) == "y"
    assert _longest_series(series_dates, ["z", "x", "y"]) == "y"
    assert _longest_series(series_dates, ["b", "a"]) == "a"
