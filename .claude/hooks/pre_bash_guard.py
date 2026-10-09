"""
PreToolUse hook for Bash: branch policy, attribution and paid calls.

- `tools/ai/check_ask_context.py` without `--dry-run` calls a real LLM and
  costs money; only the user launches it.
- Never push to `main` or a release branch (`X.Y.x`), in any environment,
  also through `HEAD`, `@` or `--all`.
- Never force push, in any form (`-f`, `--force`, `--force-with-lease`, a
  `+` refspec, `--mirror`); the deny rules in `settings.json` only catch the
  command prefixes they list.
- Commits and pull requests are authored by the user alone: no
  `Co-Authored-By` trailer naming Claude or Anthropic, no `Claude-Session`
  trailer and no "Generated with Claude Code" line, in the command text (`-m`, heredoc) or in a
  message file (`git commit -F`, `gh pr create --body-file`). The
  `attribution` setting in `settings.json` already turns them off; this
  catches messages written by hand.
- In Claude Code on the web (`CLAUDE_CODE_REMOTE=true`), commits and pushes
  only happen on a branch named `feature/...`, `fix/...`, `docs/...` or
  `chore/...`.
- Merging a pull request asks the user, also through `gh api` (the REST
  merge endpoint or the `mergePullRequest` GraphQL mutation), which the
  `Bash(gh pr merge *)` ask rule in `settings.json` does not match.

Exit code 2 blocks the command and sends the reason back to Claude; a
merge prints an `ask` decision instead. Confirming a local push is the
`ask` rule in `.claude/settings.local.json`, not here.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

PROTECTED_BRANCH = re.compile(r"^(main|master|\d+\.\d+\.x)$")
ALLOWED_BRANCH = re.compile(r"^(feature|fix|docs|chore)/[A-Za-z0-9._/-]+$")
SEGMENT_SEPARATOR = re.compile(r"\n|&&|\|\||;|\|")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# `<<EOF`, `<<-EOF`, `<<'EOF'` or `<<"EOF"`; the group is the delimiter.
HEREDOC_START = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
# git options that take a separate value before the subcommand.
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
FORCE_OPTIONS = ("--force", "--force-with-lease", "--force-if-includes")
# Push every local branch (or mirror the repository), protected ones included.
ALL_BRANCH_OPTIONS = {"--all", "--branches", "--mirror"}
AI_ATTRIBUTION = re.compile(
    r"co-authored-by:[^\n]*(claude|anthropic)|generated with \[?claude code"
    r"|^claude-session:",
    re.IGNORECASE | re.MULTILINE,
)
# A `git commit` at the start of a command, found on the raw text because
# `shlex` cannot parse a first line such as `git commit -m "$(cat <<'EOF'`.
COMMIT_COMMAND = re.compile(
    r"(?:^|[;&|(])\s*(?:[A-Za-z_]\w*=\S*\s+)*git(?:\s+-\S+(?:\s+[^-\s]\S*)?)*"
    r"\s+commit(?![\w-])",
    re.MULTILINE,
)
# Options that read a commit message or a PR body from a file.
MESSAGE_FILE_OPTIONS = ("-F", "--file", "--body-file")
# A pull request merge through `gh api`: REST endpoint or GraphQL mutation.
MERGE_API = re.compile(r"/pulls/\d+/merge\b|mergePullRequest")


def without_heredocs(command: str) -> str:
    """
    Remove the body of every heredoc from `command`: its lines are data
    (a commit message, a file written with `cat`), not commands, so a line
    that reads as one (`python tools/ai/check_ask_context.py` in a README)
    must not be checked as if it ran.
    """

    lines = command.split("\n")
    kept = []
    delimiter = None
    for line in lines:
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            continue
        kept.append(line)
        match = HEREDOC_START.search(line)
        if match:
            delimiter = match.group(1)
    return "\n".join(kept)


def segments(command: str) -> list[list[str]]:
    """
    Split `command` into simple commands and return the words of each, with
    leading env assignments removed. Heredoc bodies are left out, and a
    segment that is not valid shell is skipped.
    """

    result = []
    for segment in SEGMENT_SEPARATOR.split(without_heredocs(command)):
        try:
            words = shlex.split(segment.strip().lstrip("({ "))
        except ValueError:
            continue
        while words and ENV_ASSIGNMENT.match(words[0]):
            words.pop(0)
        if words:
            result.append(words)
    return result


def git_invocations(command: str) -> list[tuple[str, list[str]]]:
    """
    Return `(subcommand, args)` for every segment of `command` whose program
    is git. Only the first word of a segment counts, so `git push` quoted
    inside a heredoc or a grep pattern is ignored.
    """

    invocations = []
    for words in segments(command):
        if os.path.basename(words[0]) != "git":
            continue
        i = 1
        while i < len(words) and words[i].startswith("-"):
            i += 2 if words[i] in GIT_OPTIONS_WITH_VALUE else 1
        if i < len(words):
            invocations.append((words[i], words[i + 1:]))
    return invocations


def push_targets(args: list[str], branch: str) -> list[str]:
    """
    Branch names a `git push` may write to. Flags and the remote name are
    skipped; in `src:dst` the destination wins, and `HEAD` or `@` stand for
    the current branch. No refspec means the current branch.
    """

    positional = [a for a in args if not a.startswith("-")]
    refspecs = positional[1:]  # positional[0] is the remote
    if not refspecs:
        return [branch]
    targets = []
    for refspec in refspecs:
        target = refspec.split(":", 1)[-1].lstrip("+").removeprefix("refs/heads/")
        targets.append(branch if target in {"", "HEAD", "@"} else target)
    return targets


def forces(args: list[str]) -> bool:
    """
    Whether a `git push` rewrites remote history: a force option, `-f` in a
    cluster of short options (`-uf`), or a refspec starting with `+`.
    """

    for arg in args:
        if arg.startswith(FORCE_OPTIONS):
            return True
        if arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:]:
            return True
    positional = [a for a in args if not a.startswith("-")]
    return any(refspec.startswith("+") for refspec in positional[1:])


def message_files(args: list[str]) -> list[str]:
    """
    Paths given to `-F`, `--file` or `--body-file`, in the forms `-F path`,
    `-Fpath` and `--file=path`. `-` (stdin) is skipped.
    """

    paths = []
    for i, arg in enumerate(args):
        for option in MESSAGE_FILE_OPTIONS:
            if arg == option and i + 1 < len(args):
                paths.append(args[i + 1])
            elif arg.startswith(option + "="):
                paths.append(arg.split("=", 1)[1])
            elif option == "-F" and arg.startswith("-F") and len(arg) > 2:
                paths.append(arg[2:])
    return [p for p in paths if p != "-"]


def writes_message(words: list[str]) -> bool:
    """Whether a simple command writes a commit message or a PR body."""

    program = os.path.basename(words[0])
    if program == "gh":
        return words[1:2] == ["pr"] and words[2:3] in (["create"], ["edit"])
    return False


def merges_pr(words: list[str]) -> bool:
    """Whether a simple command merges a pull request."""

    if os.path.basename(words[0]) != "gh":
        return False
    if words[1:3] == ["pr", "merge"]:
        return True
    return words[1:2] == ["api"] and any(MERGE_API.search(w) for w in words[2:])


def ask_if_merging(command: str) -> int:
    """
    Print an `ask` decision when `command` merges a pull request, so the
    user confirms it in any permission mode, and return the exit code.
    """

    if any(merges_pr(words) for words in segments(command)):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": (
                    "Merging a pull request needs the user's confirmation."
                ),
            }
        }))
    return 0


def has_ai_attribution(command: str, cwd: str) -> bool:
    """
    Whether a command that writes a commit message or a PR body carries an
    AI attribution line, in its own text (which includes any heredoc) or in
    the message files it reads.
    """

    writers = [
        args for sub, args in git_invocations(command) if sub == "commit"
    ] + [words[3:] for words in segments(command) if writes_message(words)]
    if not writers and not COMMIT_COMMAND.search(command):
        return False
    if AI_ATTRIBUTION.search(command):
        return True
    for args in writers:
        for path in message_files(args):
            try:
                text = (Path(cwd) / path).read_text(errors="ignore")
            except OSError:
                continue
            if AI_ATTRIBUTION.search(text):
                return True
    return False


def current_branch(cwd: str) -> str:
    """Return the checked out branch, or an empty string when detached."""

    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    branch = result.stdout.strip()
    return "" if branch == "HEAD" else branch


def main() -> int:
    payload = json.load(sys.stdin)
    command = payload.get("tool_input", {}).get("command", "")

    for words in segments(command):
        runs_check = os.path.basename(words[0]).startswith("python") and any(
            w.endswith("check_ask_context.py") for w in words[1:2]
        )
        if runs_check and "--dry-run" not in words:
            print(
                "Blocked: check_ask_context.py without --dry-run calls a real "
                "LLM and costs money. Run it with --dry-run, or ask the user "
                "to launch the real run.",
                file=sys.stderr,
            )
            return 2

    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    if has_ai_attribution(command, cwd):
        print(
            "Blocked: commits and pull requests are authored by the user "
            "alone (AGENTS.md). Remove the Co-Authored-By trailer naming "
            "Claude or Anthropic, the Claude-Session trailer and any "
            "'Generated with Claude Code' line.",
            file=sys.stderr,
        )
        return 2

    invocations = [
        (sub, args)
        for sub, args in git_invocations(command)
        if sub in {"commit", "push"}
    ]
    if COMMIT_COMMAND.search(command) and not any(
        sub == "commit" for sub, _ in invocations
    ):
        invocations.append(("commit", []))
    if not invocations:
        return ask_if_merging(command)

    branch = current_branch(cwd)
    remote = os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true"

    for sub, args in invocations:
        if sub != "push":
            continue
        if forces(args):
            print(
                "Blocked: force pushes rewrite published history and are not "
                "allowed (AGENTS.md). Push new commits on top instead; merge "
                "the base branch rather than rebasing a pushed branch.",
                file=sys.stderr,
            )
            return 2
        if ALL_BRANCH_OPTIONS.intersection(args):
            print(
                "Blocked: --all, --branches and --mirror push every local "
                "branch, protected ones included. Push the current branch: "
                f"`git push -u origin {branch or '<branch>'}`.",
                file=sys.stderr,
            )
            return 2
        targets = push_targets(args, branch)
        blocked = [t for t in targets if PROTECTED_BRANCH.match(t)]
        if blocked:
            print(
                f"Blocked: pushing to {', '.join(blocked)} is not allowed. "
                f"Work on a feature/, fix/, docs/ or chore/ branch; the "
                f"author merges into protected branches.",
                file=sys.stderr,
            )
            return 2

    if remote and not ALLOWED_BRANCH.match(branch):
        print(
            f"Blocked: current branch '{branch}' does not follow the naming "
            f"convention. Before committing or pushing, create a branch named "
            f"<type>/<short-slug> with type feature, fix, docs or chore, for "
            f"example `git checkout -b fix/lag-validation`.",
            file=sys.stderr,
        )
        return 2

    return ask_if_merging(command)


if __name__ == "__main__":
    sys.exit(main())
