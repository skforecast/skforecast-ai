"""
Stop hook: lint the Python files changed in the working tree before Claude
hands the turn back.

Only `ruff check` runs here; the test suite is too slow for every stop and
belongs to the `/verify` skill. `stop_hook_active` prevents a loop when
Claude cannot fix the report.
"""

import json
import os
import subprocess
import sys

from post_edit_check import ruff_command


def changed_python_files(cwd: str) -> list[str]:
    """Python files under `skforecast_ai/` or `tests/` changed since HEAD."""

    tracked = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
    ).stdout.split()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=cwd,
        capture_output=True,
        text=True,
    ).stdout.split()
    return sorted(
        f
        for f in set(tracked + untracked)
        if f.endswith(".py")
        and f.startswith(("skforecast_ai/", "tests/"))
        and not f.startswith("skforecast_ai/skills/")
        and os.path.isfile(os.path.join(cwd, f))
    )


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("stop_hook_active"):
        return 0

    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    files = changed_python_files(cwd)
    if not files:
        return 0

    cmd = ruff_command()
    if cmd is None:
        return 0

    result = subprocess.run(
        [*cmd, "check", "--quiet", "--output-format", "concise", *files],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            "ruff check fails on changed files; fix before finishing:\n"
            + (result.stdout.strip() or result.stderr.strip()),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
