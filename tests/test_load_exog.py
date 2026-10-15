# Unit test load_exog

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai._utils import load_exog
from skforecast_ai.profiling.csv_dialect import EXOG_DIALECT_HINT
from skforecast_ai.exceptions import (
    DataContentError,
    DataNotFoundError,
    InvalidInputError,
)

from tests.fixtures_csv_dialect import df_dialect_exog, write_dialect

_EXPECTED = pd.DataFrame(
    {"temp": [1, 2]},
    index=pd.DatetimeIndex(["2023-01-01", "2023-01-02"], name="date"),
)


def test_load_exog_DataNotFoundError_when_file_missing(tmp_path):
    """
    Test that a path that is not a file raises `DataNotFoundError` naming
    the path.
    """
    path = tmp_path / "missing.csv"

    err_msg = re.escape(f"Exog CSV not found: '{path}'.")
    with pytest.raises(DataNotFoundError, match=err_msg):
        load_exog(path)


@pytest.mark.parametrize(
    "text, date_column, err_msg",
    [
        (
            "date,temp\n2023-01-01,1\n,2\n2023-01-03,3\n",
            None,
            "The dates of column 'date' have 1 empty cell(s), at row "
            "position(s) 1 (counting from 0, header excluded): every row needs "
            "a date. Fill in or drop those rows.",
        ),
        (
            "date,temp\n2023-03-25 00:00+01:00,1\n2023-03-27 00:00+02:00,2\n",
            None,
            "The dates of column 'date' mix time zones (+01:00, +02:00)",
        ),
        (
            "series,date,temp\na,2023-01-01,1\n",
            "fecha",
            "has no column 'fecha'; its columns are ['series', 'date', 'temp'].",
        ),
        (
            "series,date,temp\na,2023-01-01,1\n",
            "temp",
            "Column 'temp' of the exog CSV",
        ),
        (
            "date,temp\n2023-01-01,1\n2023-01-02 00:00:00,2\n2023/01/03,3\n",
            None,
            "The dates of column 'date' do not all follow the format of the "
            "first one ('%Y-%m-%d', read from '2023-01-01'), such as "
            "'2023-01-02 00:00:00': the generated script reads every date "
            "with the format of the first one. Write every date in the same "
            "format, such as '2023-01-02'.",
        ),
        (
            "date,temp\n2023-01-01,1\n2023-01-02 00:00:00,2\n2023/01/03,3\n",
            "date",
            "The dates of column 'date' do not all follow the format of the "
            "first one ('%Y-%m-%d', read from '2023-01-01'), such as "
            "'2023-01-02 00:00:00': the generated script reads every date "
            "with the format of the first one. Write every date in the same "
            "format, such as '2023-01-02'.",
        ),
    ],
    ids=["empty_date_cell", "mixed_offsets", "missing_date_column",
         "date_column_without_dates", "mixed_formats", "mixed_formats_named"],
)
def test_load_exog_InvalidInputError_when_dates_wrong(
    tmp_path, text, date_column, err_msg
):
    """
    Test that the dates are read as the CSV loader of the data reads them:
    an empty date cell and offsets that change raise, and so do a named date
    column that is missing or holds no dates, instead of a raw `KeyError`,
    and dates in mixed formats, which the generated script cannot read.
    """
    path = tmp_path / "exog.csv"
    path.write_text(text)

    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        load_exog(path, date_column=date_column)

    assert exc_info.value.field == "exog"


@pytest.mark.parametrize(
    "text, date_column",
    [
        ("date,temp\n2023-01-01,1\n2023-01-02,2\n", None),
        ("date,temp\n2023-01-02,2\n2023-01-01,1\n", None),
        ("h,date,temp\n1,2023-01-01,1\n2,2023-01-02,2\n", None),
        ("date,temp\n2023-01-01,1\n2023-01-02,2\n", "date"),
        ("date,temp\n20230102,2\n20230101,1\n", None),
    ],
    ids=["date_first", "unsorted", "date_not_first", "date_column",
         "integer_dates_first"],
)
def test_load_exog_output(tmp_path, text, date_column):
    """
    Test that the dates become the sorted index, whether they are the first
    column or another one (the first column is then left out, as
    `index_col=0` took it as the index in 0.3.1), or are named. Integer
    dates such as 20230101 in the first column are read as dates, as the CLI
    read them in 0.3.1.
    """
    path = tmp_path / "exog.csv"
    path.write_text(text)

    pd.testing.assert_frame_equal(load_exog(path, date_column=date_column), _EXPECTED)


