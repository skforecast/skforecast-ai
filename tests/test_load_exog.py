# Unit test load_exog

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai._utils import load_exog
from skforecast_ai.schemas import FutureExogFile
from skforecast_ai.profiling.csv_dialect import ENCODING_HINT, EXOG_DIALECT_HINT
from skforecast_ai.exceptions import (
    DataContentError,
    DataNotFoundError,
    InvalidInputError,
)

from tests.fixtures_csv_dialect import (
    df_dialect_cp1252_exog,
    df_dialect_exog,
    write_cp1252,
    write_dialect,
)

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
    Test that, for long-format data, series ids written as integers in the
    first column are read as text, as the ids of the data, and not as dates
    (pandas reads '2001' as a year).
    """
    path = tmp_path / "exog.csv"
    path.write_text("store,date,price\n2001,2023-04-11,1\n2002,2023-04-11,2\n")

    expected = pd.DataFrame(
        {"store": ["2001", "2002"], "price": [1, 2]},
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
            b"date,temp\n2023-01-01,1\n2023-01-02,2,3,4\n2023-01-03,4\n",
            "Error tokenizing data. C error: Expected 2 fields in line 3, saw 4",
        ),
    ],
    ids=["empty", "more fields than the header"],
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


@pytest.mark.parametrize(
    "text",
    [
        "date;temp\n2023-01-01;870\n2023-01-02;1.020\n2023-01-03;1.705\n",
        "date;temp\n2023-01-01;870,0\n2023-01-02;1.020,0\n2023-01-03;1.705,0\n",
    ],
    ids=["whole numbers", "decimal comma"],
)
def test_load_exog_output_when_point_separates_thousands(tmp_path, text):
    """
    Test that an exog file with '.' between thousands is read as the amounts
    it holds, as the data are.
    """
    path = tmp_path / "exog.csv"
    path.write_text(text)

    result = load_exog(path)

    np.testing.assert_array_equal(result["temp"].to_numpy(), [870, 1020, 1705])
    pd.testing.assert_index_equal(
        result.index,
        pd.DatetimeIndex(["2023-01-01", "2023-01-02", "2023-01-03"], name="date"),
    )


def test_load_exog_InvalidInputError_when_thousands_are_ambiguous(tmp_path):
    """
    Test that an exog file whose numbers with a '.' all read as thousands
    and as three decimals raises an InvalidInputError with the field 'exog'
    and the exog hint.
    """
    path = tmp_path / "exog.csv"
    path.write_text("date;temp\n2023-01-01;1.870\n2023-01-02;1.020\n")

    err_msg = re.escape(
        f"The thousands separator of the CSV file '{path}' cannot be told: its "
        f"numbers with a '.' (such as '1.870') read both as thousands and as "
        f"numbers with three decimals."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        load_exog(path)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"
    assert exc_info.value.hint == EXOG_DIALECT_HINT


# Seven days of a short horizon written day first: every date reads both day
# first and month first, and only the reading day first is regular (daily).
_DAY_FIRST_BODY = (
    "01/02/2021,1\n02/02/2021,2\n03/02/2021,3\n04/02/2021,4\n05/02/2021,5\n"
    "06/02/2021,6\n07/02/2021,7\n"
)
_DAY_FIRST_DATES = [
    "2021-02-01", "2021-02-02", "2021-02-03", "2021-02-04", "2021-02-05",
    "2021-02-06", "2021-02-07",
]


@pytest.mark.parametrize(
    "header, date_column, index_name",
    [
        ("date,temp", "date", "date"),
        ("date,temp", None, "date"),
        (",temp", None, None),
        ("temp", None, None),
    ],
    ids=["named", "found", "unnamed", "header_one_field_short"],
)
def test_load_exog_output_when_date_format_day_first(
    tmp_path, header, date_column, index_name
):
    """
    Test that, with the format of the dates of the data, a short horizon
    whose dates read both ways ('01/02/2021' to '07/02/2021') is read as the
    first to the seventh of February, without a warning, whether the date
    column is named, found, unnamed (an index written by `to_csv()`) or the
    index of a header one field short, and that the format is kept in
    `attrs['exog_file']`.
    """
    path = tmp_path / "exog.csv"
    path.write_text(f"{header}\n{_DAY_FIRST_BODY}")

    result = load_exog(path, date_column=date_column, date_format="%d/%m/%Y")

    expected = pd.DataFrame(
        {"temp": [1, 2, 3, 4, 5, 6, 7]},
        index=pd.DatetimeIndex(_DAY_FIRST_DATES, name=index_name),
    )
    pd.testing.assert_frame_equal(result, expected)
    exog_file = result.attrs["exog_file"]
    assert (exog_file.date_format, exog_file.encoding) == ("%d/%m/%Y", "utf-8")


@pytest.mark.parametrize("date_column", [None, "date"], ids=["found", "named"])
def test_load_exog_output_when_no_date_format_and_only_one_reading_is_regular(
    tmp_path, date_column
):
    """
    Test that, without a format of the data to decide, dates that read both
    ways are read in the only order in which they have a regular frequency
    (day first, daily), with a UserWarning that names the file, says so and
    gives the remedy for the other order: dates in ISO 8601.
    """
    path = tmp_path / "exog.csv"
    path.write_text(f"date,temp\n{_DAY_FIRST_BODY}")

    warn_msg = re.escape(
        f"Exog CSV '{path}': The dates of column 'date' read both day first "
        f"and month first (no day is after the 12th): they were read day "
        f"first, the only order in which they have a regular frequency "
        f"('D'), so '01/02/2021' is '2021-02-01' and not '2021-01-02'. If "
        f"they are written month first, write them in ISO 8601 (such as "
        f"'2021-01-02')."
    )
    with pytest.warns(UserWarning, match="^" + warn_msg + "$"):
        result = load_exog(path, date_column=date_column)

    expected = pd.DataFrame(
        {"temp": [1, 2, 3, 4, 5, 6, 7]},
        index=pd.DatetimeIndex(_DAY_FIRST_DATES, name="date"),
    )
    pd.testing.assert_frame_equal(result, expected)
    exog_file = result.attrs["exog_file"]
    assert (exog_file.date_format, exog_file.encoding) == ("%d/%m/%Y", "utf-8")


@pytest.mark.parametrize(
    "date_format", [None, "%Y%m%d"], ids=lambda dt: f"date_format: {dt}"
)
@pytest.mark.parametrize("date_column", [None, "date"], ids=["found", "named"])
def test_load_exog_DataContentError_when_dates_read_in_both_orders(
    tmp_path, date_column, date_format
):
    """
    Test that dates that read both day first and month first, regular in
    both orders (three months: monthly day first, daily month first) and
    with no format of the data that decides (none, or whole numbers),
    raise a DataContentError with the code 'data_unreadable', the field
    'exog' and the hint that asks for dates in ISO 8601.
    """
    path = tmp_path / "exog.csv"
    path.write_text("date,temp\n01/01/2021,1\n01/02/2021,2\n01/03/2021,3\n")

    err_msg = re.escape(
        f"Exog CSV '{path}': The dates of column 'date' read both day first "
        f"and month first: no day is after the 12th, so '01/02/2021' may be "
        f"'2021-02-01' or '2021-01-02', and both readings have a regular "
        f"frequency ('MS' day first and 'D' month first), so the order is not "
        f"guessed. Write them in ISO 8601, which reads one way only."
    )
    with pytest.raises(DataContentError, match="^" + err_msg + "$") as exc_info:
        load_exog(path, date_column=date_column, date_format=date_format)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"
    assert exc_info.value.hint == (
        "Write the dates of the future exogenous values in ISO 8601, such as "
        "'2024-01-31', which reads one way only."
    )


def test_load_exog_output_when_date_format_and_unsorted_dates(tmp_path):
    """
    Test that dates written day first become the sorted index, as the dates
    in ISO 8601.
    """
    path = tmp_path / "exog.csv"
    path.write_text("date,temp\n13/02/2021,3\n01/02/2021,1\n02/02/2021,2\n")

    result = load_exog(path, date_format="%d/%m/%Y")

    expected = pd.DataFrame(
        {"temp": [1, 2, 3]},
        index=pd.DatetimeIndex(
            ["2021-02-01", "2021-02-02", "2021-02-13"], name="date"
        ),
    )
    pd.testing.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "date_format", [None, "%Y%m%d", "%d/%m/%Y"], ids=lambda dt: f"date_format: {dt}"
)
@pytest.mark.parametrize("date_column", [None, "date"], ids=["found", "named"])
def test_load_exog_output_when_integer_dates(tmp_path, date_column, date_format):
    """
    Test that integer dates (20210201) are dates of the format '%Y%m%d',
    kept in `attrs`, whatever the format of the dates of the data, also when
    the date column is named.
    """
    path = tmp_path / "exog.csv"
    path.write_text("date,temp\n20210202,2\n20210201,1\n")

    result = load_exog(path, date_column=date_column, date_format=date_format)

    expected = pd.DataFrame(
        {"temp": [1, 2]},
        index=pd.DatetimeIndex(["2021-02-01", "2021-02-02"], name="date"),
    )
    pd.testing.assert_frame_equal(result, expected)
    exog_file = result.attrs["exog_file"]
    assert (exog_file.date_format, exog_file.encoding) == ("%Y%m%d", "utf-8")


def test_load_exog_output_when_date_format_and_semicolon_dialect(tmp_path):
    """
    Test that the dates of an exog file with ';' and a decimal comma that
    read both ways are read in the order of the format of the data, the
    values with the dialect of the file.
    """
    path = tmp_path / "eu.csv"
    path.write_text("date;temp\n01/02/2021;1,5\n02/02/2021;2,5\n")

    result = load_exog(path, date_format="%d/%m/%Y")

    expected = pd.DataFrame(
        {"temp": [1.5, 2.5]},
        index=pd.DatetimeIndex(["2021-02-01", "2021-02-02"], name="date"),
    )
    pd.testing.assert_frame_equal(result, expected)


def test_load_exog_output_when_date_format_and_series_id_column(tmp_path):
    """
    Test that long-format future exogenous variables are indexed by their
    dates read in the order of the format of the data (sorted by date), the
    series ids staying text.
    """
    path = tmp_path / "exog.csv"
    path.write_text(
        "series,date,temp\n001,01/02/2021,1\n001,02/02/2021,2\n"
        "002,01/02/2021,3\n002,02/02/2021,4\n"
    )

    result = load_exog(path, series_id_column="series", date_format="%d/%m/%Y")

    expected = pd.DataFrame(
        {"series": ["001", "002", "001", "002"], "temp": [1, 3, 2, 4]},
        index=pd.DatetimeIndex(
            ["2021-02-01", "2021-02-01", "2021-02-02", "2021-02-02"], name="date"
        ),
    )
    pd.testing.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "date_format", [None, "%d/%m/%Y", "%m/%d/%Y"], ids=lambda dt: f"date_format: {dt}"
)
@pytest.mark.parametrize("date_column", [None, "date"], ids=["found", "named"])
def test_load_exog_output_when_iso_dates_and_data_in_another_format(
    tmp_path, date_column, date_format
):
    """
    Test that an exog file saved with `to_csv()` from a frame indexed by its
    dates, which writes them in ISO 8601, is read whatever the format of the
    dates of the data (day first or month first): the format of the file is
    its own, and it needs none (`attrs` holds None).
    """
    path = tmp_path / "exog.csv"
    pd.DataFrame(
        {"temp": [1, 2]},
        index=pd.DatetimeIndex(["2021-02-01", "2021-02-02"], name="date"),
    ).to_csv(path)

    result = load_exog(path, date_column=date_column, date_format=date_format)

    expected = pd.DataFrame(
        {"temp": [1, 2]},
        index=pd.DatetimeIndex(["2021-02-01", "2021-02-02"], name="date"),
    )
    pd.testing.assert_frame_equal(result, expected)
    exog_file = result.attrs["exog_file"]
    assert (exog_file.date_format, exog_file.encoding) == (None, "utf-8")


@pytest.mark.parametrize("date_column", [None, "date"], ids=["found", "named"])
def test_load_exog_output_when_day_first_dates_and_data_in_iso(
    tmp_path, date_column
):
    """
    Test that an exog file written day first with a day after the 12th is
    read day first for data whose dates are in ISO 8601 (no format), with
    its own format kept in `attrs`.
    """
    path = tmp_path / "exog.csv"
    path.write_text("date,temp\n12/02/2021,1\n13/02/2021,2\n")

    result = load_exog(path, date_column=date_column)

    expected = pd.DataFrame(
        {"temp": [1, 2]},
        index=pd.DatetimeIndex(["2021-02-12", "2021-02-13"], name="date"),
    )
    pd.testing.assert_frame_equal(result, expected)
    exog_file = result.attrs["exog_file"]
    assert (exog_file.date_format, exog_file.encoding) == ("%d/%m/%Y", "utf-8")


def test_load_exog_DataContentError_when_dates_in_more_than_one_format(tmp_path):
    """
    Test that dates written in two formats ('01/02/2021' and '2021-02-02')
    raise the DataContentError of the dates of the data written in more
    than one format, with a named date column: the format of the data does
    not apply to them.
    """
    path = tmp_path / "exog.csv"
    path.write_text("date,temp\n01/02/2021,1\n2021-02-02,2\n")

    err_msg = re.escape(
        f"Exog CSV '{path}': The dates of column 'date' do not all follow the "
        f"format of the first one ('%m/%d/%Y', read from '01/02/2021'), such "
        f"as '2021-02-02': the generated script reads every date with the "
        f"format of the first one. Write every date in the same format, such "
        f"as '2021-02-02'."
    )
    with pytest.raises(DataContentError, match="^" + err_msg + "$") as exc_info:
        load_exog(path, date_column="date", date_format="%d/%m/%Y")

    assert exc_info.value.field == "exog"


@pytest.mark.parametrize(
    "date_column", [None, "fecha"], ids=["found", "named"]
)
def test_load_exog_output_when_file_is_cp1252(tmp_path, date_column):
    """
    Test that future values saved by Excel on Windows in Spanish (cp1252,
    ';', accents in the categories, dates day first that read in both
    orders) are read as cp1252, their own encoding, kept in `attrs` with
    their date format, with a warning that the encoding cannot be checked.
    """
    path = write_cp1252(tmp_path, df_dialect_cp1252_exog, name="exog.csv")

    warn_msg = re.escape(
        f"Exog CSV '{path}': The CSV file is not UTF-8: it was read as cp1252 "
        f"(Windows-1252), the encoding of the CSV files that Excel saves on "
        f"Windows, and the generated script reads it so. That encoding cannot "
        f"be checked: if column names or categories show wrong characters, "
        f"save the file as UTF-8 and pass it again."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        result = load_exog(path, date_column=date_column, date_format="%d/%m/%Y")

    expected = pd.DataFrame(
        {"zona": df_dialect_cp1252_exog["zona"].to_numpy()},
        index=pd.DatetimeIndex(
            pd.date_range("2023-03-02", periods=10, freq="D"), name="fecha"
        ),
    )
    pd.testing.assert_frame_equal(result, expected, check_freq=False)
    exog_file = result.attrs["exog_file"]
    assert (exog_file.date_format, exog_file.encoding) == ("%d/%m/%Y", "cp1252")


def test_load_exog_InvalidInputError_when_file_is_utf16(tmp_path):
    """
    Test that future values in UTF-16 raise an InvalidInputError with the
    code 'data_unreadable', the field 'exog' and the hint that asks for a
    copy in UTF-8.
    """
    path = tmp_path / "exog.csv"
    df_dialect_exog.to_csv(path, index=False, encoding="utf-16")

    err_msg = re.escape(
        f"The CSV file '{path}' could not be read: it is written in UTF-16"
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        load_exog(path)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"
    assert exc_info.value.hint == ENCODING_HINT


@pytest.mark.parametrize(
    "text, encoding, dialect",
    [
        ("date,temp\n2021-02-01,1.5\n2021-02-02,2.5\n", "utf-8", {}),
        ("date;temp\n2021-02-01;1.5\n2021-02-02;2.5\n", "utf-8", {"sep": ";"}),
        ("date\ttemp\n2021-02-01\t1.5\n2021-02-02\t2.5\n", "utf-8", {"sep": "\t"}),
        (
            "date;temp\n2021-02-01;1,5\n2021-02-02;2,5\n",
            "utf-8",
            {"sep": ";", "decimal": ","},
        ),
        (
            "date;temp\n2021-02-01;870\n2021-02-02;1.020\n",
            "utf-8",
            {"sep": ";", "decimal": ",", "thousands": "."},
        ),
        ("date,año\n2021-02-01,1.5\n2021-02-02,2.5\n", "cp1252", {}),
        (
            "date,temp\n01/02/2021,1.5\n13/02/2021,2.5\n",
            "utf-8",
            {"date_format": "%d/%m/%Y"},
        ),
        (
            "fecha;año\n01/02/2021;1.705,5\n13/02/2021;870,25\n",
            "cp1252",
            {
                "sep": ";", "decimal": ",", "thousands": ".",
                "encoding": "cp1252", "date_format": "%d/%m/%Y",
            },
        ),
    ],
    ids=[
        "defaults", "sep", "tab", "decimal", "thousands", "encoding",
        "date_format", "all",
    ],
)
def test_load_exog_output_when_file_dialect_kept_in_attrs(
    tmp_path, text, encoding, dialect
):
    """
    Test that the path of the file and how it is written (separator,
    decimal mark, thousands separator, encoding and format of the dates),
    each one on its own and all together as the Excel in Spanish saves
    them, are kept in `attrs['exog_file']`, the file the generated script
    reads with them. A file in cp1252 is read so, with its warning.
    """
    path = tmp_path / "exog.csv"
    path.write_bytes(text.encode(encoding))
    if encoding == "cp1252":
        with pytest.warns(UserWarning, match="it was read as cp1252"):
            result = load_exog(path)
        dialect = {"encoding": "cp1252", **dialect}
    else:
        result = load_exog(path)

    expected = FutureExogFile(
        path        = str(path),
        date_column = "fecha" if "fecha" in text else "date",
        **dialect,
    )
    assert result.attrs == {"exog_file": expected}


@pytest.mark.parametrize(
    "date_column, text, expected_column",
    [
        (None, "fecha,temp\n2021-02-01,1\n2021-02-02,2\n", "fecha"),
        ("fecha", "fecha,temp\n2021-02-01,1\n2021-02-02,2\n", "fecha"),
        (None, ",temp\n2021-02-01,1\n2021-02-02,2\n", "Unnamed: 0"),
        (None, ",date,temp\n0,2021-02-01,1\n1,2021-02-02,2\n", "date"),
    ],
    ids=["found", "named", "unnamed", "after_row_numbers"],
)
def test_load_exog_output_when_date_column_kept_in_attrs(
    tmp_path, date_column, text, expected_column
):
    """
    Test that the column of the file that holds the dates, found or named,
    is kept in `attrs['exog_file']`, so the script names it as the date
    column of the data when it is another one.
    """
    path = tmp_path / "exog.csv"
    path.write_text(text)

    result = load_exog(path, date_column=date_column)

    assert result.attrs["exog_file"].date_column == expected_column


@pytest.mark.parametrize(
    "text, expected",
    [
        ("date,temp\n2023-01-01,1\n2023-01-02,2\n", False),
        ("date,temp\n2023-01-01,1\n2023-01-02,2\n,\n,\n", True),
        ("date;temp\n;\n2023-01-01;1\n2023-01-02;2\n", True),
    ],
    ids=["none", "trailing", "first"],
)
def test_load_exog_output_when_blank_rows_kept_in_attrs(tmp_path, text, expected):
    """
    Test that whether the file has rows made only of separators (a
    spreadsheet saved as CSV), which are dropped, is kept in
    `attrs['exog_file']`, so the script drops them too.
    """
    path = tmp_path / "exog.csv"
    path.write_text(text)

    result = load_exog(path)

    assert result.attrs["exog_file"].blank_rows is expected
