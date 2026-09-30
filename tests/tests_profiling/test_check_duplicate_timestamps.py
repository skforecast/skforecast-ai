# Unit test _check_duplicate_timestamps

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _check_duplicate_timestamps

from .fixtures_profiling import (
    df_long_identical_duplicates_series_b,
    df_range_index,
    df_single_daily,
    df_single_identical_duplicates,
)


def test_check_duplicate_timestamps_ValueError_when_rows_hold_unhashable_values():
    """
    Test that a repeated timestamp whose rows hold unhashable values (which
    cannot be compared) raises a ValueError instead of being dropped.
    """
    data = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-01", "2023-01-01", "2023-01-02"]),
            "y": [1.0, 1.0, 2.0],
            "tags": [["a"], ["a"], ["b"]],
        }
    )

    err_msg = re.escape(
        "Found 1 timestamp with more than one row and different values, for "
        "example '2023-01-01'. A single series needs one row per timestamp, "
        "and keeping only one of them would silently discard data. Aggregate "
        "or remove the repeated rows before profiling, or pass "
        "`series_id_column` if a column identifies different series."
    )
    with pytest.raises(ValueError, match=err_msg):
        _check_duplicate_timestamps(
            data             = data,
            target           = "y",
            date_col         = "date",
            index_type       = "datetime",
            data_format      = "single",
            series_id_column = None,
        )


@pytest.mark.parametrize(
    "data, index_type",
    [(df_single_daily, "datetime"), (df_range_index, "range")],
    ids=["datetime index without duplicates", "no datetime index"],
)
def test_check_duplicate_timestamps_output_when_no_timestamp_is_repeated(
    data, index_type
):
    """
    Test that no repeated timestamp (or no datetime source at all) returns
    a zero count and no mask.
    """
    result = _check_duplicate_timestamps(
        data             = data,
        target           = data.columns[0],
        date_col         = None,
        index_type       = index_type,
        data_format      = "single",
        series_id_column = None,
    )

    assert result == (0, None)


@pytest.mark.parametrize(
    "data, date_col, data_format, series_id_column, expected_n, expected_mask",
    [
        (
            df_single_identical_duplicates,
            None,
            "single",
            None,
            5,
            np.array([True] * 50 + [False] * 5),
        ),
        (
            df_long_identical_duplicates_series_b,
            "date",
            "long",
            "series_id",
            1,
            np.array([True] * 300 + [False]),
        ),
    ],
    ids=["single with a missing value in the copies", "long"],
)
def test_check_duplicate_timestamps_output_when_repeated_rows_are_identical(
    data, date_col, data_format, series_id_column, expected_n, expected_mask
):
    """
    Test that timestamps repeated in identical rows (two missing values
    count as identical) return their count and a mask that keeps the first
    row of each.
    """
    n_duplicate_timestamps, keep_mask = _check_duplicate_timestamps(
        data             = data,
        target           = "y" if data_format == "single" else "value",
        date_col         = date_col,
        index_type       = "datetime",
        data_format      = data_format,
        series_id_column = series_id_column,
    )

    assert n_duplicate_timestamps == expected_n
    np.testing.assert_array_equal(keep_mask, expected_mask)


def test_check_duplicate_timestamps_output_when_dates_are_missing():
    """
    Test that rows with a missing date are left out of the check, so two
    of them with different values do not count as a repeated timestamp.
    """
    data = pd.DataFrame(
        {
            "date": pd.to_datetime([None, None, "2023-01-01", "2023-01-02"]),
            "y": [1.0, 2.0, 3.0, 4.0],
        }
    )

    result = _check_duplicate_timestamps(
        data             = data,
        target           = "y",
        date_col         = "date",
        index_type       = "datetime",
        data_format      = "single",
        series_id_column = None,
    )

    assert result == (0, None)
