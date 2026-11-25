# Unit test compact_dates_as_text

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import compact_dates_as_text

_DATES = pd.date_range("2020-01-30", periods=3, freq="D")


@pytest.mark.parametrize(
    "dtype",
    ["int64", "int32", "Int64"],
    ids=lambda dtype: f"{dtype}",
)
def test_compact_dates_as_text_output_when_dates_are_whole_numbers(dtype):
    """
    Test that dates of whole numbers of eight digits become text, as the
    generated script reads them, that the other columns are not touched and
    that the input is not modified.
    """
    data = pd.DataFrame({
        "date": pd.Series([20200130, 20200131, 20200201], dtype=dtype),
        "y":    [1.0, 2.0, 3.0],
    })

    result = compact_dates_as_text(data, "date")

    expected = pd.DataFrame({
        "date": ["20200130", "20200131", "20200201"],
        "y":    [1.0, 2.0, 3.0],
    })
    pd.testing.assert_frame_equal(result, expected)
    assert data["date"].dtype == dtype


@pytest.mark.parametrize(
    "dates, date_column",
    [
        (_DATES, "date"),
        (["20200130", "20200131", "20200201"], "date"),
        (["2020-01-30", "2020-01-31", "2020-02-01"], "date"),
        ([120, 135, 150], "date"),
        ([20200130, 20200131, 20200231], "date"),
        ([20200130, 20200131, 20200201], None),
        ([20200130, 20200131, 20200201], "other"),
    ],
    ids=["dates", "text of eight digits", "text", "counts",
         "a number that is not a day", "no date column",
         "date column not in the data"],
)
def test_compact_dates_as_text_output_is_data_when_nothing_to_turn(
    dates, date_column
):
    """
    Test that data are returned as they are when their dates are not whole
    numbers that are all dates of eight digits (dates already parsed, text,
    other numbers), and without a date column or one the data do not hold.
    """
    data = pd.DataFrame({"date": dates, "y": [1.0, 2.0, 3.0]})

    result = compact_dates_as_text(data, date_column)

    assert result is data


def test_compact_dates_as_text_output_is_data_when_date_column_is_repeated():
    """
    Test that data with a repeated date column name are returned as they
    are: the checks of the data report the repeated name.
    """
    data = pd.DataFrame(
        [[20200130, 20200130, 1.0], [20200131, 20200131, 2.0]],
        columns=["date", "date", "y"],
    )

    result = compact_dates_as_text(data, "date")

    assert result is data
