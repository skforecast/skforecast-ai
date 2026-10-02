# Fixtures for the tests of the MCP server

import json
import re
from pathlib import Path

import anyio
import numpy as np
import pandas as pd
from mcp import Client

from ..fixtures_datasets import df_h2o

# h2o (monthly, 204 observations) with the dates in the column 'fecha'.
df_h2o_csv = df_h2o.reset_index()

# Daily series whose first column holds dates with two empty cells, so the
# column 'date' is used instead with a warning, and an exogenous variable.
_n_obs = 60
_dates = pd.date_range("2023-01-01", periods=_n_obs, freq="D")
_event = pd.Series(_dates.strftime("%Y-%m-%d"), dtype=object)
_event[[3, 10]] = None
df_data_warning = pd.DataFrame({
    "event": _event,
    "date": _dates.strftime("%Y-%m-%d"),
    "y": np.arange(_n_obs, dtype=float) % 7 + np.arange(_n_obs) * 0.1,
})

DATA_WARNING = (
    "The dates of column 'event' have 2 empty cell(s), at row position(s) 3, "
    "10 (counting from 0, header excluded). Column 'date' is used as the date "
    "column instead; pass `date_column` to choose another one."
)

ID_PATTERN = re.compile(r"(profile|plan|cv|backtest|comparison|forecast)-\d+-[0-9a-f]{6}")

# Python code that creates the file at {marker} when it runs, for the
# regressions of code injection: a payload that ran would leave the file.
MARKER_CODE = "__import__('pathlib').Path({marker!r}).touch()"


def h2o_server(directory: Path, **limits):
    """
    Write the h2o file into `directory` and return a server allowed to read
    it (writing to `directory / 'out'`) and the path of the file.
    """

    from skforecast_ai.mcp import create_server

    path = write_csv(directory, "h2o.csv", df_h2o_csv)
    server = create_server(allow_dir=directory, output_dir=Path(directory) / "out", **limits)

    return server, path


def profile_and_plan(server, path: str, target: str = "x", **plan_arguments):
    """
    Profile `path` and build a plan with `plan_arguments` (`steps` 12 unless
    given) in the server; return the ids of the profile and the plan.
    """

    plan_arguments.setdefault("steps", 12)

    async def steps(client):
        profile = content_of(
            await client.call_tool("profile", {"data_path": path, "target": target})
        )
        plan = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], **plan_arguments})
        )
        return profile["id"], plan["id"]

    return run_session(server, steps)


def write_csv(directory: Path, name: str, frame: pd.DataFrame) -> str:
    """
    Write a frame to a CSV file without its index and return the path.
    """

    path = Path(directory) / name
    frame.to_csv(path, index=False)

    return str(path)


def run_session(server, steps):
    """
    Open an in-memory client of `server`, await `steps(client)` and return
    its result.
    """

    async def main():
        async with Client(server) as client:
            return await steps(client)

    return anyio.run(main)


def call(server, name: str, arguments: dict):
    """
    Call one tool in a new session and return the `CallToolResult`.
    """

    async def steps(client):
        return await client.call_tool(name, arguments)

    return run_session(server, steps)


def error_of(result, tool: str) -> dict:
    """
    Return the JSON object of the error of a tool call.
    """

    assert result.is_error
    text = result.content[0].text
    prefix = f"Error executing tool {tool}: "
    assert text.startswith(prefix), text

    return json.loads(text[len(prefix):])


def content_of(result) -> dict:
    """
    Return the structured content of a successful tool call.
    """

    assert not result.is_error, result.content[0].text

    return result.structured_content


GOLDEN_SCHEMAS = Path(__file__).parent / "golden" / "tool_schemas.json"


def tool_schemas(server) -> list[dict]:
    """
    Return the name, description, annotations and input and output schemas
    of every tool of `server`, as an MCP client lists them.
    """

    async def steps(client):
        return (await client.list_tools()).tools

    return [
        {
            "name": tool.name,
            "description": tool.description,
            "annotations": tool.annotations.model_dump(mode="json", by_alias=True),
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
        }
        for tool in run_session(server, steps)
    ]


def write_golden_schemas(directory: str) -> None:
    """
    Write the golden file of the tool schemas. Run it after a deliberate
    change of the tools and review the diff:
    `python -c "from tests.tests_mcp.fixtures_mcp import write_golden_schemas;
    write_golden_schemas('/tmp')"`.
    """

    from skforecast_ai.mcp import create_server

    server = create_server(allow_dir=directory, output_dir=directory)
    GOLDEN_SCHEMAS.parent.mkdir(exist_ok=True)
    GOLDEN_SCHEMAS.write_text(
        json.dumps(tool_schemas(server), indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
