"""
SessionStart hook.

In Claude Code on the web (`CLAUDE_CODE_REMOTE=true`) it installs the package
with the test, llm and docs extras plus ruff, so the session can run the same
checks as a local one (`/verify`). Locally it does nothing: the environment
comes from `CLAUDE.local.md` (conda).

It also runs after a compaction (matcher in `.claude/settings.json`), so the
environment and branch notes stay in context; the install is skipped when
every module is already there.

While skforecast-ai depends on a skforecast release that is not on PyPI yet
(development on a `X.Y.x` branch), the install from PyPI fails; the hook
then installs skforecast from the matching `X.Y.x` branch on GitHub, which
is what the local environment does too.

Whatever it prints on stdout is added to Claude's context. Environment
variables written to `CLAUDE_ENV_FILE` apply to every later Bash command.
"""

import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys

REQUIRED_MODULES = (
    "skforecast_ai", "pytest", "xdist", "pydantic_ai", "ruff", "mkdocs"
)
SKFORECAST_REPO = "https://github.com/skforecast/skforecast.git"
PROTECTED_BRANCH = re.compile(r"^(main|master|\d+\.\d+\.x)$")
ALLOWED_PREFIXES = ("feature/", "fix/", "docs/", "chore/")
# The privacy plugin of the docs downloads third-party assets (unpkg.com,
# GitHub avatars) that the network policy of a cloud environment may block;
# it only matters for the published site, so checks build without it.
DOCS_ENV = {"SKFORECAST_AI_DOCS_PRIVACY": "false"}


def git(*args: str, cwd: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    ).stdout.strip()


def install(cwd: str) -> str:
    """Install the package in editable mode; return a one line status."""

    missing = [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]
    if not missing:
        return "dependencies already installed"

    packages = ["-e", ".[test,llm,docs]", "ruff"]
    if shutil.which("uv"):
        base = ["uv", "pip", "install", "--python", sys.executable]
    else:
        base = [sys.executable, "-m", "pip", "install", "--quiet"]

    result = subprocess.run(
        [*base, *packages], cwd=cwd, capture_output=True, text=True
    )
    source = "PyPI"
    branch = skforecast_dev_branch(cwd)
    if result.returncode != 0 and branch:
        spec = f"skforecast @ git+{SKFORECAST_REPO}@{branch}"
        result = subprocess.run(
            [*base, spec, *packages], cwd=cwd, capture_output=True, text=True
        )
        source = f"skforecast from the {branch} branch"
    if result.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout).splitlines()[-15:])
        return f"dependency install FAILED ({' '.join(base)}):\n{tail}"
    return f"installed {', '.join(missing)} with {base[0]} ({source})"


def skforecast_dev_branch(cwd: str) -> str | None:
    """
    Development branch of the minimum skforecast version required in
    `pyproject.toml`, for example `0.26.x` for `skforecast>=0.26.0`.
    """

    text = open(os.path.join(cwd, "pyproject.toml"), encoding="utf-8").read()
    match = re.search(r'"skforecast>=(\d+)\.(\d+)', text)
    return f"{match.group(1)}.{match.group(2)}.x" if match else None


def export_env(values: dict[str, str]) -> None:
    """Persist environment variables for later Bash commands, if possible."""

    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        return
    try:
        with open(env_file, encoding="utf-8") as fh:
            present = set(fh.read().splitlines())
    except OSError:
        present = set()
    # The hook runs again on resume and after a compaction.
    lines = [f"export {name}={value}" for name, value in values.items()]
    with open(env_file, "a", encoding="utf-8") as fh:
        for line in lines:
            if line not in present:
                fh.write(line + "\n")


def main() -> int:
    if os.environ.get("CLAUDE_CODE_REMOTE", "").lower() != "true":
        return 0

    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    status = install(cwd)
    export_env(DOCS_ENV)
    branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)

    lines = [
        "Remote session (Claude Code on the web).",
        f"Python {platform.python_version()} at {sys.executable}; {status}.",
        "Run tests with `python -m pytest -n auto`; do not ask about conda.",
        f"Current branch: {branch}.",
    ]
    if PROTECTED_BRANCH.match(branch):
        lines.append(
            f"'{branch}' is protected: if the session instructions name it as "
            f"the branch to develop on or push to, use it only as the base. "
            f"Before the first commit run `git checkout -b <type>/<slug>` "
            f"(type: feature, fix, docs or chore) and push that branch; "
            f"commits here and pushes to '{branch}' are blocked by a hook."
        )
    elif not branch.startswith(ALLOWED_PREFIXES):
        lines.append(
            "Before the first commit, create a branch named <type>/<slug> "
            "(type: feature, fix, docs or chore). Commits and pushes on "
            "other branches are blocked by a hook."
        )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
