# Unit test detect_date_column

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import detect_date_column


def test_detect_date_column_output_when_named_column_is_not_datetime_like():
    """
    Test that pointing `date_column` at a column that does not hold
    datetimes yields no date column and the `'other'` index type.
    """
    data = pd.DataFrame({"code": ["a", "b", "c"], "y": [1.0, 2.0, 3.0]})

    assert detect_date_column(data, "code") == (None, "other")


def test_detect_date_column_output_when_named_index_is_not_datetime():
    """
    Test that pointing `date_column` at the index name yields the
    `'other'` index type when the index is not a DatetimeIndex.
    """
    data = pd.DataFrame({"y": [1.0, 2.0, 3.0]}, index=pd.Index(["a", "b", "c"], name="code"))

    assert detect_date_column(data, "code") == (None, "other")


def test_detect_date_column_output_when_no_datetime_source_and_string_index():
    """
    Test that a frame without datetime columns and with a non-range,
    non-datetime index is classified as `'other'`.
    """
    data = pd.DataFrame({"y": [1.0, 2.0, 3.0]}, index=pd.Index(["a", "b", "c"]))

    assert detect_date_column(data, None) == (None, "other")


def test_detect_date_column_ValueError_when_column_missing():
    """
    Test that an unknown `date_column` raises ValueError listing the
    available columns.
    """
    data = pd.DataFrame({"y": [1.0, 2.0, 3.0]})

    with pytest.raises(ValueError, match="date_column='date' was not found"):
        detect_date_column(data, "date")
