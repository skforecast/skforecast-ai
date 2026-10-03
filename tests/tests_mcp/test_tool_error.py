# Unit test tool_error

import json

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.mcp._errors import error_payload, tool_error


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
