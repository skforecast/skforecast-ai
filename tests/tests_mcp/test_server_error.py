# Unit test ServerError

import re
import pytest

from skforecast_ai.mcp._errors import ServerError


def test_ServerError_attributes_correctly_stored():
    """
    Test that a `ServerError` keeps its message, code, field, hint and
    details, with a code of the server or of the core.
    """
    error = ServerError(
        "Gone.", code="unknown_id", field="plan_id", hint="List them.",
        details={"id": "x"},
    )
    core = ServerError("Bad.", code="invalid_argument")

    assert (str(error), error.code, error.field, error.hint, error.details) == (
        "Gone.", "unknown_id", "plan_id", "List them.", {"id": "x"}
    )
    assert (core.code, core.field, core.hint, core.details) == (
        "invalid_argument", None, None, None
    )


def test_ServerError_ValueError_when_code_unknown():
    """
    Test that a `ServerError` only takes the codes of the server and of the
    core.
    """
    with pytest.raises(ValueError, match=re.escape("Unknown error code 'bogus'.")):
        ServerError("x", code="bogus")
