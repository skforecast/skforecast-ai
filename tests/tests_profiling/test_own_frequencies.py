# Unit test _own_frequencies

import pandas as pd

from skforecast_ai.profiling.data_profile import _own_frequencies

_DAILY = pd.date_range("2023-01-01", periods=40)


def test_own_frequencies_output():
    """
    Test that a series gets the frequency pandas infers on its first dates
    when they are regular (also for series that start on another day, which
    reuse the result of the same steps, and for months), and none when it
    has fewer than 10 dates, a gap among its first dates, or later dates
    sparser or denser than its first ones (daily then weekly, every two
    hours then hourly).
    """
    series_dates = {
        "daily": _DAILY,
        "daily_later": _DAILY + pd.Timedelta(days=3),
        "short": _DAILY[:9],
        "gappy": _DAILY.delete([5]),
        "months": pd.date_range("2020-01-01", periods=24, freq="MS"),
        "daily_then_weekly": pd.date_range("2020-01-01", periods=30).append(
            pd.date_range("2020-02-02", periods=20, freq="W-SUN")
        ),
        "two_hours_then_hourly": pd.date_range(
            "2021-01-01", periods=30, freq="2h"
        ).append(pd.date_range("2021-01-04", periods=300, freq="h")),
    }

    own = _own_frequencies(
        {name: dates.asi8 for name, dates in series_dates.items()}
    )

    assert own == {"daily": "D", "daily_later": "D", "months": "MS"}
