# Unit test detect_date_column

import datetime
import re

import dateutil.tz
import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import DAYFIRST_FRAME_HINT, detect_date_column

from ..fixtures_datasets import df_h2o_text, df_madrid_hourly_text


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


@pytest.mark.parametrize(
    "dtype", [object, "string"], ids=lambda dt: f"dtype: {dt}"
)
def test_detect_date_column_ValueError_when_named_column_has_empty_cells(dtype):
    """
    Test that a named text date column with empty cells raises an error that
    says where they are, instead of quoting valid dates as values that
    could not be parsed.
    """
    data = df_h2o_text.astype({"date": dtype})
    data.loc[[100, 101], "date"] = None

    err_msg = re.escape(
        "The dates of column 'date' have 2 empty cell(s), at row position(s) "
        "100, 101 (counting from 0, header excluded): every row needs a date. "
        "Fill in or drop those rows."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        detect_date_column(data, "date")

    assert exc_info.value.field == "data"


def test_detect_date_column_ValueError_when_named_column_mixes_time_zones():
    """
    Test that a named text date column in local time across a daylight
    saving time change raises an error that names the time zones, instead
    of a pandas error raised later.
    """
    err_msg = re.escape(
        "The dates of column 'date' mix time zones (+01:00, +02:00), so they "
        "cannot be placed on one time axis"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        detect_date_column(df_madrid_hourly_text, "date")


def test_detect_date_column_output_when_named_column_of_utc_datetimes():
    """
    Test that a named column of UTC datetimes whose time zone objects differ
    (from dateutil and from the standard library) is a date column, as
    pandas reads them as one time zone.
    """
    data = pd.DataFrame({
        "date": pd.Series(
            [
                datetime.datetime(2023, 1, 1, tzinfo=dateutil.tz.tzutc()),
                datetime.datetime(2023, 1, 2, tzinfo=datetime.timezone.utc),
                datetime.datetime(2023, 1, 3, tzinfo=dateutil.tz.tzutc()),
            ],
            dtype=object,
        ),
        "y": [1.0, 2.0, 3.0],
    })

    assert detect_date_column(data, "date") == ("date", "datetime")


@pytest.mark.parametrize(
    "dtype", ["int64", "int32", "Int64"], ids=lambda dt: f"dtype: {dt}"
)
def test_detect_date_column_output_when_named_column_of_whole_numbers_as_dates(
    dtype,
):
    """
    Test that a named column of whole numbers that are all dates of eight
    digits ('20200131', year, month and day) is a datetime column, whatever
    the integer dtype.
    """
    data = pd.DataFrame(
        {
            "day": pd.Series([20200101, 20200102, 20200131], dtype=dtype),
            "y": [1.0, 2.0, 3.0],
        }
    )

    assert detect_date_column(data, "day") == ("day", "datetime")


def test_detect_date_column_output_when_whole_numbers_as_dates_without_date_column():
    """
    Test that whole numbers of eight digits are not looked for when
    `date_column` is None: the frame has no datetime source, as the numbers
    are read as dates only where the caller names the column (a CSV file is
    converted before, see `_try_parse_first_date_column`).
    """
    data = pd.DataFrame({"day": [20200101, 20200102], "y": [1.0, 2.0]})

    assert detect_date_column(data, None) == (None, "range")


def test_detect_date_column_ValueError_when_named_column_of_whole_numbers_not_dates():
    """
    Test that a named column of whole numbers of eight digits that are not
    all real days (20200230) raises an InvalidInputError that quotes the
    values, as any column that does not hold dates, with the field
    'date_column'.
    """
    data = pd.DataFrame({"day": [20200101, 20200230], "y": [1.0, 2.0]})

    err_msg = re.escape(
        "date_column='day' does not hold dates: values such as ['20200101', "
        "'20200230'] could not be parsed as timestamps. Pass the column that "
        "holds the dates, or convert it with pandas.to_datetime before "
        "profiling."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        detect_date_column(data, "day")

    assert exc_info.value.field == "date_column"


@pytest.mark.parametrize(
    "dates",
    [
        ["13/01/2020", "14/01/2020"],
        ["01/02/2020", "13/02/2020"],
        ["01/13/2020", "01/14/2020"],
    ],
    ids=["day first", "day first after a date that reads both", "month first"],
)
def test_detect_date_column_output_when_named_column_of_text_dates_read_in_one_order(
    dates,
):
    """
    Test that a named column of text dates in day-first or month-first order
    that the dates themselves settle is a datetime column, with no
    `date_format` needed.
    """
    data = pd.DataFrame({"date": dates, "y": [1.0, 2.0]})

    assert detect_date_column(data, "date") == ("date", "datetime")


def test_detect_date_column_InvalidInputError_when_named_text_dates_ambiguous():
    """
    Test that a named column of text dates in a DataFrame that read day first
    and month first, with no `date_format` to decide and both readings
    regular, raises an InvalidInputError that asks for `dayfirst`, with the
    code 'data_unreadable', the field 'data' and the hint of a DataFrame:
    the order is never guessed.
    """
    data = pd.DataFrame(
        {"date": ["01/01/2020", "01/02/2020", "01/03/2020"], "y": [1.0, 2.0, 3.0]}
    )

    err_msg = re.escape(
        "The dates of column 'date' read both day first and month first: no "
        "day is after the 12th, so '01/02/2020' may be '2020-02-01' or "
        "'2020-01-02', and both readings have a regular frequency ('MS' day "
        "first and 'D' month first), so the order is not guessed. Profile the "
        "data saying which it is, with `dayfirst`."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        detect_date_column(data, "date")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == DAYFIRST_FRAME_HINT


@pytest.mark.parametrize("dayfirst", [True, False], ids=lambda dt: f"dayfirst: {dt}")
def test_detect_date_column_output_when_dayfirst_decides_ambiguous_text(dayfirst):
    """
    Test that a named column of text dates in a DataFrame that read day first
    and month first, regular in both orders, is the date column when
    `dayfirst` gives their order.
    """
    data = pd.DataFrame(
        {"date": ["01/01/2020", "01/02/2020", "01/03/2020"], "y": [1.0, 2.0, 3.0]}
    )

    assert detect_date_column(data, "date", dayfirst=dayfirst) == (
        "date",
        "datetime",
    )


@pytest.mark.parametrize(
    "date_format", ["%d/%m/%Y", "%m/%d/%Y"], ids=lambda dt: f"date_format: {dt}"
)
def test_detect_date_column_output_when_date_format_decides_ambiguous_text(
    date_format,
):
    """
    Test that a named column of text dates that read day first and month
    first is a datetime column when the format of a profile of the data is
    given, in either order.
    """
    data = pd.DataFrame(
        {"date": ["01/01/2020", "01/02/2020", "01/03/2020"], "y": [1.0, 2.0, 3.0]}
    )

    assert detect_date_column(data, "date", date_format) == ("date", "datetime")