@pytest.mark.parametrize(
    "date_column, expected",
    [
        (None, _EXPECTED),
        ("date", _EXPECTED.assign(**{"Unnamed: 0": [0, 1]})[["Unnamed: 0", "temp"]]),
    ],
    ids=["found", "named"],
)
def test_load_exog_output_when_row_numbers_first(tmp_path, date_column, expected):
    """
    Test that a first column of row numbers written by `to_csv()` is dropped
    when the dates are found in another column (`index_col=0` took it as the
    index in 0.3.1), and kept when the date column is named, as in 0.3.1.
    """
    path = tmp_path / "exog.csv"
    path.write_text(",date,temp\n0,2023-01-01,1\n1,2023-01-02,2\n")

    pd.testing.assert_frame_equal(load_exog(path, date_column=date_column), expected)


def test_load_exog_output_when_header_one_field_short_and_date_column(tmp_path):
    """
    Test that a header one field short with a named date column drops the
    first field, the row numbers, as `set_index(date_column)` did in 0.3.1.
    """
    path = tmp_path / "exog.csv"
    path.write_text("date,temp\n0,2023-01-01,1\n1,2023-01-02,2\n")

    pd.testing.assert_frame_equal(load_exog(path, date_column="date"), _EXPECTED)


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "temp,date\n1,2023-01-01\n0,2023-01-02\n",
            pd.DataFrame(
                {"temp": [1, 0]},
                index=pd.DatetimeIndex(["2023-01-01", "2023-01-02"], name="date"),
            ),
        ),
        (
            "id,date,temp\n101,2023-01-01,1\n105,2023-01-02,2\n",
            _EXPECTED,
        ),
    ],
    ids=["values_first", "row_ids_first"],
)
def test_load_exog_output_when_first_column_holds_values(tmp_path, text, expected):
    """
    Test that a first column of values is kept when the dates are in another
    column, and that a first column of increasing integers (row ids), which
    `index_col=0` took as the index in 0.3.1, is left out.
    """
    path = tmp_path / "exog.csv"
    path.write_text(text)

    pd.testing.assert_frame_equal(load_exog(path), expected)


def test_load_exog_output_when_integer_series_ids(tmp_path):
    """
    Test that, for long-format data, integer series ids in the first column
    are not read as dates (pandas reads 2001 as a year).
    """
    path = tmp_path / "exog.csv"
    path.write_text("store,date,price\n2001,2023-04-11,1\n2002,2023-04-11,2\n")

    expected = pd.DataFrame(
        {"store": [2001, 2002], "price": [1, 2]},
        index=pd.DatetimeIndex(["2023-04-11", "2023-04-11"], name="date"),
    )
    pd.testing.assert_frame_equal(
        load_exog(path, series_id_column="store"), expected
    )


def test_load_exog_output_when_integer_dates_and_text_dates(tmp_path):
    """
    Test that integer dates in the first column are the dates, as
    `index_col=0, parse_dates=True` read them in 0.3.1, also when a later
    column holds text dates (kept as a column).
    """
    path = tmp_path / "exog.csv"
    path.write_text(
        "date,temp,updated\n20230101,1,2022-12-15\n20230102,2,2022-12-15\n"
    )

    expected = _EXPECTED.assign(updated="2022-12-15")
    pd.testing.assert_frame_equal(load_exog(path), expected)


