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


def test_agent_instruction_files_are_identical():
    """
    Test that AGENTS.md and CLAUDE.md carry the same content. They are
    the same conventions published under the two names coding agents look
    for; keeping two copies in sync by hand is the price of not relying on
    symlinks, so this test makes a divergence fail loudly.
    """

    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    claude = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert agents == claude
