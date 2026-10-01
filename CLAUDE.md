@AGENTS.md

# Claude Code specifics

`AGENTS.md` (imported above) holds the conventions shared with every coding
agent; edit it there, not here. This section covers only what depends on the
Claude Code harness in `.claude/`.

## Environment

- Local session: `CLAUDE.local.md` (not versioned) names the conda
  environment and how to run commands on this machine; use it instead of
  asking. Without it, follow "Python environment" in `AGENTS.md`.
- Cloud session (`CLAUDE_CODE_REMOTE=true`): the SessionStart hook has
  already installed the package with `[test,llm,docs]` and ruff, and exports
  `SKFORECAST_AI_DOCS_PRIVACY=false` so the docs build without the privacy
  plugin (its downloads are blocked by the default network policy). Use
  `python -m pytest` directly; there is no conda and nobody to ask.

## Git

- Local: no commits unless asked (`settings.local.json` makes
  `git commit` and `git push` ask for confirmation).
- Cloud: create `<type>/<slug>` (type `feature`, `fix`, `docs` or `chore`)
  before the first commit, then commit and push there. A PreToolUse hook
  blocks commits and pushes on other branches, pushes to `main` or `X.Y.x`
  everywhere (also through `HEAD`, `@`, `--all` or `--mirror`) and every
  form of force push.
- Cloud: when the session instructions name a protected branch (`main` or
  `X.Y.x`) as the branch to develop on or push to, take it as the base and
  branch off it; the SessionStart note says so too.
- Cloud: the environment's own Stop hook asks to commit and push whenever
  the tree has changes or unpushed commits, and the container can restart
  mid-task. When a turn ends while background work is still running, commit
  and push the finished part on the session branch, and complete it in a
  later commit; never rewrite pushed commits.

## Harness

- Hooks check every edit: `ruff check` on Python files and the no dash rule
  on Python and Markdown. Exit code 2 means fix it now.
- The hooks have their own tests, outside the package suite: run
  `python -m pytest .claude/hooks -q -p no:cacheprovider` after changing one.
- Path-scoped rules in `.claude/rules/` load when you touch tests, the LLM
  layer, rendering or execution.
- Definition of done: run `/verify` before reporting a task as finished.
- Skills: `/verify`, `/release-note`, `/llm-context-change`,
  `/sync-skforecast-assets` (user only), `/handoff` (user only).
- Subagents: `conventions-reviewer` (read-only review of the diff against
  the core principles) and `test-author` (writes tests under `tests/`).
- Files synced from skforecast are denied for Edit and Write in
  `.claude/settings.json`; change them only through the sync script.
