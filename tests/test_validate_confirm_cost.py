# Unit test validate_confirm_cost

import re

import numpy as np
import pytest

from skforecast_ai._validation import validate_confirm_cost
from skforecast_ai.exceptions import InvalidInputError, InvalidInputTypeError


@pytest.mark.parametrize(
    "confirm_cost",
    [True, False, 0, 60, np.int64(60)],
    ids=lambda value: f"{type(value).__name__}: {value}",
)
def test_validate_confirm_cost_no_error_when_bool_or_non_negative_integer(
    confirm_cost,
):
    """
    Test that a bool, an integer of 0 or more and a numpy integer are
    accepted, and that nothing is returned.
    """
    result = validate_confirm_cost(confirm_cost)

    assert result is None


@pytest.mark.parametrize(
    "confirm_cost, type_name",
    [("60", "str"), (60.0, "float"), (None, "NoneType")],
    ids=lambda value: f"{type(value).__name__}: {value}",
)
def test_validate_confirm_cost_InvalidInputTypeError_when_not_bool_or_integer(
    confirm_cost, type_name
):
    """
    Test that a string, a float (even with an integer value) and None raise
    InvalidInputTypeError, a TypeError, with the field `confirm_cost` and
    the type received.
    """
    err_msg = re.escape(
        "`confirm_cost` must be True, False or the integer figure of the "
        f"cost, got {type_name}."
    )
    with pytest.raises(InvalidInputTypeError, match=f"^{err_msg}$") as exc_info:
        validate_confirm_cost(confirm_cost)

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "confirm_cost"
    assert exc_info.value.code == "invalid_argument"


def test_validate_confirm_cost_InvalidInputError_when_integer_is_negative():
    """
    Test that a negative integer raises InvalidInputError, a ValueError and
    not a TypeError, with the field `confirm_cost` and the value received.
    """
    err_msg = re.escape(
        "`confirm_cost` must be True, False or the integer figure of the "
        "cost (0 or more), got -1."
    )
    with pytest.raises(InvalidInputError, match=f"^{err_msg}$") as exc_info:
        validate_confirm_cost(-1)

    assert isinstance(exc_info.value, ValueError)
    assert not isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "confirm_cost"
    assert exc_info.value.code == "invalid_argument"
