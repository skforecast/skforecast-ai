# Unit test validate_target_numeric

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
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
        ([1.0, "abc", 3.0], "['abc']"),
        (["a", "b", "c", "d", "e", "f", "g"], "['a', 'b', 'c', 'd', 'e']"),
    ],
    ids=["text", "mixed with numbers", "at most 5 values quoted"],
)
def test_validate_target_numeric_InvalidInputError_when_values_not_numbers(
    values, shown
):
    """
    Test that a target with text that is not a number raises, quoting the
    distinct values (at most 5), with the field 'target' and a hint.
    """
    data = pd.DataFrame({"y": values})

    err_msg = re.escape(
        f"Target column 'y' is not numeric: values such as {shown} are not "
        f"numbers."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_target_numeric(data, "y")

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "target"
    assert exc_info.value.hint == _HINT


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
        [1.0, np.nan, 3.0],
        [1, 2, 3],
    ],
    ids=["numeric strings", "numeric strings with a missing value", "float", "int"],
)
def test_validate_target_numeric_output_when_values_are_numbers(values):
    """
    Test that numeric columns, and text that converts to numbers (as
    pandas.to_numeric reads it), are not rejected.
    """
    data = pd.DataFrame({"y": values})

    assert validate_target_numeric(data, "y") is None
