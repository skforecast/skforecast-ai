# Unit test decimal_after_sample

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.csv_dialect import DIALECT_HINT, EXOG_DIALECT_HINT
from skforecast_ai.profiling.data_profile import decimal_after_sample


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame({"date": ["2020-01-01", "2020-01-02"], "y": [1, 2]}),
        pd.DataFrame({"date": ["2020-01-01", "2020-01-02"], "y": [1.5, 2.0]}),
        pd.DataFrame({"y": [1, 2], "name": ["a,b", "1,5 kg"]}),
        pd.DataFrame({"y": [1.0, np.nan], "name": ["x", None]}),
    ],
    ids=["integers", "numbers with a point", "text with commas", "missing values"],
)
def test_decimal_after_sample_output_point_when_no_number_with_comma(frame):
    """
    Test that the decimal mark stays '.' when no column read as text holds
    numbers written with ','.
    """
    result = decimal_after_sample(frame, "data.csv", "data")

    assert result == "."


@pytest.mark.parametrize(
    "values",
    [["1", "2", "2,5"], ["1", " 0,125 ", "3"], ["1,234", "12,5", None]],
    ids=["one decimal", "spaces around", "thousands shaped and another"],
)
def test_decimal_after_sample_output_comma_when_text_column_has_numbers(values):
    """
    Test that the decimal mark is ',' when a column read as text holds a
    number written with ',' that does not read as thousands.
    """
    frame = pd.DataFrame({"y": [1, 2, 3], "x": values})

    result = decimal_after_sample(frame, "data.csv", "data")

    assert result == ","


@pytest.mark.parametrize(
    "values",
    [
        ["870", "1.705,11"],
        ["870", "1.234.567"],
        ["870", " -1.705,11 "],
        ["1.705,11", None],
    ],
    ids=["thousands and decimals", "two groups", "sign and spaces", "missing value"],
)
@pytest.mark.parametrize("sep", [";", "\t"])
def test_decimal_after_sample_output_comma_when_text_column_has_dot_thousands(
    values, sep
):
    """
    Test that the decimal mark is ',' when a column read as text holds a
    number with '.' between thousands that cannot read with '.' as decimal
    mark ('1.705,11', '1.234.567'), next to a column of integers, with ';'
    and with a tabulator (its only-thousands check does not fire for them).
    """
    frame = pd.DataFrame({"y": [1, 2], "x": values})

    result = decimal_after_sample(frame, "data.csv", "data", sep=sep)

    assert result == ","


@pytest.mark.parametrize("sep", [";", "\t"])
def test_decimal_after_sample_output_point_when_number_reads_as_float(sep):
    """
    Test that a text column holding '1.705', which is a valid float with '.'
    as decimal mark, does not make the decimal mark ','.
    """
    frame = pd.DataFrame({"y": [1, 2], "x": ["870", "1.705"]})

    result = decimal_after_sample(frame, "data.csv", "data", sep=sep)

    assert result == "."


@pytest.mark.parametrize(
    "field, hint",
    [("data", DIALECT_HINT), ("exog", EXOG_DIALECT_HINT)],
    ids=lambda dt: f"{dt[:4]}",
)
def test_decimal_after_sample_InvalidInputError_when_both_marks(field, hint):
    """
    Test that numbers written with ',' in a column read as text and numbers
    with decimals in a numeric column raise an InvalidInputError with the code
    'data_unreadable', the argument that named the file and its hint.
    """
    frame = pd.DataFrame({"y": [1.0, 2.75, 3.0], "x": ["1", "2,5", "3"]})

    err_msg = re.escape(
        "The decimal mark of the CSV file 'data.csv' cannot be told: it holds "
        "numbers written with ',' (such as '2,5') and with '.' (such as "
        "'2.75')."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        decimal_after_sample(frame, "data.csv", field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


def test_decimal_after_sample_InvalidInputError_when_only_thousands():
    """
    Test that numbers with a ',' that all read as thousands too raise an
    InvalidInputError with the code 'data_unreadable' when the file is
    separated by tabulators.
    """
    frame = pd.DataFrame({"y": [1, 2, 3], "x": ["1", "1,234", "20,500"]})

    err_msg = re.escape(
        "The decimal mark of the CSV file 'data.csv' cannot be told: its "
        "numbers with a ',' (such as '1,234') read both as thousands and as "
        "numbers with three decimals."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        decimal_after_sample(frame, "data.csv", "data", sep="\t")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == DIALECT_HINT


def test_decimal_after_sample_output_comma_when_semicolon_and_only_thousands():
    """
    Test that in a file separated by ';' numbers with a ',' that all read as
    thousands too are numbers with three decimals: the decimal mark is ','.
    """
    frame = pd.DataFrame({"y": [1, 2, 3], "x": ["1", "1,234", "20,500"]})

    result = decimal_after_sample(frame, "data.csv", "data", sep=";")

    assert result == ","


def test_decimal_after_sample_InvalidInputError_when_dot_thousands_and_decimals():
    """
    Test that a number with '.' between thousands that cannot read with '.'
    as decimal mark ('1.705,11') and a number with decimals in a numeric
    column raise an InvalidInputError with the code 'data_unreadable'.
    """
    frame = pd.DataFrame({"y": [1.0, 2.75], "x": ["870", "1.705,11"]})

    err_msg = re.escape(
        "The decimal mark of the CSV file 'data.csv' cannot be told: it holds "
        "numbers written with ',' (such as '1.705,11') and with '.' (such as "
        "'2.75')."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        decimal_after_sample(frame, "data.csv", "data")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == DIALECT_HINT
