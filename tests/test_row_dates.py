# Unit test row_dates

import numpy as np
import pandas as pd
import pytest

from skforecast_ai._dates import row_dates

_dates = pd.date_range("2023-01-01", periods=3, freq="D")


@pytest.mark.parametrize(
    "data, date_column",
    [
        (pd.DataFrame({"date": _dates, "y": [1.0, 2.0, 3.0]}), "date"),
        (
            pd.DataFrame({
                "date": ["2023-01-01", "2023-01-02", "2023-01-03"],
                "y": [1.0, 2.0, 3.0],
            }),
            "date",
        ),
        (pd.DataFrame({"y": [1.0, 2.0, 3.0]}, index=_dates), None),
        (
            pd.DataFrame(
                {"y": [1.0, 2.0, 3.0]},
                index=pd.MultiIndex.from_arrays(
                    [["a", "a", "a"], _dates], names=["series", "date"]
                ),
            ),
            "date",
        ),
    ],
    ids=["datetime_column", "text_column", "datetime_index", "multiindex_level"],
)
def test_row_dates_output(data, date_column):
    """
    Test that the date of every row is read from the date column (parsed when
    it holds text), the level of a MultiIndex or the DatetimeIndex.
    """
    dates = row_dates(data, date_column)

    assert isinstance(dates, pd.DatetimeIndex)
    np.testing.assert_array_equal(dates.to_numpy(), _dates.to_numpy())


def test_row_dates_column_wins_over_index_of_same_name():
    """
    Test that a date column is used even when the index is a different
    DatetimeIndex, or has the same name as the column.
    """
    data = pd.DataFrame(
        {"date": _dates[::-1], "y": [1.0, 2.0, 3.0]},
        index=pd.DatetimeIndex(_dates, name="date"),
    )

    dates = row_dates(data, "date")

    np.testing.assert_array_equal(dates.to_numpy(), _dates[::-1].to_numpy())


def test_row_dates_output_when_date_level_of_multiindex_unnamed():
    """
    Test that the second level of a MultiIndex is read as the dates when it
    has no name, as profiling reads it.
    """
    data = pd.DataFrame(
        {"y": [3.0, 1.0, 2.0]},
        index=pd.MultiIndex.from_arrays(
            [["a", "a", "a"], [_dates[2], _dates[0], _dates[1]]],
            names=["series", None],
        ),
    )

    dates = row_dates(data, "datetime")

    np.testing.assert_array_equal(
        dates.to_numpy(), _dates[[2, 0, 1]].to_numpy()
    )


def test_row_dates_output_when_no_multiindex_level_matches():
    """
    Test that a MultiIndex without a level named as the date column, and
    whose second level has a name, has no dates.
    """
    data = pd.DataFrame(
        {"y": [1.0, 2.0, 3.0]},
        index=pd.MultiIndex.from_arrays(
            [["a", "a", "a"], _dates], names=["series", "when"]
        ),
    )

    assert row_dates(data, "date") is None


def test_row_dates_output_when_text_dates_day_first():
    """
    Test that a text date column is parsed with the format of its first
    date, so '01/02/2023' is the first of February after '13/01/2023'.
    """
    data = pd.DataFrame({
        "date": ["13/01/2023", "01/02/2023", "02/02/2023"],
        "y": [1.0, 2.0, 3.0],
    })

    dates = row_dates(data, "date")

    np.testing.assert_array_equal(
        dates.to_numpy(),
        pd.to_datetime(["2023-01-13", "2023-02-01", "2023-02-02"]).to_numpy(),
    )


def test_row_dates_output_when_multiindex_level_holds_text_dates_day_first():
    """
    Test that a MultiIndex level of text dates is parsed as a date column
    is, with the format of its first date and without the warning pandas
    emits for day-first formats.
    """
    data = pd.DataFrame(
        {"y": [1.0, 2.0, 3.0]},
        index=pd.MultiIndex.from_arrays(
            [["a", "a", "a"], ["13/01/2023", "01/02/2023", "02/02/2023"]],
            names=["series", "date"],
        ),
    )

    dates = row_dates(data, "date")

    np.testing.assert_array_equal(
        dates.to_numpy(),
        pd.to_datetime(["2023-01-13", "2023-02-01", "2023-02-02"]).to_numpy(),
    )


def test_row_dates_output_when_no_datetime_source():
    """
    Test that data without a date column or a DatetimeIndex has no dates.
    """
    data = pd.DataFrame({"y": [1.0, 2.0, 3.0]})

    assert row_dates(data, None) is None
    assert row_dates(data, "missing") is None
