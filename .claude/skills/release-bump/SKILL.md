---
name: release-bump
description: Bumps the skforecast-ai version in every place that carries it and prepares the release notes section for the new version.
disable-model-invocation: true
argument-hint: "<new version, e.g. 0.5.0>"
---

# Bump the version

New version: $ARGUMENTS (ask for it if empty). The current one is
`__version__` in `skforecast_ai/__init__.py`.

## 1. Branch

A new minor version starts a new release branch `X.Y.x` from the previous
one (ask before creating or pushing it). A patch version stays on its
release branch. The bump itself goes in a `chore/<slug>` branch, as any
other change.

## 2. Update every version reference

Replace the old version with the new one in:

- `pyproject.toml` (`version = ...`)
- `skforecast_ai/__init__.py` (`__version__`)
- `plugin/.claude-plugin/plugin.json` (`version`)
- `plugin/.mcp.json` (the `skforecast-ai[mcp]==X.Y.Z` pin)
- `.claude-plugin/marketplace.json` (`version`, twice)
- `packages/skforecast-ai-mcp/pyproject.toml` (`version` and the
  `skforecast-ai[mcp]==X.Y.Z` pin)
- `server.json` (`version`, twice)
- `tests/test_cli_config.py` (the version in the output)
- `docs/quick-start/how-to-install.md` (the example of a pinned install)

Then grep the old version across the repository (excluding
`docs/releases/`, `dev/`, `site/`, `build/`, `dist/` and the reports under
`tools/mcp/agent_reports/` and `tools/perf/results/`) and review each
remaining hit. Most are historical and must stay: "added in X.Y.Z" in
comments and docstrings, the run tables of `tools/mcp/README.md` and
`tools/ai/ask_context_reports/README.md`. Others (a test that mentions
the version, a TODO such as "review in X.Y.Z") need a decision. List them
for the user instead of changing them blindly.

`CITATION.cff` has no version on purpose.

## 3. Release notes

The section of the version being closed must not stay as `In development`:
check that it went through the consolidation pass of the `release-note`
skill (`/release-note consolidate`) and that its heading has the release
date (`<small>Oct 8, 2026</small>`). If not, tell the user before going on.

Then, in `docs/releases/releases.md`, add a section above the previous one
following the existing format:

```markdown
## X.Y.Z <small>In development</small> { id="X.Y.Z" }

The main changes in this release are:


**Added**


**Changed**


**Fixed**
```

## 4. Check

With the Python command of `/verify`:

```bash
python -m pytest tests/test_plugin_distribution.py tests/test_mcp_registry_distribution.py tests/test_cli_config.py -q -p no:cacheprovider
python tools/docs/check_release_notes.py
```

Remind the user that the release has two more steps after `skforecast-ai`
is on PyPI: publishing `skforecast-ai-mcp` and the entry of the MCP
registry, with the commands of `packages/README.md`.

Report the files changed and the remaining hits of the old version that
need a decision.
