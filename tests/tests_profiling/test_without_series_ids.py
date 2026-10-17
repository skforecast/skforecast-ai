# Unit test without_series_ids

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import without_series_ids

_DATA = pd.DataFrame(
    {
        "id": ["001", "1", "10"],
        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "y": [1.5, 2.5, 3.5],
    }
)


def test_without_series_ids_output():
    """
    Test that the column of series ids is left out and the other columns keep
    their order, and that the data given is not modified.
    """
    data = _DATA.copy()

    result = without_series_ids(data, "id")

    expected = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "y": [1.5, 2.5, 3.5],
        }
    )
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(data, _DATA)


@pytest.mark.parametrize(
    "series_id_column",
    [None, "store"],
    ids=lambda dt: f"series_id_column: {dt}",
)
def test_without_series_ids_returns_same_object_when_no_series_id_column(
    series_id_column,
):
    """
    Test that the data is returned as the same object when `series_id_column`
    is None or a column that the data does not hold.
    """
    result = without_series_ids(_DATA, series_id_column)

    assert result is _DATA


@pytest.mark.parametrize(
    "series_id_column, date_column, expected_columns",
    [
        ("id", "date", ["y"]),
        (None, "date", ["id", "y"]),
        ("id", None, ["date", "y"]),
        ("id", "store", ["date", "y"]),
        ("store", "date", ["id", "y"]),
        ("id", "id", ["date", "y"]),
    ],
    ids=[
        "series ids and dates",
        "dates only",
        "series ids only",
        "dates not in the data",
        "series ids not in the data",
        "same column",
    ],
)
def test_without_series_ids_output_when_date_column(
    series_id_column, date_column, expected_columns
):
    """
    Test that the column of the dates is left out too, which is not made of
    numbers either, together with the column of series ids when both are
    given, and that a column the data does not hold is ignored. The other
    columns keep their order and the data given is not modified.
    """
    data = _DATA.copy()

    result = without_series_ids(data, series_id_column, date_column)

    pd.testing.assert_frame_equal(result, _DATA[expected_columns])
    pd.testing.assert_frame_equal(data, _DATA)


@pytest.mark.parametrize(
    "series_id_column, date_column",
    [(None, None), ("store", None), (None, "day"), ("store", "day")],
    ids=lambda dt: f"{dt}",
)
def test_without_series_ids_returns_same_object_when_no_column_to_drop(
    series_id_column, date_column
):
    """
    Test that the data is returned as the same object when the columns of
    series ids and dates are None or columns that the data does not hold.
    """
    result = without_series_ids(_DATA, series_id_column, date_column)

    assert result is _DATA
