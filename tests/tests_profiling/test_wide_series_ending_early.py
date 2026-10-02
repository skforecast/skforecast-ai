# Unit test _wide_series_ending_early

import numpy as np
import pandas as pd

from skforecast_ai.profiling.data_profile import _wide_series_ending_early

from .fixtures_profiling import df_wide_ending_early


def test_wide_series_ending_early_output():
    """
    Test that the columns whose last value comes before the last date with a
    value are returned with the date of their last value, missing values
    between values being kept.
    """
    result = _wide_series_ending_early(df_wide_ending_early, ["a", "b", "c"], None)

    assert result == ("2023-01-04", {"b": "2023-01-02", "c": "2023-01-03"})


def test_wide_series_ending_early_output_when_dates_in_column_and_unsorted():
    """
    Test that the dates are read from the date column when the data has one,
    in date order whatever the order of the rows.
    """
    data = df_wide_ending_early.reset_index(names="date").iloc[::-1]

    result = _wide_series_ending_early(data, ["a", "b"], "date")

    assert result == ("2023-01-04", {"b": "2023-01-02"})


def test_wide_series_ending_early_output_None_when_series_end_together():
    """
    Test that None is returned when every series reaches the last date with
    a value, also when they all end with missing values, and that a column
    without any value is left out.
    """
    data = df_wide_ending_early[["a"]].assign(d=df_wide_ending_early["a"], e=np.nan)
    data.iloc[-1] = np.nan

    assert _wide_series_ending_early(data, ["a", "d", "e"], None) is None


def test_wide_series_ending_early_output_when_dates_tz_aware_beyond_nanoseconds():
    """
    Test that time zone aware dates beyond the years 1677 to 2262 (a unit of
    seconds) are read without being converted to nanoseconds.
    """
    data = df_wide_ending_early.set_axis(
        pd.date_range("2300-01-01", periods=4, freq="D", unit="s", tz="UTC")
    )

    result = _wide_series_ending_early(data, ["a", "b"], None)

    assert result == ("2300-01-04", {"b": "2300-01-02"})


def test_wide_series_ending_early_output_when_columns_of_other_types():
    """
    Test that only the missing values of the columns are read, so columns of
    durations next to numbers and tuple names are accepted.
    """
    data = pd.DataFrame(
        {
            ("x", "a"): [1.0, 2.0, 3.0, 4.0],
            ("x", "b"): pd.to_timedelta([1, 2, None, None], unit="h"),
        },
        index=df_wide_ending_early.index,
    )

    result = _wide_series_ending_early(data, [("x", "a"), ("x", "b")], None)

    assert result == ("2023-01-04", {"('x', 'b')": "2023-01-02"})


def test_wide_series_ending_early_output_None_when_columns_repeated():
    """
    Test that None is returned when a target name is repeated in the data,
    so the columns cannot be read one per series.
    """
    data = pd.concat([df_wide_ending_early, df_wide_ending_early[["b"]]], axis=1)

    assert _wide_series_ending_early(data, ["a", "b"], None) is None
