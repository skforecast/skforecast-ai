# Unit test _sort_rows_by_date

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _sort_rows_by_date

_dates = pd.date_range("2023-01-01", periods=4, freq="D")


def _sort(data, date_col=None, data_format="single", series_id_column=None):
    """Call `_sort_rows_by_date` on datetime data."""
    return _sort_rows_by_date(
        data             = data,
        date_col         = date_col,
        index_type       = "datetime",
        data_format      = data_format,
        series_id_column = series_id_column,
    )


@pytest.mark.parametrize(
    "data, kwargs",
    [
        (pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0]}, index=_dates), {}),
        (
            pd.DataFrame({"date": [_dates[0], pd.NaT, _dates[2], _dates[3]]}),
            {"date_col": "date"},
        ),
        (
            pd.DataFrame({
                "date": [_dates[0], _dates[0], _dates[1], _dates[1]],
                "id": ["b", "a", "b", "a"],
            }),
            {"date_col": "date", "data_format": "long", "series_id_column": "id"},
        ),
    ],
    ids=["sorted", "sorted_with_missing_date", "long_by_date"],
)
def test_sort_rows_by_date_returns_input_when_in_date_order(data, kwargs):
    """
    Test that rows already in date order (missing dates ignored; long format
    in date order within each series) are returned as given, the same
    object, and are not reported as sorted.
    """
    result, rows_sorted = _sort(data, **kwargs)

    assert result is data
    assert rows_sorted is False


def test_sort_rows_by_date_output_when_missing_dates_and_unsorted():
    """
    Test that unsorted rows are sorted with a stable sort and that rows
    without a date go last.
    """
    data = pd.DataFrame({
        "date": [_dates[2], pd.NaT, _dates[0], _dates[1]],
        "y": [3.0, 9.0, 1.0, 2.0],
    })

    result, rows_sorted = _sort(data, date_col="date")

    assert rows_sorted is True
    np.testing.assert_array_equal(result["y"].to_numpy(), [1.0, 2.0, 3.0, 9.0])
    np.testing.assert_array_equal(result.index.to_numpy(), [2, 3, 0, 1])


def test_sort_rows_by_date_output_when_time_zone_aware_index():
    """
    Test that a time zone aware DatetimeIndex out of order is sorted in time.
    """
    index = pd.date_range("2023-03-25 22:00", periods=6, freq="h", tz="Europe/Madrid")
    data = pd.DataFrame({"y": np.arange(6.0)}, index=index[::-1])

    result, rows_sorted = _sort(data)

    assert rows_sorted is True
    np.testing.assert_array_equal(result.index.to_numpy(), index.to_numpy())


def test_sort_rows_by_date_output_when_long_format_one_series_unsorted():
    """
    Test that long-format data with only one series out of order is sorted by
    series, in order of first appearance, and then by date, so the first
    series stays first.
    """
    data = pd.DataFrame({
        "date": [_dates[0], _dates[1], _dates[1], _dates[0]],
        "id": ["b", "b", "a", "a"],
        "y": [1.0, 2.0, 4.0, 3.0],
    })

    result, rows_sorted = _sort(
        data, date_col="date", data_format="long", series_id_column="id"
    )

    assert rows_sorted is True
    assert result["id"].tolist() == ["b", "b", "a", "a"]
    np.testing.assert_array_equal(result["y"].to_numpy(), [1.0, 2.0, 3.0, 4.0])


def test_sort_rows_by_date_returns_input_when_no_dates():
    """
    Test that data without dates keeps its row order.
    """
    data = pd.DataFrame({"y": [3.0, 1.0, 2.0]})

    result, rows_sorted = _sort_rows_by_date(
        data             = data,
        date_col         = None,
        index_type       = "range",
        data_format      = "single",
        series_id_column = None,
    )

    assert result is data
    assert rows_sorted is False


def test_sort_rows_by_date_keeps_parsed_dates_when_text_dates_sorted():
    """
    Test that sorted text dates are replaced by the dates parsed before
    sorting, so they are not parsed again from another first row with
    another format (day-first dates in descending order).
    """
    data = pd.DataFrame({
        "date": ["13/01/2012", "02/01/2012", "01/01/2012"],
        "y": [3.0, 2.0, 1.0],
    })

    result, rows_sorted = _sort(data, date_col="date")

    assert rows_sorted is True
    np.testing.assert_array_equal(
        result["date"].to_numpy(),
        pd.to_datetime(["2012-01-01", "2012-01-02", "2012-01-13"]).to_numpy(),
    )


def test_sort_rows_by_date_ignores_rows_without_series_id():
    """
    Test that rows without a series id, which belong to no series, are left
    out of the order check of long-format data.
    """
    data = pd.DataFrame({
        "date": [_dates[0], _dates[1], _dates[3], _dates[0], _dates[1]],
        "id": ["a", "a", None, "b", None],
    })

    result, rows_sorted = _sort(
        data, date_col="date", data_format="long", series_id_column="id"
    )

    assert result is data
    assert rows_sorted is False


def test_sort_rows_by_date_puts_rows_without_series_id_last():
    """
    Test that rows without a series id go after every series when long-format
    data is sorted, so the first row still belongs to a real series.
    """
    data = pd.DataFrame({
        "date": [_dates[1], _dates[0], _dates[2], _dates[1], _dates[0]],
        "id": ["a", "a", None, "b", "b"],
        "y": [2.0, 1.0, 9.0, 4.0, 3.0],
    })

    result, rows_sorted = _sort(
        data, date_col="date", data_format="long", series_id_column="id"
    )

    assert rows_sorted is True
    assert result["id"].tolist() == ["a", "a", "b", "b", None]
    np.testing.assert_array_equal(result["y"].to_numpy(), [1.0, 2.0, 3.0, 4.0, 9.0])
