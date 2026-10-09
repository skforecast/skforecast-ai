"""
PostToolUse hook for Edit, Write and MultiEdit.

Checks the edited file right away so Claude fixes problems while the change
is still in context:

- Python files under `skforecast_ai/` or `tests/`: `ruff check`.
- Python and Markdown files: no en dash or em dash (same pattern as
  `tests/test_source_conventions.py`).

Exit code 2 sends the report on stderr back to Claude. Files synced from
skforecast are skipped because they follow upstream style.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DASH_PATTERN = re.compile("[\\u2013\\u2014]")

# Synced verbatim from skforecast; not ours to fix.
SKIPPED_PREFIXES = (
    "skforecast_ai/skills/",
    "skforecast_ai/resources/",
    ".github/copilot-instructions.md",
    ".github/instructions/",
)
RUFF_DIRS = ("skforecast_ai/", "tests/")


def ruff_command() -> list[str] | None:
    """
    Return the ruff command to use, or None when ruff is not available.
    `RUFF_BIN` (set in `.claude/settings.local.json`) wins, so a local
    session can point to the ruff of its conda environment.
    """

    if os.environ.get("RUFF_BIN") and os.path.isfile(os.environ["RUFF_BIN"]):
        return [os.environ["RUFF_BIN"]]
    if shutil.which("ruff"):
        return ["ruff"]
    try:
        subprocess.run(
            [sys.executable, "-m", "ruff", "--version"],
            capture_output=True,
            check=True,
        )
        return [sys.executable, "-m", "ruff"]
    except (subprocess.CalledProcessError, OSError):
        return None


def main() -> int:
    payload = json.load(sys.stdin)
    file_path = payload.get("tool_input", {}).get("file_path")
    if not file_path:
        return 0

    project_dir = Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    ).resolve()
    path = Path(file_path).resolve()
    try:
        rel = path.relative_to(project_dir).as_posix()
    except ValueError:
        return 0
    if rel.startswith(SKIPPED_PREFIXES) or not path.is_file():
        return 0

    problems = []

    if path.suffix in {".py", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if DASH_PATTERN.search(line):
                problems.append(
                    f"{rel}:{lineno}: en dash or em dash found; use commas, "
                    f"colons, semicolons or parentheses instead"
                )

    if path.suffix == ".py" and rel.startswith(RUFF_DIRS):
        cmd = ruff_command()
        if cmd is None:
            print(
                "post_edit_check: ruff not found, lint skipped "
                "(install it with `uv tool install ruff`)",
                file=sys.stderr,
            )
        else:
            result = subprocess.run(
                [*cmd, "check", "--quiet", "--output-format", "concise", rel],
                cwd=project_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                problems.append(result.stdout.strip() or result.stderr.strip())

    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
