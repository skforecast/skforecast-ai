---
name: open-pr
description: Prepare and open a skforecast-ai pull request against the current release branch, after running the tests and checks that CI does not run on release branches.
argument-hint: "[short PR title]"
---

# Open a pull request

Title hint from the user: $ARGUMENTS

## 1. Branches

- Release branch: read `__version__` in `skforecast_ai/__init__.py` and
  derive `X.Y.x` (`0.4.0` -> `0.4.x`). The PR base is that branch, never
  `main`.
- `git fetch origin` and compare against `origin/<release-branch>`: the
  local copy of the release branch may be stale. Below, `BASE` stands for
  `origin/<release-branch>`.
- If the current branch is `main` or the release branch, create
  `<type>/<slug>` first (type `feature`, `fix`, `docs` or `chore`, the
  names the cloud hook accepts). In a cloud session, keep the branch the
  session is working on.
- Review `git log --oneline BASE..HEAD`, `git diff BASE...HEAD --stat` and
  `git status`. Commit the uncommitted changes that belong to the PR
  without asking; leave the rest out (see the `dev/` files in step 2) and
  list them in the report.
- If the branch is behind `BASE`, say so; do not rebase or merge without
  asking.
- `gh pr view` tells whether the branch already has a PR. If it does,
  update that one (push, then `gh pr edit` if the body must change)
  instead of opening a second one.

## 2. Checks

CI runs lint and the unit tests only on pull requests to `main`. On a
release branch it only runs the AI context check, and only when
`skforecast_ai/skills/`, `skforecast_ai/resources/` or
`skforecast_ai/llm/prompts.py` change. The checks run here are the only
ones before merge.

1. Run `/verify` on the whole branch: its scope is
   `git diff --name-only BASE...HEAD` plus the working tree, not only the
   last commit. Stop on failures.
2. If the branch touches the paths of the AI context check, run what CI
   runs, with the Python command of `/verify` (the second one needs
   network access):
   ```bash
   python tools/ai/measure_skill_tokens.py --check
   python tools/ai/sync_skforecast_assets.py --check --branch auto
   ```
   Changes to `skforecast_ai/skills/` or
   `skforecast_ai/resources/llms-base.txt` must come from the sync script,
   never from a hand edit.
3. If the branch changes what the LLM receives (`llm/context.py`,
   `llm/prompts.py`, `skforecast_ai/skills/`,
   `recommendation/explanation.py`, `execution/backtesting_runner.py`,
   `execution/comparison.py`), the goldens must be regenerated on purpose
   (`/llm-context-change`). The real-model run of
   `tools/ai/check_ask_context.py` costs money, so the user launches it:
   ask whether it was run and whether its report is saved under
   `tools/ai/ask_context_reports/`; otherwise list it as pending in the PR
   body.
4. User-facing changes (API, CLI output, generated scripts, warnings) have
   an entry in `docs/releases/releases.md` under the version in
   development. If one is missing, write it with `/release-note` and show
   it to the user.
5. `dev/` holds working notes. `/handoff` writes `dev/<slug>.md`, and
   only some notes are versioned on purpose (`dev/mcp-preparation.md`).
   List the `dev/` files in the diff and ask whether each belongs to the
   PR.

## 3. Open the PR

- GitHub account: `git remote -v` shows which account pushes (an SSH host
  alias may point to a different key than `gh` uses), and
  `gh api user --jq .login` shows which account `gh` would open the PR
  with. If they are not the same person,
  stop and ask: the user can switch with `gh auth switch` (or log in the
  other account with `gh auth login`), or open the PR from the link
  printed by `git push`. Never switch accounts yourself.
- Push the branch with `git push -u origin <branch>` (a local session asks
  for confirmation; a cloud session's hook blocks pushes to `main` and
  `X.Y.x`).
- Write the body to a file in the scratchpad:
  - Maintainers (Javier Escobar Ortiz, Joaquin Amat Rodrigo, as in
    `pyproject.toml`; compare with `git config user.name`): a
    `## Description` of what changes and why (link the issue if any) and a
    `## How was this tested?` section listing each check run, with its
    command and result (number of tests passed), plus what was not run
    (for example the real-model `check_ask_context.py` run). Leave out the
    checklist of `.github/pull_request_template.md`: it is written for
    external contributors (the CLA does not apply to the copyright
    holders), and the results say more than ticked boxes.
  - Anyone else: fill `.github/pull_request_template.md` with the
    Description, how it was tested and the checklist, ticking only what
    was actually verified.
- Create it with
  `gh pr create --base <release-branch> --title "<title>" --body-file <file>`.
  The title follows the commit style of the repository
  (`fix(forecast): ...`, `docs(dev): ...`). In a cloud session, use the
  session's PR flow if `gh` is not authenticated.
- The title, body and commits carry only the author's identity: no AI
  co-author trailer, session link, "Generated with" line or mention of
  Claude (the Bash guard blocks them, also in a `--body-file`). No en
  dashes or em dashes.

## 4. Report

Give the PR URL, the checks run with their results, and anything left for
the reviewer (pending real-model run, `dev/` files left out, open
questions).