@pytest.mark.parametrize(
    "text, date_column, err_msg",
    [
        (
            "date,temp\n2023-01-01,1,,\n2023-01-02,2,,\n",
            None,
            "its header has 2 fields and its first row 4, so the first column "
            "would be read as the row labels and every other column would move "
            "one place (the rows end with separators that the header does not "
            "have).",
        ),
        (
            "date,temp\n2023-01-01,1,\n2023-01-02,2,\n",
            None,
            "its header has 2 fields and its first row 3, so the first column "
            "would be read as the row labels and every other column would move "
            "one place (the rows end with separators that the header does not "
            "have).",
        ),
        (
            "date,temp\n2023-01-01,1,\n2023-01-02,2,\n",
            "date",
            "its header has 2 fields and its first row 3",
        ),
        (
            "date,temp\n2023-01-01,1,9\n2023-01-02,2\n2023-01-03,3\n",
            None,
            "its header has 2 fields and its first row 3, so the first column "
            "would be read as the row labels and every other column would move "
            "one place (a field too many in the first row, or a header without "
            "a name for the first column).",
        ),
        (
            "date,temp,\n2023-01-01,1,\n2023-01-02,2,\n",
            None,
            "column 'Unnamed: 2' has no name in the header and no values (often "
            "a separator at the end of every line, the header included).",
        ),
    ],
    ids=["more_fields_than_header", "separator_at_row_end",
         "separator_at_row_end_named", "field_too_many_in_first_row",
         "separator_at_line_end_with_header"],
)
def test_load_exog_InvalidInputError_when_rows_longer_than_header(
    tmp_path, text, date_column, err_msg
):
    """
    Test that, as for the data, rows with more fields than the header that
    are not a header one field short (separators at the end of every row, a
    field too many only in the first row) and a column without name and
    values (a separator at the end of every line, the header included) raise
    with the code 'data_unreadable' and a hint, instead of a raw `TypeError`
    or future exogenous variables moved one column.
    """
    path = tmp_path / "exog.csv"
    path.write_text(text)

    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        load_exog(path, date_column=date_column)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"
    assert "ask its owner before writing it" in exc_info.value.hint


def test_load_exog_output_when_header_one_field_short(tmp_path):
    """
    Test that a header one field short (`to_csv(index_label=False)` or R's
    `write.csv`), which pandas reads with the dates as the index, keeps the
    dates as the index and every column.
    """
    path = tmp_path / "exog.csv"
    path.write_text("temp\n2023-01-01,1\n2023-01-02,2\n")

    expected = _EXPECTED.rename_axis(None)
    pd.testing.assert_frame_equal(load_exog(path), expected)


