# Unit test _leave_to_user

import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.mcp.server import _leave_to_user


def test_leave_to_user_adds_the_hint_of_the_field():
    """
    Test that an error of the library without a hint gets the hint the
    server gives for its field.
    """
    exc = InvalidInputError("The data has a problem.", field="data")

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
    exc = InvalidInputError("Something is wrong.", field=field, hint=hint)

    _leave_to_user(exc, {"data": "Ask the user."})

    assert exc.hint == hint
