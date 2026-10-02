# Unit test source conventions shared by the whole package

import ast
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


# Built-in exceptions still raised on purpose: they signal a broken internal
# invariant or a missing resource of the package, not an invalid input, so
# `ErrorInfo` reports them as 'internal_error'. Any other raise must use the
# hierarchy of `skforecast_ai.exceptions`.
BUILTIN_RAISES_ALLOWED = {
    ("skforecast_ai/exceptions.py", "ValueError"): 1,
    ("skforecast_ai/llm/skills.py", "FileNotFoundError"): 3,
    ("skforecast_ai/mcp/_errors.py", "ValueError"): 1,
    ("skforecast_ai/recommendation/preprocessing.py", "ValueError"): 1,
}


def test_package_raises_errors_of_the_hierarchy():
    """
    Test that the package raises `ValueError`, `TypeError` and
    `FileNotFoundError` only through the hierarchy of
    `skforecast_ai.exceptions` (which derives from them), so every error a
    user can trigger carries a code and a field. The few built-in raises
    left are listed in `BUILTIN_RAISES_ALLOWED`.
    """

    builtins = {"ValueError", "TypeError", "FileNotFoundError"}
    found = {}
    for path in _python_files(REPO_ROOT / "skforecast_ai"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(exc, ast.Name) and exc.id in builtins:
                key = (path.relative_to(REPO_ROOT).as_posix(), exc.id)
                found[key] = found.get(key, 0) + 1

    assert found == BUILTIN_RAISES_ALLOWED

