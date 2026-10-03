# Unit test run_server

import os
import sys
import anyio
import pytest
from mcp.server.mcpserver import MCPServer

from skforecast_ai.mcp import run_server
from skforecast_ai.mcp import server as server_module

if sys.version_info < (3, 11):
    from exceptiongroup import ExceptionGroup


def test_run_server_serves_stdio_from_the_output_dir(tmp_path, monkeypatch):
    """
    Test that `run_server` makes the output directory the working directory
    (so a library that writes next to it does not write into the project of
    the user) and serves over stdio.
    """
    monkeypatch.chdir(tmp_path)
    calls = []

    def fake_run(self, transport="stdio", **kwargs):
        calls.append((transport, os.getcwd(), self.name))

    monkeypatch.setattr(MCPServer, "run", fake_run)

    run_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    assert calls == [("stdio", str(tmp_path / "out"), "skforecast-ai")]


@pytest.mark.parametrize(
    "error",
    [
        BrokenPipeError(32, "Broken pipe"),
        ExceptionGroup("unhandled errors in a TaskGroup", [BrokenPipeError()]),
        ExceptionGroup(
            "outer",
            [anyio.ClosedResourceError(), ExceptionGroup("inner", [ConnectionResetError()])],
        ),
    ],
    ids=["broken pipe", "group", "nested group"],
)
def test_run_server_returns_when_the_client_disconnects(
    tmp_path, monkeypatch, capsys, error
):
    """
    Test that a server whose client closed its pipes while a call ran
    returns normally (the command exits with 0) and logs one line instead
    of a traceback, and that the log of the server is restored afterwards.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server_module, "_discard_stdout", lambda: None)

    def fake_run(self, transport="stdio", **kwargs):
        raise error

    monkeypatch.setattr(MCPServer, "run", fake_run)

    run_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 2
    assert lines[0].endswith(
        f"INFO skforecast_ai.mcp: skforecast-ai MCP server: reads CSV files in "
        f"{tmp_path}, writes files to {tmp_path / 'out'}."
    )
    assert lines[1].endswith(
        "INFO skforecast_ai.mcp: The client disconnected; the server stops."
    )
    assert server_module.logger.handlers == []
    assert server_module.logger.propagate is True


def test_run_server_other_errors_are_raised(tmp_path, monkeypatch):
    """
    Test that an error other than a disconnection, alone or in a group with
    one, is raised as it is.
    """
    monkeypatch.chdir(tmp_path)

    def fake_run(self, transport="stdio", **kwargs):
        raise ExceptionGroup("errors", [BrokenPipeError(), ValueError("bug")])

    monkeypatch.setattr(MCPServer, "run", fake_run)

    with pytest.raises(ExceptionGroup):
        run_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
