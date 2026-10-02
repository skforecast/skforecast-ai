# Unit test attach_details

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.mcp._errors import attach_details, error_payload


def test_attach_details_reaches_the_payload_of_the_error():
    """
    Test that details attached to an error of the core are sent in the
    `details` of its payload.
    """
    exc = InvalidInputError("Bad.", field="data")
    attach_details(exc, {"failure_id": "failure-3-abcdef"})

    assert error_payload(exc)["details"] == {"failure_id": "failure-3-abcdef"}