def test_load_exog_UserWarning_when_dates_with_empty_cell_before_date_column(
    tmp_path,
):
    """
    Test that, as for the data, a column of dates with an empty cell before a
    complete date column is left as a column, with a warning that names it,
    and the complete one becomes the index (the first column, row numbers,
    is left out).
    """
    path = tmp_path / "exog.csv"
    path.write_text(
        ",promo_end,date,temp\n0,2023-02-01,2023-01-01,1\n1,,2023-01-02,2\n"
    )

    warn_msg = re.escape(
        "The dates of column 'promo_end' have 1 empty cell(s), at row "
        "position(s) 1 (counting from 0, header excluded). Column 'date' is "
        "used as the date column instead; pass `date_column` to choose another "
        "one."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        result = load_exog(path)

    expected = _EXPECTED.assign(promo_end=["2023-02-01", np.nan])[
        ["promo_end", "temp"]
    ]
    pd.testing.assert_frame_equal(result, expected)


def test_load_exog_output_when_month_names(tmp_path):
    """
    Test that dates written with month names, which pandas parses one by
    one, are read as the CLI read them in 0.3.1, without a warning (warnings
    are errors in the tests).
    """
    path = tmp_path / "exog.csv"
    path.write_text("date,temp\nJuly 2008,1\nAugust 2008,2\n")

    expected = pd.DataFrame(
        {"temp": [1, 2]},
        index=pd.DatetimeIndex(["2008-07-01", "2008-08-01"], name="date"),
    )
    pd.testing.assert_frame_equal(load_exog(path), expected)


@pytest.mark.parametrize(
    "text",
    [
        "date,temp\n,\n2023-01-01,1\n,\n2023-01-02,2\n",
        "date,temp\n20230102,2\n,\n20230101,1\n",
    ],
    ids=["dates", "integer_dates"],
)
def test_load_exog_output_when_rows_of_separators(tmp_path, text):
    """
    Test that rows made only of separators, anywhere in the file, are
    dropped: they hold no date and no value (pandas reads the column with
    them as float). Integer dates, read again as `index_col=0`, stay with
    their rows.
    """
    path = tmp_path / "exog.csv"
    path.write_text(text)

    expected = _EXPECTED.astype({"temp": float})
    pd.testing.assert_frame_equal(load_exog(path), expected)


def test_load_exog_output_when_unnamed_dates_and_trailing_empty_row(tmp_path):
    """
    Test that unnamed dates (an index written by `to_csv()`) give an index
    without a name, and that a row of separators at the end of the file is
    dropped, as it holds no date.
    """
    path = tmp_path / "exog.csv"
    path.write_text(",temp\n2023-01-01,1\n2023-01-02,2\n,\n")

    expected = pd.DataFrame(
        {"temp": [1.0, 2.0]},
        index=pd.DatetimeIndex(["2023-01-01", "2023-01-02"]),
    )
    pd.testing.assert_frame_equal(load_exog(path), expected)


def test_load_exog_output_when_series_id_first(tmp_path):
    """
    Test that long-format future exogenous variables with the series id in
    the first column are indexed by their dates and keep the series id (the
    first column used to become the index, and the dates stayed text).
    """
    path = tmp_path / "exog.csv"
    path.write_text("series,date,temp\na,2023-01-01,1\nb,2023-01-01,2\n")

    expected = pd.DataFrame(
        {"series": ["a", "b"], "temp": [1, 2]},
        index=pd.DatetimeIndex(["2023-01-01", "2023-01-01"], name="date"),
    )
    pd.testing.assert_frame_equal(
        load_exog(path, series_id_column="series"), expected
    )


def test_load_exog_output_when_no_path():
    """
    Test that no path gives no future exogenous variables.
    """
    assert load_exog(None) is None


@pytest.mark.parametrize(
    "content, reason",
    [
        (b"", "No columns to parse from file"),
        (
            bytes(range(256)),
            "'utf-8' codec can't decode byte 0x80 in position 128: invalid "
            "start byte",
        ),
        (
            b"date,temp\n2023-01-01,1\n2023-01-02,2,3,4\n2023-01-03,4\n",
            "Error tokenizing data. C error: Expected 2 fields in line 3, saw 4",
        ),
        (
            "date,temp,name\n2023-01-01,1,caf\xe9\n".encode("latin-1"),
            "'utf-8' codec can't decode byte 0xe9 in position 31: invalid "
            "continuation byte",
        ),
    ],
    ids=["empty", "binary", "more fields than the header", "latin-1"],
)
def test_load_exog_InvalidInputError_when_file_unreadable(tmp_path, content, reason):
    """
    Test that a file that pandas cannot read as a CSV raises an
    InvalidInputError (a ValueError) with the code 'data_unreadable' and the
    field 'exog', and a hint.
    """
    path = tmp_path / "exog.csv"
    path.write_bytes(content)

    err_msg = re.escape(f"The CSV file '{path}' could not be read: {reason}")
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        load_exog(path)

    assert isinstance(exc_info.value, ValueError)
    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"
    assert exc_info.value.hint == (
        "Pass a text file in UTF-8 separated by ',', ';' or tabulators, with a "
        "header row and the same number of fields in every row."
    )


@pytest.mark.parametrize(
    "text, hint",
    [
        (
            "date,temp\n2023-01-01,1\n,2\n2023-01-03,3\n",
            "Every row needs a date: fill in or drop the rows without one.",
        ),
        (
            "date,temp\n2023-01-01T00:00:00+01:00,1\n2023-07-01T00:00:00+02:00,2\n",
            "Write every date in one time zone: in UTC for data recorded "
            "within the day, or without the time zone for daily or coarser "
            "data.",
        ),
    ],
    ids=["empty_date_cell", "mixed_offsets"],
)
@pytest.mark.parametrize(
    "date_column, advice",
    [
        (None, ""),
        ("date", ""),
    ],
    ids=["date_column: None", "date_column: date"],
)
def test_load_exog_hint_when_dates_wrong(tmp_path, text, hint, date_column, advice):
    """
    Test that the error of the dates of the file, with or without a named
    date column, carries the remedy as the hint, without the pandas calls
    that only apply in Python.
    """
    path = tmp_path / "exog.csv"
    path.write_text(text)

    with pytest.raises(InvalidInputError) as exc_info:
        load_exog(path, date_column=date_column)

    assert exc_info.value.hint == hint + advice


def test_load_exog_DataContentError_when_date_column_missing(tmp_path):
    """
    Test that the error for a file of future exogenous variables without
    the date column is a DataContentError, the class that tells a problem
    of the content of the file from an argument to correct, with the code
    and the field of an InvalidInputError.
    """
    path = tmp_path / "exog.csv"
    path.write_text("day,promo\n2023-01-01,1\n")

    err_msg = re.escape(
        f"The exog CSV '{path}' has no column 'date'; its columns are "
        f"['day', 'promo']."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        load_exog(path, date_column="date")

    assert type(exc_info.value) is DataContentError
    assert (exc_info.value.code, exc_info.value.field) == (
        "invalid_argument", "exog"
    )


@pytest.mark.parametrize(
    "name",
    ["semicolon_comma", "semicolon_dot", "tab_dot", "tab_comma", "tsv",
     "gz_comma_dot", "gz_semicolon_comma"],
)
def test_load_exog_output_when_file_has_another_dialect(tmp_path, name):
    """
    Test that an exog file with ';' or tabulators, a decimal comma, a '.tsv'
    extension or gzip compression gives the same frame as the comma file.
    """
    path = write_dialect(tmp_path, df_dialect_exog, name)
    comma_path = tmp_path / "us.csv"
    df_dialect_exog.to_csv(comma_path, index=False)

    result = load_exog(path)

    expected = pd.DataFrame(
        {"temp": [1.5, 2.25, 3.5, 4.75, 5.5, 6.25, 7.5, 8.75, 9.5, 10.25]},
        index=pd.date_range("2023-03-02", periods=10, freq="D", name="date"),
    )
    pd.testing.assert_frame_equal(result, expected, check_freq=False)
    pd.testing.assert_frame_equal(result, load_exog(comma_path), check_freq=False)


def test_load_exog_output_when_dates_are_the_first_column_and_dialect_is_semicolon(
    tmp_path,
):
    """
    Test that the index of an exog file written with `to_csv()` (dates in the
    first column, not named) is read with the dialect of the file.
    """
    path = tmp_path / "eu.csv"
    path.write_text("date;temp\n2023-01-01;1,5\n2023-01-02;2,5\n")

    result = load_exog(path)

    expected = pd.DataFrame(
        {"temp": [1.5, 2.5]},
        index=pd.DatetimeIndex(["2023-01-01", "2023-01-02"], name="date"),
    )
    pd.testing.assert_frame_equal(result, expected, check_freq=False)


def test_load_exog_InvalidInputError_when_separator_is_ambiguous(tmp_path):
    """
    Test that an exog file whose header reads with ',' and with ';' raises
    an InvalidInputError with the code 'data_unreadable', the field 'exog'
    and the hint of the exog file.
    """
    path = tmp_path / "exog.csv"
    path.write_text("date;temp,x\n2023-01-01;1,5\n2023-01-02;2,5\n")

    err_msg = re.escape(
        f"The separator of the CSV file '{path}' cannot be told: its header "
        f"reads with ',' (2 columns) and ';' (2 columns)."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        load_exog(path)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"
    assert exc_info.value.hint == EXOG_DIALECT_HINT
    assert EXOG_DIALECT_HINT == (
        "Write the file with ',' as separator and '.' as decimal mark, as "
        "`DataFrame.to_csv()` writes it, without ';' or tabulators in the "
        "column names."
    )


def test_load_exog_InvalidInputError_when_decimal_is_ambiguous(tmp_path):
    """
    Test that an exog file with numbers written as '1,5' and as '2.5' raises
    an InvalidInputError with the field 'exog' and the exog hint.
    """
    path = tmp_path / "exog.csv"
    path.write_text("date;a;b\n2023-01-01;1,5;2.5\n")

    err_msg = re.escape(
        f"The decimal mark of the CSV file '{path}' cannot be told: it holds "
        f"numbers written with ',' (such as '1,5') and with '.' (such as "
        f"'2.5')."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        load_exog(path)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"
    assert exc_info.value.hint == EXOG_DIALECT_HINT


def test_load_exog_output_when_integer_dates_and_dialect_is_semicolon(tmp_path):
    """
    Test that integer dates (20230101) of an exog file with ';' and a decimal
    comma are read as dates, the index being read again with the dialect.
    """
    path = tmp_path / "eu.csv"
    path.write_text("date;temp\n20230101;1,5\n20230102;2,5\n")

    result = load_exog(path)

    expected = pd.DataFrame(
        {"temp": [1.5, 2.5]},
        index=pd.DatetimeIndex(["2023-01-01", "2023-01-02"], name="date"),
    )
    pd.testing.assert_frame_equal(result, expected, check_freq=False)
