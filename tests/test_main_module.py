# Unit test __main__ (python -m skforecast_ai and python -m skforecast_ai.cli)

import subprocess
import sys
import pytest

from skforecast_ai import __version__


@pytest.mark.parametrize("module", ["skforecast_ai", "skforecast_ai.cli"])
def test_main_module_runs_the_cli(module, tmp_path):
    """
    Test that `python -m skforecast_ai` and `python -m skforecast_ai.cli`
    run the CLI as the `skforecast-ai` command does (they exited with 0
    without doing anything), with its name in the help.
    """
    version = subprocess.run(
        [sys.executable, "-m", module, "--version"],
        capture_output=True, text=True, cwd=tmp_path, timeout=120,
    )
    help_text = subprocess.run(
        [sys.executable, "-m", module, "mcp", "--help"],
        capture_output=True, text=True, cwd=tmp_path, timeout=120,
    )
    missing = subprocess.run(
        [sys.executable, "-m", module, "mcp"],
        capture_output=True, text=True, cwd=tmp_path, timeout=120,
    )

    assert (version.returncode, version.stdout) == (0, f"skforecast-ai {__version__}\n")
    assert help_text.returncode == 0
    assert "Usage: skforecast-ai mcp" in help_text.stdout
    assert missing.returncode == 2
