# Unit test create_server

import json
import os
import re
import tempfile
import pytest

from skforecast_ai import __version__
from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.mcp import create_server

from .fixtures_mcp import GOLDEN_SCHEMAS, call, run_session, tool_schemas


def test_create_server_tool_schemas_match_golden(tmp_path):
    """
    Test that the tools, their descriptions, annotations and input and output
    schemas are those of the golden file, so a change of the SDK of MCP or of
    pydantic that changes what agents see is noticed. Every input schema
    rejects unknown arguments. Regenerate the golden with
    `write_golden_schemas` of `fixtures_mcp` only after a deliberate change.
    """
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    schemas = tool_schemas(server)
    golden = json.loads(GOLDEN_SCHEMAS.read_text(encoding="utf-8"))

    assert [tool["name"] for tool in schemas] == [
        "profile",
        "plan",
        "refine_plan",
        "create_cv",
        "backtest",
        "compare",
        "forecast",
        "get_code",
        "get_failure",
        "list_objects",
        "describe_object",
    ]
    assert all(
        tool["input_schema"]["additionalProperties"] is False for tool in schemas
    )
    assert schemas == golden


def test_create_server_name_version_and_instructions(tmp_path):
    """
    Test that the server presents itself as skforecast-ai with the version
    of the package and instructions on the workflow.
    """
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    async def steps(client):
        return client.server_info, client.instructions

    info, instructions = run_session(server, steps)

    assert (info.name, info.version) == ("skforecast-ai", __version__)
    assert instructions.startswith(
        "Deterministic time series forecasting with skforecast."
    )


def test_create_server_output_dir_created_or_temporary(tmp_path, monkeypatch):
    """
    Test that the output directory is created when it does not exist, that
    without one the server writes to a new temporary directory, and that one
    that cannot be created raises `InvalidInputError`.
    """
    output_dir = tmp_path / "a" / "b"
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))
    (tmp_path / "file").write_text("")

    create_server(allow_dir=tmp_path, output_dir=output_dir)
    create_server(allow_dir=tmp_path)

    assert output_dir.is_dir()
    assert [name.startswith("skforecast-ai-mcp-") for name in os.listdir(temp_dir)] == [
        True
    ]
    err_msg = re.escape(
        f"The output directory {str(tmp_path / 'file' / 'out')!r} cannot be created"
    )
    with pytest.raises(InvalidInputError, match=err_msg) as excinfo:
        create_server(allow_dir=tmp_path, output_dir=tmp_path / "file" / "out")
    assert excinfo.value.field == "output_dir"


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"max_objects": 0}, "`max_objects` must be an integer of at least 1, got 0."),
        (
            {"max_memory_mb": True},
            "`max_memory_mb` must be an integer of at least 1, got True.",
        ),
        (
            {"max_objects": 2.5},
            "`max_objects` must be an integer of at least 1, got 2.5.",
        ),
        (
            {"max_file_mb": -1},
            "`max_file_mb` must be an integer of at least 0 (0 for no limit), "
            "got -1.",
        ),
    ],
    ids=lambda dt: f"{dt}",
)
def test_create_server_InvalidInputError_when_limits_invalid(
    tmp_path, arguments, message
):
    """
    Test that the limits of the store must be integers of at least 1, and
    the size of a file an integer of at least 0.
    """
    with pytest.raises(InvalidInputError, match=re.escape(message)):
        create_server(allow_dir=tmp_path, output_dir=tmp_path, **arguments)


def test_create_server_unknown_tool(tmp_path):
    """
    Test that calling a tool the server does not have is an error.
    """
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = call(server, "ask", {"question": "Why?"})

    assert result.is_error
    assert result.content[0].text == "Unknown tool: ask"
