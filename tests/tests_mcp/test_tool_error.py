# Unit test tool_error

import json
import pytest

from skforecast_ai.exceptions import InvalidInputError, SkforecastAIError
from skforecast_ai.mcp._errors import ServerError, error_payload, tool_error


def test_tool_error_text_is_ascii_json():
    """
    Test that the text of the `ToolError` is the JSON of the payload, with
    every line break and non-ASCII character escaped.
    """
    exc = InvalidInputError("Column 'Año\u2028x' bad\nvalue.", field="target")

    text = str(tool_error(exc))

    assert text.isascii()
    assert "\n" not in text
    assert json.loads(text) == error_payload(exc)


def test_tool_error_unexpected_exception_sends_internal_error_payload():
    """
    Test that an exception neither the server nor skforecast-ai raised is
    sent with `internal_error_payload`: its type and an id, not its message.
    """
    payload = json.loads(str(tool_error(RuntimeError("value 'secret'"))))

    assert payload["code"] == "internal_error"
    assert payload["details"]["error_type"] == "RuntimeError"
    assert "secret" not in json.dumps(payload)


@pytest.mark.parametrize(
    "exc",
    [
        ServerError(
            "The call was cancelled. Nothing was registered.",
            code = "internal_error",
        ),
        SkforecastAIError("Raised by skforecast-ai itself."),
    ],
    ids=["server error", "error of the core"],
)
def test_tool_error_errors_with_internal_code_of_the_package_keep_their_message(exc):
    """
    Test that an error the server or skforecast-ai raised with the code
    `internal_error` (a cancelled call, a bare `SkforecastAIError`) keeps
    its own message: only exceptions of other libraries lose it.
    """
    assert json.loads(str(tool_error(exc))) == error_payload(exc)
