# Unit test read_csv_file

import re

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import read_csv_file

_HINT = (
    "Pass a comma-separated text file in UTF-8 with a header row, and the "
    "same number of fields in every row."
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
