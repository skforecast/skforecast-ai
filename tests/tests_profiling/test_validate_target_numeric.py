# Unit test validate_target_numeric

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.exceptions import DataContentError, InvalidInputError
from skforecast_ai.profiling.data_profile import validate_target_numeric

_HINT = (
    "Leave the cells of missing values empty instead of marking them with "
    "text such as '-' or '?', and check that the target is the column of "
    "values to forecast."
)


@pytest.mark.parametrize(
    "values, shown",
    [
        (["1.5", "abc", "2.5", "-", "abc"], "['abc', '-']"),
        (["10,025.1", "-", "11,023.6"], "['10,025.1', '-', '11,023.6']"),
        (["12.5%", "?"], "['12.5%', '?']"),
        ([1.0, "abc", 3.0], "['abc']"),
        (["a", "b", "c", "d", "e", "f", "g"], "['a', 'b', 'c', 'd', 'e']"),
    ],
    ids=[
        "text",
        "thousands separator and text",
        "percent and text",
        "mixed with numbers",
        "at most 5 values quoted",
    ],
)
def test_validate_target_numeric_InvalidInputError_when_values_not_numbers(
    values, shown
):
    """
    Test that a target with text that is not a number raises, quoting the
    distinct values (at most 5), with the field 'target' and a hint. A column
    that also holds numbers written with a thousands separator or with '%'
    keeps this error when it holds another text.
    """
    data = pd.DataFrame({"y": values})

    err_msg = re.escape(
        f"Target column 'y' is not numeric: values such as {shown} are not "
        f"numbers."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_target_numeric(data, "y")

    assert type(exc_info.value) is InvalidInputError
    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "target"
    assert exc_info.value.hint == _HINT


_PLAIN = "a format that is not read. Write them as plain numbers"


@pytest.mark.parametrize(
    "values, message",
    [
        (
            ["10,025.1", "11,023.6", "9,999"],
            "Target column 'y' is not numeric: values such as ['10,025.1', "
            "'11,023.6', '9,999'] are numbers written with a thousands "
            f"separator, {_PLAIN}.",
        ),
        (
            ["1,234", 5.0, "2,500"],
            "Target column 'y' is not numeric: values such as ['1,234', "
            "'2,500'] are numbers written with a thousands separator, "
            f"{_PLAIN}.",
        ),
        (
            ["12.5%", "10%", "3.5%"],
            "Target column 'y' is not numeric: values such as ['12.5%', "
            f"'10%', '3.5%'] are numbers written with '%', {_PLAIN}.",
        ),
        (
            ["-3,5 %", None, "10 %"],
            "Target column 'y' is not numeric: values such as ['-3,5 %', "
            f"'10 %'] are numbers written with '%', {_PLAIN}.",
        ),
        (
            ["10,025.1", "12.5%"],
            "Target column 'y' is not numeric: values such as ['10,025.1', "
            "'12.5%'] are numbers written with a thousands separator or with "
            f"'%', {_PLAIN}.",
        ),
        (
            ["1.705,11", "870", "1.234.567"],
            "Target column 'y' is not numeric: values such as ['1.705,11', "
            "'1.234.567'] are numbers written with a thousands separator, "
            f"{_PLAIN}, or profile the file with `thousands` '.' when '.' "
            "separates its thousands and ',' is its decimal mark.",
        ),
        (
            ["1.705,11", "12.5%"],
            "Target column 'y' is not numeric: values such as ['1.705,11', "
            "'12.5%'] are numbers written with a thousands separator or with "
            f"'%', {_PLAIN}, or profile the file with `thousands` '.' when "
            "'.' separates its thousands and ',' is its decimal mark.",
        ),
    ],
    ids=[
        "comma thousands",
        "comma thousands and a number",
        "percent",
        "percent with spaces and a missing value",
        "thousands and percent",
        "point thousands",
        "point thousands and percent",
    ],
)
def test_validate_target_numeric_DataContentError_when_values_have_format_not_read(
    values, message
):
    """
    Test that a target whose values that are not numbers are all numbers
    written with a thousands separator ('10,025.1', '1.705,11') or with '%'
    raises a DataContentError for the field 'data' with no hint, a message
    that names the format and, when a thousands separator is '.', the option
    to profile the file with `thousands`.
    """
    data = pd.DataFrame({"y": values})

    err_msg = re.escape(message)
    with pytest.raises(DataContentError, match="^" + err_msg + "$") as exc_info:
        validate_target_numeric(data, "y")

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint is None
    assert isinstance(exc_info.value, InvalidInputError)


def test_validate_target_numeric_DataContentError_when_one_of_several_targets():
    """
    Test that every column of a list of targets is checked for numbers
    written in a format that is not read, and the column is named.
    """
    data = pd.DataFrame({"a": [1.0, 2.0], "b": ["12.5%", "10%"]})

    err_msg = re.escape(
        "Target column 'b' is not numeric: values such as ['12.5%', '10%'] are "
        f"numbers written with '%', {_PLAIN}."
    )
    with pytest.raises(DataContentError, match="^" + err_msg + "$") as exc_info:
        validate_target_numeric(data, ["a", "b"])

    assert exc_info.value.field == "data"


def test_validate_target_numeric_InvalidInputError_when_one_of_several_targets():
    """
    Test that every column of a list of targets is checked.
    """
    data = pd.DataFrame({"a": [1.0, 2.0], "b": ["1", "?"]})

    err_msg = re.escape(
        "Target column 'b' is not numeric: values such as ['?'] are not numbers."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_target_numeric(data, ["a", "b"])


@pytest.mark.parametrize(
    "values",
    [
        ["1.5", "2", "3e2", " 4 "],
        ["1.5", None, "2.5"],
        ["1.705", "870", "1.234"],
        [1.0, np.nan, 3.0],
        [1, 2, 3],
    ],
    ids=[
        "numeric strings",
        "numeric strings with a missing value",
        "strings with a point read as decimals",
        "float",
        "int",
    ],
)
def test_validate_target_numeric_output_when_values_are_numbers(values):
    """
    Test that numeric columns, and text that converts to numbers (as
    pandas.to_numeric reads it), are not rejected.
    """
    data = pd.DataFrame({"y": values})

    assert validate_target_numeric(data, "y") is None
