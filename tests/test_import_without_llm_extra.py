# Unit test package import without the LLM and MCP extras

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_importing_the_package_does_not_load_pydantic_ai_or_mcp():
    """
    Test that `import skforecast_ai` (and the CLI module) imports neither
    pydantic-ai nor the SDK of MCP. The deterministic core is documented to
    work with the base dependencies only, so every import of an optional
    extra must stay inside the functions that need it. The check runs in a
    fresh interpreter because the test process has already imported
    everything.
    """
    code = (
        "import sys\n"
        "import skforecast_ai\n"
        "import skforecast_ai.cli\n"
        "from skforecast_ai import ForecastingAssistant\n"
        "ForecastingAssistant()\n"
        "ForecastingAssistant(llm='openai:gpt-5.5', api_key='x').check_llm()\n"
        "loaded = [name for name in sys.modules if name.split('.')[0] in "
        "('pydantic_ai', 'mcp') or name.startswith('skforecast_ai.mcp')]\n"
        "print(loaded)\n"
    )

    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )

    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip() == "[]"
