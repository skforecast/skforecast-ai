# Unit test _leave_to_user

import pytest

from skforecast_ai.exceptions import (
    DataContentError,
    InvalidInputError,
    SkforecastAIError,
)
from skforecast_ai.mcp.server import _leave_to_user


def test_leave_to_user_adds_the_hint_of_the_field():
    """
    Test that an error of the library about the content of the data,
    without a hint, gets the hint the server gives for its field.
    """
    exc = DataContentError("The data has a problem.", field="data")

    _leave_to_user(exc, {"data": "Ask the user.", "exog": "Ask for the file."})

    assert exc.hint == "Ask the user."
    assert str(exc) == "The data has a problem."


@pytest.mark.parametrize(
    "field, hint",
    [("data", "Replace them."), ("steps", None), (None, None)],
    ids=lambda dt: f"{dt!r}",
)
def test_leave_to_user_keeps_the_hint_of_the_library_and_other_fields(field, hint):
    """
    Test that the hint the library gives is kept, and that an error on
    another field, or on none, gets no hint.
    """
    exc = DataContentError("Something is wrong.", field=field, hint=hint)

    _leave_to_user(exc, {"data": "Ask the user."})

    assert exc.hint == hint


@pytest.mark.parametrize("field", ["data", "exog"], ids=lambda dt: f"{dt!r}")
def test_leave_to_user_gives_no_hint_to_an_error_of_an_argument(field):
    """
    Test that an error with the same field that is not about the content
    of the data (an argument that does not fit the plan, data without the
    columns of the profile) gets no hint: it is not the user's to solve.
    """
    exc = InvalidInputError(
        "`data` does not contain the column(s) ['x'] recorded in `profile`.",
        field=field,
    )

    _leave_to_user(exc, {"data": "Ask the user.", "exog": "Ask for the file."})

    assert exc.hint is None


def test_leave_to_user_adds_the_hint_to_the_kind_of_error_given():
    """
    Test that `kind` widens the errors that get the hint, for a tool whose
    errors on a field are all about the file of the user.
    """
    exc = InvalidInputError("The file has repeated dates.", field="data")

    _leave_to_user(exc, {"data": "Ask the user."}, kind=SkforecastAIError)

    assert exc.hint == "Ask the user."
