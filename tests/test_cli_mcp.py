# Unit test cli mcp

import sys
from typer.testing import CliRunner

import skforecast_ai.mcp.server as server_module
from skforecast_ai.cli import app

runner = CliRunner()


def test_cli_mcp_runs_the_server_with_its_options(tmp_path, monkeypatch):
    """
    Test that `skforecast-ai mcp` runs the server with the allowed
    directory, the output directory, the limits and the allowed foundation
    models given.
    """
    calls = []
    monkeypatch.setattr(server_module, "run_server", lambda **kwargs: calls.append(kwargs))

    result = runner.invoke(app, [
        "mcp", "--allow-dir", str(tmp_path), "--output-dir", str(tmp_path / "out"),
        "--max-objects", "10", "--max-memory-mb", "64",
        "--allow-model", "google/timesfm-3.0", "--allow-model", "taharnbl/TS-ICL",
        "--max-file-mb", "0",
    ])

    assert result.exit_code == 0, result.output
    assert calls == [{
        "allow_dir": tmp_path, "output_dir": tmp_path / "out",
        "max_objects": 10, "max_memory_mb": 64, "max_file_mb": 0,
        "allow_models": ["google/timesfm-3.0", "taharnbl/TS-ICL"],
    }]


def test_cli_mcp_defaults(tmp_path, monkeypatch):
    """
    Test the defaults: no output directory (a temporary one), 256 objects,
    1024 MB, files of 256 MB and no restricted foundation model.
    """
    calls = []
    monkeypatch.setattr(server_module, "run_server", lambda **kwargs: calls.append(kwargs))

    result = runner.invoke(app, ["mcp", "--allow-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert calls == [{
        "allow_dir": tmp_path, "output_dir": None, "max_objects": 256,
        "max_memory_mb": 1024, "max_file_mb": 256, "allow_models": (),
    }]


def test_cli_mcp_exit_code_when_allow_dir_missing_or_invalid(tmp_path):
    """
    Test that `--allow-dir` is required, that a directory that does not
    exist exits with code 1 and its message, and that a limit below 1 (below
    0 for the file size) is rejected.
    """
    missing = runner.invoke(app, ["mcp"])
    invalid = runner.invoke(app, ["mcp", "--allow-dir", str(tmp_path / "nope")])
    limit = runner.invoke(app, ["mcp", "--allow-dir", str(tmp_path), "--max-objects", "0"])
    size = runner.invoke(app, ["mcp", "--allow-dir", str(tmp_path), "--max-file-mb", "-1"])

    assert missing.exit_code == 2
    assert "Missing option '--allow-dir'" in missing.output
    assert invalid.exit_code == 1
    assert "does not exist or is not a directory." in " ".join(invalid.output.split())
    assert limit.exit_code == 2
    assert size.exit_code == 2


def test_cli_mcp_exit_code_when_allow_model_is_not_a_model_prefix(tmp_path):
    """
    Test that an `--allow-model` prefix that does not start with the prefix
    of a foundation model of skforecast exits with code 1 and its message,
    before serving anything.
    """
    result = runner.invoke(
        app, ["mcp", "--allow-dir", str(tmp_path), "--allow-model", "google/"]
    )

    assert result.exit_code == 1
    assert "`--allow-model google/` does not start with the model ID prefix" in (
        " ".join(result.output.split())
    )


def test_cli_mcp_exit_code_when_mcp_extra_missing(tmp_path, monkeypatch):
    """
    Test that without the `mcp` package the command says which extra to
    install and exits with code 1.
    """
    for name in list(sys.modules):
        if name == "mcp" or name.startswith("mcp."):
            monkeypatch.setitem(sys.modules, name, None)
        if name.startswith("skforecast_ai.mcp"):
            monkeypatch.delitem(sys.modules, name)

    result = runner.invoke(app, ["mcp", "--allow-dir", str(tmp_path)])

    assert result.exit_code == 1
    output = " ".join(result.output.split())
    assert "the MCP server needs the `mcp` extra" in output
    assert 'pip install "skforecast-ai[mcp]"' in output


def test_cli_mcp_exit_code_when_output_dir_not_writable(tmp_path, monkeypatch):
    """
    Test that an output directory the server cannot write stops the command
    with code 1 and its message before serving.
    """
    def read_only(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(server_module.tempfile, "NamedTemporaryFile", read_only)
    served = []
    monkeypatch.setattr(
        server_module.MCPServer, "run", lambda *args, **kwargs: served.append(1)
    )

    result = runner.invoke(
        app,
        ["mcp", "--allow-dir", str(tmp_path), "--output-dir", str(tmp_path / "out")],
    )

    assert result.exit_code == 1
    assert "cannot be written: Permission denied." in " ".join(result.output.split())
    assert served == []
