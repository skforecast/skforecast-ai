# Unit test source conventions shared by the whole package

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# `skills/` is synced verbatim from skforecast and follows its own style.
EXCLUDED_PARTS = {"skills", "__pycache__"}

# En dash and em dash. Both are banned by AGENTS.md in code, docstrings,
# comments, and user-facing messages; plain ASCII punctuation is used instead.
DASH_PATTERN = re.compile("[\\u2013\\u2014]")


def _python_files(directory: Path) -> list[Path]:
    """
    Collect the Python files under `directory`, skipping excluded parts.

    Parameters
    ----------
    directory : Path
        Root directory to walk.

    Returns
    -------
    files : list of Path
        Sorted Python files found under `directory`.
    """

    return sorted(
        path
        for path in directory.rglob("*.py")
        if not EXCLUDED_PARTS.intersection(path.relative_to(directory).parts)
    )


@pytest.mark.parametrize(
    "directory",
    ["skforecast_ai", "tests"],
    ids=lambda dt: f"directory: {dt}"
)
def test_source_files_contain_no_en_or_em_dashes(directory):
    """
    Test that no Python file in the package or the test suite contains an
    en dash or an em dash. The rule lives in AGENTS.md; the test keeps it
    from regressing through generated code comments, error messages, or
    docstrings, which are all visible to users.
    """

    files = _python_files(REPO_ROOT / directory)
    assert files, f"no Python files collected under {directory}"

    offenders = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if DASH_PATTERN.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")

    assert offenders == []


def test_claude_instructions_import_agents_instructions():
    """
    Test that CLAUDE.md starts by importing AGENTS.md, so the conventions
    shared by every coding agent live in a single file and Claude Code
    loads them without a second copy that could drift. CLAUDE.md only adds
    what is specific to the Claude Code harness.
    """

    claude = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert claude.splitlines()[0] == "@AGENTS.md"
    assert (REPO_ROOT / "AGENTS.md").is_file()
