# Unit test run_server

import os
from mcp.server.mcpserver import MCPServer

from skforecast_ai.mcp import run_server


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
