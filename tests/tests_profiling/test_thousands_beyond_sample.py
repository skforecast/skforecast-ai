# Unit test thousands_beyond_sample

import re

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.csv_dialect import (
    DOTTED_VALUES_HINT,
    EXOG_DIALECT_HINT,
    THOUSANDS_HINT,
)
from skforecast_ai.profiling.data_profile import thousands_beyond_sample


def _read(tmp_path, text: str, index_col=None) -> tuple:
    """
    Write `text` to a ';' file and return its path and its content read with
    '.' as decimal mark and no thousands separator.
    """
    path = tmp_path / "data.csv"
    path.write_text(text)

    return path, pd.read_csv(path, sep=";", index_col=index_col)


@pytest.mark.parametrize(
    "text",
    [
        "date;y\n2020-01-01;870\n2020-01-02;945\n2020-01-03;1.020\n",
        "id;date;y\na;2020-01-01;870\nb;2020-01-01;1.020\nb;2020-01-02;2.015\n",
        "date;y;x\n2020-01-01;-870;1\n2020-01-02;-1.020;2\n",
    ],
    ids=["one series", "long format sorted by series", "negative numbers"],
)
def test_thousands_beyond_sample_output_point_when_column_mixes_thousands(
    tmp_path, text
):
    """
    Test that a column read as numbers with decimals that holds whole numbers
    of at most three digits next to numbers such as '1.020' is to be read
    again with '.' as thousands separator.
    """
    path, data = _read(tmp_path, text)

    assert thousands_beyond_sample(path, data, "data.csv", "data", ";") == "."


@pytest.mark.parametrize(
    "text",
    [
        "date;y\n2020-01-01;870\n2020-01-02;945\n",
        "date;y\n2020-01-01;0.5\n2020-01-02;12.25\n",
        "date;y;x\n2020-01-01;1.020;0.5\n2020-01-02;1500;2.5\n",
        "date;y\n2020-01-01;870\n2020-01-02;a.b\n",
    ],
    ids=[
        "whole numbers only",
        "numbers with point decimals",
        "three decimals next to point decimals",
        "column read as text",
    ],
)
def test_thousands_beyond_sample_output_None_when_no_thousands(tmp_path, text):
    """
    Test that nothing changes for a file without numbers that read as
    thousands, or whose '.' is the decimal mark of another number ('0.5').
    """
    path, data = _read(tmp_path, text)

    assert thousands_beyond_sample(path, data, "data.csv", "data", ";") is None


def test_thousands_beyond_sample_output_None_when_first_column_is_the_index(
    tmp_path,
):
    """
    Test that a frame whose first column was read as its index (a header
    one field short) is not looked at.
    """
    path, data = _read(
        tmp_path, "y\n2020-01-01;870\n2020-01-02;1.020\n", index_col=0
    )

    assert thousands_beyond_sample(path, data, "data.csv", "data", ";") is None


@pytest.mark.parametrize(
    "field, hint",
    [("data", THOUSANDS_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_thousands_beyond_sample_InvalidInputError_when_thousands_are_ambiguous(
    tmp_path, field, hint
):
    """
    Test that numbers whose only '.' is followed by three digits, next to
    whole numbers written without separator above 999, raise an
    InvalidInputError with the code 'data_unreadable' and the hint of the
    argument.
    """
    path, data = _read(tmp_path, "date;y\n2020-01-01;1500\n2020-01-02;1.020\n")

    err_msg = re.escape(
        "The thousands separator of the CSV file 'data.csv' cannot be told: "
        "its numbers with a '.' (such as '1.020') read both as thousands and "
        "as numbers with three decimals."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        thousands_beyond_sample(path, data, "data.csv", field, ";")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


@pytest.mark.parametrize(
    "text, other",
    [
        ("date;y;x\n2020-01-01;870;1\n2020-01-02;1.020;0.5\n", "0.5"),
        ("date;y\n15.01.2020;870\n16.01.2020;1.020\n", "15.01.2020"),
    ],
    ids=["point decimals in another column", "dates with points"],
)
@pytest.mark.parametrize(
    "field, hint",
    [("data", DOTTED_VALUES_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_thousands_beyond_sample_InvalidInputError_when_point_is_also_elsewhere(
    tmp_path, text, other, field, hint
):
    """
    Test that a column of thousands next to values whose '.' does not
    separate thousands raises an InvalidInputError with the code
    'data_unreadable', an example of each and the hint of the argument.
    """
    path, data = _read(tmp_path, text)

    err_msg = re.escape(
        f"The CSV file 'data.csv' cannot be read: it holds numbers with '.' "
        f"between the thousands (such as '1.020') and values with a '.' that "
        f"does not separate thousands (such as '{other}'), which pandas would "
        f"read as numbers without it."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        thousands_beyond_sample(path, data, "data.csv", field, ";")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.hint == hint
