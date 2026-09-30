# Unit test detect_date_column

import re

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import detect_date_column


def test_detect_date_column_ValueError_when_named_column_is_not_datetime_like():
    """
    Test that pointing `date_column` at a column that does not hold dates
    raises a ValueError quoting values that could not be parsed, instead of
    treating the column as an exogenous variable.
    """
    data = pd.DataFrame(
        {"code": ["2023-01-01", "b", "c", "d"], "y": [1.0, 2.0, 3.0, 4.0]}
    )

    err_msg = re.escape(
        "date_column='code' does not hold dates: values such as ['b', 'c', "
        "'d'] could not be parsed as timestamps. Pass the column that holds "
        "the dates, or convert it with pandas.to_datetime before profiling."
    )
    with pytest.raises(ValueError, match=err_msg):
        detect_date_column(data, "code")


def test_detect_date_column_ValueError_when_named_index_is_not_datetime():
    """
    Test that pointing `date_column` at the index name raises a ValueError
    when the index is not a DatetimeIndex, even if its values are dates.
    """
    data = pd.DataFrame(
        {"y": [1.0, 2.0, 3.0]},
        index=pd.Index(["2023-01-01", "2023-01-02", "2023-01-03"], name="day"),
    )

    err_msg = re.escape(
        "date_column='day' names the index, which is not a DatetimeIndex "
        "(values such as ['2023-01-01', '2023-01-02', '2023-01-03']). Convert "
        "it with pandas.to_datetime before profiling, or omit date_column."
    )
    with pytest.raises(ValueError, match=err_msg):
        detect_date_column(data, "day")


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
