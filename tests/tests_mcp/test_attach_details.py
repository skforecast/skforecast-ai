# Unit test attach_details

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.mcp._errors import add_details, attach_details, error_payload


def test_attach_details_reaches_the_payload_of_the_error():
    """
    Test that details attached to an error of the core are sent in the
    `details` of its payload.
    """
    exc = InvalidInputError("Bad.", field="data")
    attach_details(exc, {"failure_id": "failure-3-abcdef"})

    assert error_payload(exc)["details"] == {"failure_id": "failure-3-abcdef"}


def test_add_details_keeps_the_details_already_attached():
    """
    Test that `add_details` adds to the details an error already carries
    (the id of its failure) instead of replacing them, and works on an
    error without details.
    """
    exc = InvalidInputError("Bad.", field="data")
    attach_details(exc, {"failure_id": "failure-3-abcdef"})
    add_details(exc, {"notices": [{"source": "plan"}]})
    bare = InvalidInputError("Bad.")
    add_details(bare, {"notices": []})

    assert error_payload(exc)["details"] == {
        "failure_id": "failure-3-abcdef",
        "notices": [{"source": "plan"}],
    }
    assert error_payload(bare)["details"] == {"notices": []}
