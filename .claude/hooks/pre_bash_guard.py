"""
PreToolUse hook for Bash: branch policy and paid calls.

- `tools/ai/check_ask_context.py` without `--dry-run` calls a real LLM and
  costs money; only the user launches it.
- Never push to `main` or a release branch (`X.Y.x`), in any environment,
  also through `HEAD`, `@` or `--all`.
- Never force push, in any form (`-f`, `--force`, `--force-with-lease`, a
  `+` refspec, `--mirror`); the deny rules in `settings.json` only catch the
  command prefixes they list.
- In Claude Code on the web (`CLAUDE_CODE_REMOTE=true`), commits and pushes
  only happen on a branch named `feature/...`, `fix/...`, `docs/...` or
  `chore/...`.

Exit code 2 blocks the command and sends the reason back to Claude. Local
sessions without an explicit request to commit are handled by the `ask`
rules in `.claude/settings.local.json`, not here.
"""

import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED_BRANCH = re.compile(r"^(main|master|\d+\.\d+\.x)$")
ALLOWED_BRANCH = re.compile(r"^(feature|fix|docs|chore)/[A-Za-z0-9._/-]+$")
SEGMENT_SEPARATOR = re.compile(r"\n|&&|\|\||;|\|")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# git options that take a separate value before the subcommand.
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
FORCE_OPTIONS = ("--force", "--force-with-lease", "--force-if-includes")
# Push every local branch (or mirror the repository), protected ones included.
ALL_BRANCH_OPTIONS = {"--all", "--branches", "--mirror"}


def segments(command: str) -> list[list[str]]:
    """
    Split `command` into simple commands and return the words of each, with
    leading env assignments removed. A segment that is not valid shell
    (for example a line inside a heredoc) is skipped.
    """

    result = []
    for segment in SEGMENT_SEPARATOR.split(command):
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

    invocations = [
        (sub, args)
        for sub, args in git_invocations(command)
        if sub in {"commit", "push"}
    ]
    if not invocations:
        return 0

    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
