# Unit test _compact_dates

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import COMPACT_DATE_FORMAT, _compact_dates


def test_compact_dates_format():
    """
    Test that the format whole numbers of eight digits are read with is
    year, month and day.
    """
    assert COMPACT_DATE_FORMAT == "%Y%m%d"


@pytest.mark.parametrize(
    "dtype", ["int64", "int32", "uint32", "Int64"], ids=lambda dt: f"dtype: {dt}"
)
def test_compact_dates_output_when_whole_numbers_are_dates(dtype):
    """
    Test that a column of whole numbers of eight digits that are all real
    days (year, month, day) is returned as dates, whatever the integer dtype,
    with its index and name, and that the column given is not modified.
    """
    values = pd.Series(
        [20200101, 20200131, 20201231],
        index=[5, 6, 7],
        name="date",
        dtype=dtype,
    )
    values_copy = values.copy()

    result = _compact_dates(values)

    expected = pd.Series(
        pd.to_datetime(["2020-01-01", "2020-01-31", "2020-12-31"]),
        index=[5, 6, 7],
        name="date",
    )
    pd.testing.assert_series_equal(result, expected)
    pd.testing.assert_series_equal(values, values_copy)


@pytest.mark.parametrize(
    "values",
    [
        pd.Series([20200101.0, 20200102.0]),
        pd.Series(["20200101", "20200102"]),
        pd.Series([True, False]),
        pd.Series([], dtype="int64"),
        pd.Series([20200101, None], dtype="Int64"),
        pd.Series([1, 2, 3]),
        pd.Series([20200101, 5]),
        pd.Series([20200101, 12345678]),
        pd.Series([20200101, 20200230]),
        pd.Series([20200101, 20201301]),
        pd.Series([20200101, 20200100]),
        pd.Series([20200101, 10000100]),
        pd.Series([10000101]),
        pd.Series([20200101, 100000000]),
        pd.Series([20200101, 99991231]),
    ],
    ids=[
        "floats",
        "text",
        "booleans",
        "empty",
        "missing value",
        "small numbers",
        "one small number",
        "one number that is not a date",
        "day that does not exist",
        "month that does not exist",
        "day zero",
        "below the range",
        "year before the range of pandas",
        "above the range",
        "year after the range of pandas",
    ],
)
def test_compact_dates_output_is_None_when_not_all_whole_numbers_are_dates(values):
    """
    Test that None is returned for a column that is not made of whole
    numbers that are all dates of eight digits: floats, text, booleans, an
    empty column, a missing value, a number that is not a real day (amounts,
    counts and codes are not dates) and a date out of the range of pandas.
    """
    assert _compact_dates(values) is None
