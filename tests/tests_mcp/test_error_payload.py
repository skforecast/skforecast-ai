# Unit test error_payload

import pytest
from pydantic import ValidationError

from skforecast_ai.exceptions import DataNotFoundError, InvalidInputError
from skforecast_ai.mcp._errors import ServerError, error_payload
from skforecast_ai.schemas import ForecastPlan


@pytest.mark.parametrize(
    "field, expected",
    [
        ("data", "data_path"),
        ("profile", "profile_id"),
        ("plan", "plan_id"),
        ("cv", "cv_id"),
        ("exog", "exog_path"),
        ("plan.steps", "plan_id.steps"),
        ("lags", "lags"),
        (None, None),
    ],
    ids=lambda dt: f"{dt}",
)
def test_error_payload_renames_the_fields_of_the_python_api(field, expected):
    """
    Test that the field of an error of the core is renamed to the argument
    of the tools that replaces it (ids and paths), and kept otherwise.
    """
    payload = error_payload(InvalidInputError("Bad value.", field=field))

    assert payload == {
        "code": "invalid_argument",
        "message": "Bad value.",
        "field": expected,
        "hint": None,
        "details": None,
    }


def test_error_payload_output_of_server_core_and_internal_errors():
    """
    Test the payload of a `ServerError` (with its details), of an error of
    the core with its own code, and of an exception that skforecast-ai did
    not raise (its type and first line, never a traceback).
    """
    server = ServerError(
        "Gone.",
        code="unknown_id",
        field="plan_id",
        hint="List them.",
        details={"id": "plan-1-abcdef"},
    )
    missing = DataNotFoundError("No file.", field="data")
    internal = RuntimeError("first line\nsecond line")

    assert error_payload(server) == {
        "code": "unknown_id",
        "message": "Gone.",
        "field": "plan_id",
        "hint": "List them.",
        "details": {"id": "plan-1-abcdef"},
    }
    assert error_payload(missing) == {
        "code": "data_not_found",
        "message": "No file.",
        "field": "data_path",
        "hint": None,
        "details": None,
    }
    assert error_payload(internal) == {
        "code": "internal_error",
        "message": "RuntimeError: first line",
        "field": None,
        "hint": None,
        "details": None,
    }


def test_error_payload_output_of_a_validation_error():
    """
    Test that a pydantic `ValidationError` is `invalid_argument` with the
    location of its first error as the field.
    """
    with pytest.raises(ValidationError) as excinfo:
        ForecastPlan.model_validate(
            {
                "task_type": "single_series",
                "forecaster": "ForecasterRecursive",
                "steps": "twelve",
                "explanation": "",
            }
        )

    payload = error_payload(excinfo.value)

    assert payload["code"] == "invalid_argument"
    assert payload["field"] == "steps"


def test_error_payload_cuts_long_messages_and_hints():
    """
    Test that the message is cut to 4,000 characters, the hint to 1,000 and
    the texts of the details to 500, saying how many characters were left
    out.
    """
    payload = error_payload(
        ServerError(
            "m" * 4_010,
            code="invalid_argument",
            hint="h" * 1_005,
            details={"id": "i" * 503, "removed": False},
        )
    )

    assert payload["message"] == "m" * 4_000 + " ... (10 more characters)"
    assert payload["hint"] == "h" * 1_000 + " ... (5 more characters)"
    assert payload["details"] == {
        "id": "i" * 500 + " ... (3 more characters)",
        "removed": False,
    }
