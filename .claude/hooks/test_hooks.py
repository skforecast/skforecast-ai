"""
Tests of the Claude Code hooks in this directory.

They are not part of the package suite (`testpaths = ["tests"]`); run them
after changing a hook with `python -m pytest .claude/hooks -q -p no:cacheprovider`.
Every test works on a throwaway git repository under `tmp_path`.
"""

import importlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
HOOK_ENV_VARS = ("CLAUDE_CODE_REMOTE", "CLAUDE_PROJECT_DIR", "CLAUDE_ENV_FILE")


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=hook@test", "-c", "user.name=hook", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def make_repo(path: Path, branch: str) -> Path:
    """A git repository on `branch` with one commit and no remote."""

    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "checkout", "-q", "-b", branch)
    git(path, "commit", "-q", "--allow-empty", "-m", "init")
    return path


def run_hook(
    name: str, payload: dict, repo: Path, remote: bool
) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in HOOK_ENV_VARS}
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    if remote:
        env["CLAUDE_CODE_REMOTE"] = "true"
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )


HEREDOC_COMMIT = (
    "git commit -m \"$(cat <<'EOF'\nfix: x\n\n{trailer}\nEOF\n)\""
)
CLAUDE_TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


@pytest.mark.parametrize(
    "branch, command, remote, expected",
    [
        ("0.4.x", "git push origin HEAD", False, 2),
        ("0.4.x", "git push origin @", False, 2),
        ("0.4.x", "git push", False, 2),
        ("main", "git push -u origin main", False, 2),
        ("feature/x", "git push origin HEAD:0.4.x", False, 2),
        ("feature/x", "git push origin :0.4.x", False, 2),
        ("feature/x", "git push --force origin feature/x", False, 2),
        ("feature/x", "git push origin feature/x --force", False, 2),
        ("feature/x", "git push -uf origin feature/x", False, 2),
        ("feature/x", "git push --force-with-lease origin feature/x", False, 2),
        ("feature/x", "git push --force-with-lease=feature/x origin feature/x", False, 2),
        ("feature/x", "git push origin +feature/x", False, 2),
        ("feature/x", "git push --all origin", False, 2),
        ("feature/x", "git push --mirror origin", False, 2),
        ("feature/x", "git push -u origin feature/x", True, 0),
        ("feature/x", "cd repo && git push -u origin HEAD", True, 0),
        ("feature/x", "git push --follow-tags origin feature/x", False, 0),
        ("feature/x", "grep -n 'git push --force' notes.txt", False, 0),
        ("0.4.x", "git commit -m 'x'", True, 2),
        ("claude/some-session", "git commit -m 'x'", True, 2),
        ("0.4.x", "git commit -m 'x'", False, 0),
        ("0.4.x", HEREDOC_COMMIT.format(trailer="Body."), True, 2),
        ("feature/x", HEREDOC_COMMIT.format(trailer="Body."), True, 0),
        ("feature/x", HEREDOC_COMMIT.format(trailer=CLAUDE_TRAILER), True, 2),
        ("feature/x", HEREDOC_COMMIT.format(trailer=CLAUDE_TRAILER), False, 2),
        ("feature/x", f"git commit -m 'x' -m '{CLAUDE_TRAILER}'", False, 2),
        ("feature/x", "git commit -m 'x' -m 'Co-authored-by: Ana <a@b.c>'", False, 0),
        ("feature/x", HEREDOC_COMMIT.format(trailer="Claude-Session: https://x"), False, 2),
        ("feature/x", "gh pr create --body 'Generated with [Claude Code](u)'", False, 2),
        ("feature/x", "gh pr create --title t --body 'Adds x.'", False, 0),
        ("feature/x", f"grep -rn '{CLAUDE_TRAILER}' .", False, 0),
        ("0.4.x", f"git commit-tree t -m \"$(grep -v '{CLAUDE_TRAILER}' m)\"", True, 0),
        ("feature/x", "python tools/ai/check_ask_context.py", False, 2),
        ("feature/x", "python tools/ai/check_ask_context.py --dry-run", False, 0),
        (
            "feature/x",
            "cat > notes.md <<'EOF'\npython tools/ai/check_ask_context.py --dataset h2o\nEOF",
            False, 0,
        ),
        (
            "feature/x",
            "cat > notes.md <<'EOF'\ntext\nEOF\npython tools/ai/check_ask_context.py",
            False, 2,
        ),
    ],
)
def test_pre_bash_guard_exit_code(tmp_path, branch, command, remote, expected):
    """
    Test that the Bash guard blocks pushes to protected branches (also through
    HEAD, @ and --all), every form of force push, commits outside the naming
    convention in the cloud (also with a heredoc message), AI attribution in
    commit messages and PR bodies, and the paid context check, and lets the
    rest run.
    """

    repo = make_repo(tmp_path / "repo", branch)
    result = run_hook(
        "pre_bash_guard.py", {"tool_input": {"command": command}}, repo, remote
    )

    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize(
    "command",
    ["git commit -F msg.txt", "git commit --file=msg.txt", "gh pr create --body-file msg.txt"],
)
def test_pre_bash_guard_blocks_attribution_in_message_file(tmp_path, command):
    """
    Test that the Bash guard reads the message file of `git commit -F` and
    `gh pr create --body-file` and blocks an AI attribution line in it.
    """

    repo = make_repo(tmp_path / "repo", "feature/x")
    (repo / "msg.txt").write_text(f"fix: x\n\n{CLAUDE_TRAILER}\n")
    result = run_hook(
        "pre_bash_guard.py", {"tool_input": {"command": command}}, repo, False
    )

    assert result.returncode == 2
    assert "authored by the user alone" in result.stderr


@pytest.fixture
def session_start(monkeypatch):
    """The session_start module with the dependency install stubbed out."""

    monkeypatch.syspath_prepend(str(HOOKS_DIR))
    module = importlib.import_module("session_start")
    monkeypatch.setattr(module, "install", lambda cwd: "dependencies stubbed")
    for name in HOOK_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return module


@pytest.mark.parametrize(
    "branch, expected",
    [
        ("0.4.x", "'0.4.x' is protected"),
        ("claude/some-session", "Before the first commit, create a branch"),
        ("feature/x", None),
    ],
)
def test_session_start_branch_note(
    session_start, monkeypatch, capsys, tmp_path, branch, expected
):
    """
    Test that the SessionStart hook explains what to do on a protected branch
    or on a branch outside the naming convention, and exports the docs
    environment variable for later commands once, however often it runs.
    """

    repo = make_repo(tmp_path / "repo", branch)
    env_file = tmp_path / "env.sh"
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))

    assert session_start.main() == 0
    out = capsys.readouterr().out
    # A second run (resume or compaction) must not repeat the export.
    assert session_start.main() == 0

    assert f"Current branch: {branch}." in out
    if expected is None:
        assert "Before the first commit" not in out
    else:
        assert expected in out
    assert env_file.read_text() == "export SKFORECAST_AI_DOCS_PRIVACY=false\n"


def test_session_start_silent_in_local_session(session_start, monkeypatch, capsys):
    """Test that the SessionStart hook prints nothing outside the cloud."""

    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

    assert session_start.main() == 0
    assert capsys.readouterr().out == ""
