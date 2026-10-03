# Unit test internal_error_payload

import json
import logging
import re

from skforecast_ai.mcp._errors import internal_error_payload


def test_internal_error_payload_sends_type_and_id_and_logs_the_rest(caplog):
    """
    Test that an exception neither the server nor skforecast-ai raised
    reaches the agent with its type and an id only, never its message (which
    can quote a value of the data), and that its message and traceback go to
    the log of the server under that id.
    """
    try:
        float("secret-value")
    except ValueError as exc:
        error = exc

    with caplog.at_level(logging.ERROR, logger="skforecast_ai.mcp"):
        payload = internal_error_payload(error)

    error_id = payload["details"]["error_id"]
    assert re.fullmatch(r"error-[0-9a-f]{12}", error_id)
    assert payload == {
        "code": "internal_error",
        "message": (
            f"Unexpected ValueError. Its message and traceback are in the log "
            f"of the server (stderr) under the id {error_id}."
        ),
        "field": None,
        "hint": (
            "Report it to the user with the id; do not retry with the same "
            "inputs."
        ),
        "details": {"error_id": error_id, "error_type": "ValueError"},
    }
    assert "secret-value" not in json.dumps(payload)
    (record,) = caplog.records
    assert record.getMessage() == (
        f"internal_error {error_id}: ValueError: could not convert string to "
        f"float: 'secret-value'"
    )
    assert record.exc_info[1] is error
