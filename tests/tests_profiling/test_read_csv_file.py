# Unit test read_csv_file

import re

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import read_csv_file

_HINT = (
    "Pass a text file in UTF-8 separated by ',', ';' or tabulators, with a "
    "header row and the same number of fields in every row."
)


def test_read_csv_file_output_when_readable(tmp_path):
    """
    Test that a well formed CSV file is read as pandas.read_csv reads it.
    """
    path = tmp_path / "data.csv"
    path.write_text("date,x\n2020-01-01,1.5\n2020-01-02,2.5\n")

    result = read_csv_file(path)

    expected = pd.DataFrame({"date": ["2020-01-01", "2020-01-02"], "x": [1.5, 2.5]})
    pd.testing.assert_frame_equal(result, expected)


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
            b"date,x\n2020-01-01,1\n2020-01-02,2,3,4\n2020-01-03,4\n",
            "Error tokenizing data. C error: Expected 2 fields in line 3, saw 4",
        ),
        (
            "date,x,name\n2020-01-01,1,caf\xe9\n".encode("latin-1"),
            "'utf-8' codec can't decode byte 0xe9 in position 28: invalid "
            "continuation byte",
        ),
    ],
    ids=["empty", "binary", "more fields than the header", "latin-1"],
)
@pytest.mark.parametrize("field", ["data", "exog"])
def test_read_csv_file_InvalidInputError_when_file_unreadable(
    tmp_path, content, reason, field
):
    """
    Test that a file that pandas cannot read as a CSV raises an
    InvalidInputError (still a ValueError) with the code 'data_unreadable',
    the first line of the pandas reason, the argument that named the file and
    a hint.
    """
    path = tmp_path / "data.csv"
    path.write_bytes(content)

    err_msg = re.escape(f"The CSV file '{path}' could not be read: {reason}")
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_file(path, field=field)

    assert isinstance(exc_info.value, ValueError)
    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == _HINT


def test_read_csv_file_field_is_data_by_default(tmp_path):
    """
    Test that the error names the argument `data` when no field is given.
    """
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")

    with pytest.raises(InvalidInputError) as exc_info:
        read_csv_file(str(path))

    assert exc_info.value.field == "data"


_ROW_FIELDS_HINT = (
    "Every row needs as many fields as the header. Write a copy of the file "
    "without the extra fields (or with a name for the first column in the "
    "header) and pass that copy; if the file is not yours, ask its owner "
    "before writing it."
)

_EMPTY_COLUMN_HINT = (
    "Write a copy of the file without that column (often the separator at "
    "the end of every line) and pass that copy; if the file is not yours, "
    "ask its owner before writing it."
)


@pytest.mark.parametrize(
    "text, fields, cause",
    [
        (
            "date,y\n2020-01-01,1,\n2020-02-01,2,\n2020-03-01,3,\n",
            3,
            "the rows end with separators that the header does not have",
        ),
        (
            "date,y\n2020-01-01,1,,\n2020-02-01,2,,\n2020-03-01,3,,\n",
            4,
            "the rows end with separators that the header does not have",
        ),
        (
            "date,y\n2020-01-01,1,9\n2020-02-01,2\n2020-03-01,3\n",
            3,
            "a field too many in the first row, or a header without a name "
            "for the first column",
        ),
        (
            "y\n2020-01-01,1\n2020-02-01,2\n2020-03-01,3\n",
            2,
            "a field too many in the first row, or a header without a name "
            "for the first column",
        ),
    ],
    ids=["separator at the end of every row", "two separators at the end",
         "field too many in the first row", "header one field short"],
)
@pytest.mark.parametrize("field", ["data", "exog"])
def test_read_csv_file_InvalidInputError_when_first_row_longer_than_header(
    tmp_path, text, fields, cause, field
):
    """
    Test that a file whose first row has more fields than its header, which
    pandas reads with the first column as the index and every other column
    moved one place, raises an InvalidInputError with the code
    'data_unreadable', the cause, the argument that named the file and a hint
    that asks the owner of the file before a copy is written, instead of
    reading a target without values or dates as an exogenous variable.
    """
    path = tmp_path / "data.csv"
    path.write_text(text)
    header = len(text.splitlines()[0].split(","))

    err_msg = re.escape(
        f"The CSV file '{path}' could not be read: its header has {header} "
        f"field{'s' if header != 1 else ''} and its first row {fields}, so the "
        f"first column would be read as the row labels and every other column "
        f"would move one place ({cause})."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_file(path, field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == _ROW_FIELDS_HINT


def test_read_csv_file_InvalidInputError_when_separator_at_the_end_of_rows_and_dialect(
    tmp_path,
):
    """
    Test that rows that end with a separator are detected in a file written
    with ';' and ',' too.
    """
    path = tmp_path / "data.csv"
    path.write_text("date;y\n2020-01-01;1,5;\n2020-02-01;2,5;\n2020-03-01;3,5;\n")

    with pytest.raises(InvalidInputError) as exc_info:
        read_csv_file(path)

    assert exc_info.value.code == "data_unreadable"
    assert "its header has 2 fields and its first row 3" in str(exc_info.value)
    assert exc_info.value.hint == _ROW_FIELDS_HINT


@pytest.mark.parametrize(
    "text, columns",
    [
        (
            "date,y,\n2020-01-01,1,\n2020-02-01,2,\n",
            "column 'Unnamed: 2' has",
        ),
        (
            "date,y,,\n2020-01-01,1,,\n2020-02-01,2,,\n",
            "columns 'Unnamed: 2', 'Unnamed: 3' have",
        ),
        (
            "date,,y\n2020-01-01,,1\n2020-02-01,,2\n",
            "column 'Unnamed: 1' has",
        ),
    ],
    ids=["separator at the end of every line", "two separators at the end",
         "empty column in the middle"],
)
def test_read_csv_file_InvalidInputError_when_column_without_name_and_values(
    tmp_path, text, columns
):
    """
    Test that a column without name and values (a separator at the end of
    every line, the header included) raises an InvalidInputError with the
    code 'data_unreadable' that names the column, instead of being profiled
    as an exogenous variable without values.
    """
    path = tmp_path / "data.csv"
    path.write_text(text)

    err_msg = re.escape(
        f"The CSV file '{path}' could not be read: {columns} no name in the "
        f"header and no values (often a separator at the end of every line, "
        f"the header included)."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_file(path, field="exog")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"
    assert exc_info.value.hint == _EMPTY_COLUMN_HINT


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            ",y\n2020-01-01,1\n2020-02-01,\n",
            pd.DataFrame(
                {"Unnamed: 0": ["2020-01-01", "2020-02-01"], "y": [1.0, None]}
            ),
        ),
        (
            "date,y,\n2020-01-01,1,\n2020-02-01,2,5\n",
            pd.DataFrame(
                {"date": ["2020-01-01", "2020-02-01"], "y": [1, 2],
                 "Unnamed: 2": [None, 5.0]}
            ),
        ),
    ],
    ids=["unnamed index of to_csv", "unnamed column with values"],
)
def test_read_csv_file_output_when_unnamed_column_holds_values(
    tmp_path, text, expected
):
    """
    Test that a column without name that holds values (the index written by
    `to_csv()`) is read as before.
    """
    path = tmp_path / "data.csv"
    path.write_text(text)

    pd.testing.assert_frame_equal(read_csv_file(path), expected)
