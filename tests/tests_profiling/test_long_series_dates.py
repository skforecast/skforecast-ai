# Unit test _long_series_dates

import numpy as np
import pandas as pd

from skforecast_ai.profiling.data_profile import _long_series_dates


def test_long_series_dates_output():
    """
    Test that the dates of each series (nanoseconds since the epoch) are
    sorted and distinct, in order of first appearance of the series, without
    the rows that have no date or no series id, and without the unused
    categories of a categorical id.
    """
    data = pd.DataFrame({
        "date": pd.to_datetime([
            "2023-01-02", "2023-01-01", "2023-01-01", "2023-01-02", None,
            "2023-01-03", "2023-01-01",
        ]),
        "id": pd.Categorical(
            ["b", "b", "a", "a", "a", "b", np.nan], categories=["a", "b", "z"]
        ),
    })

    series_dates = _long_series_dates(pd.DatetimeIndex(data["date"]), data["id"])

    assert list(series_dates) == ["b", "a"]
    np.testing.assert_array_equal(
        series_dates["b"],
        pd.DatetimeIndex(["2023-01-01", "2023-01-02", "2023-01-03"]).asi8,
    )
    np.testing.assert_array_equal(
        series_dates["a"], pd.DatetimeIndex(["2023-01-01", "2023-01-02"]).asi8
    )


def test_long_series_dates_output_when_no_row_has_date_and_id():
    """
    Test that data without any row with both a date and a series id has no
    series.
    """
    data = pd.DataFrame({
        "date": pd.to_datetime(["2023-01-01", None]),
        "id": [None, "a"],
    })

    assert _long_series_dates(pd.DatetimeIndex(data["date"]), data["id"]) == {}


def test_long_series_dates_output_when_dates_time_zone_aware():
    """
    Test that time zone aware dates are read in local time, so the days
    across a daylight saving time change keep midnight, or in UTC when they
    are converted to UTC.
    """
    data = pd.DataFrame({
        "date": pd.date_range("2023-03-25", periods=3, tz="Europe/Madrid"),
        "id": ["a", "a", "a"],
    })

    dates = pd.DatetimeIndex(data["date"])

    local = _long_series_dates(dates, data["id"])
    utc = _long_series_dates(dates.tz_convert("UTC"), data["id"])

    np.testing.assert_array_equal(
        local["a"],
        pd.DatetimeIndex(["2023-03-25", "2023-03-26", "2023-03-27"]).asi8,
    )
    np.testing.assert_array_equal(
        utc["a"],
        pd.DatetimeIndex(
            ["2023-03-24 23:00", "2023-03-25 23:00", "2023-03-26 22:00"]
        ).asi8,
    )


def test_long_series_dates_output_when_dates_beyond_nanoseconds():
    """
    Test that dates after the year 2262, which pandas keeps in seconds but
    not in nanoseconds, return None, so the frequency is read from the first
    series as before instead of failing.
    """
    dates = pd.DatetimeIndex(
        np.array(["2411-01-01", "2411-01-02"], dtype="datetime64[s]")
    )

    assert _long_series_dates(dates, pd.Series(["a", "a"])) is None


def test_long_series_dates_output_when_integer_categorical_ids_with_missing():
    """
    Test that integer categorical ids keep their values as names (not floats)
    when a row has no id.
    """
    dates = pd.date_range("2023-01-01", periods=3)
    ids = pd.Series(pd.Categorical([1, None, 3], categories=[1, 3]))

    series_dates = _long_series_dates(dates, ids)

    assert list(series_dates) == [1, 3]
    assert all(isinstance(name, (int, np.integer)) for name in series_dates)
