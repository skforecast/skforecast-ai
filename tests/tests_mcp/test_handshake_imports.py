# Unit test imports of the MCP server before it answers its client

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "packages" / "skforecast-ai-mcp"


def test_handshake_does_not_load_pandas_scikit_learn_scipy_or_skforecast(
    tmp_path,
):
    """
    Test that what the server runs before it answers `initialize` and
    `tools/list` (the launcher of the plugin, the CLI, the server module, the
    server with its tools and the list of tools) imports neither pandas,
    NumPy, scipy, scikit-learn nor skforecast: Claude Code waits 30 seconds
    for both answers, and those imports take most of the first start. They
    are imported in the background once the client is connected, which this
    check does not do. The check runs in a fresh interpreter because the
    test process has already imported everything. `--allow-model` is left
    out: checking its prefixes imports skforecast before the answer.
    """
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(LAUNCHER)!r})\n"
        "import anyio\n"
        "import skforecast_ai_mcp\n"
        "from skforecast_ai.mcp.server import create_server\n"
        f"server = create_server(allow_dir={str(tmp_path)!r}, "
        f"output_dir={str(tmp_path / 'out')!r})\n"
        "tools = anyio.run(server.list_tools)\n"
        "heavy = {'pandas', 'numpy', 'scipy', 'sklearn', 'skforecast'}\n"
        "loaded = sorted({name.split('.')[0] for name in sys.modules} & heavy)\n"
        "print(len(tools), loaded)\n"
    )

    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )

    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip() == "11 []"
