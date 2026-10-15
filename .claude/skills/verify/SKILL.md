---
name: verify
description: Definition of done for skforecast-ai. Lints, runs the tests affected by the current diff and then the full suite, and builds the docs or checks the LLM goldens when those areas changed. Use before reporting any code, test or docs change as finished.
---

# Verify the current change

Run every step, in order, and report each result. Stop at the first failure,
fix it, and start again from that step. Never report the task as done with a
failing step; if a failure is unrelated to the change, say so explicitly with
the output.

Reuse: when a run ends with every step green, note the commit it started
from and a fingerprint of the tree against it:

```bash
git rev-parse HEAD                                 # <verified-head>
git diff <verified-head> | shasum; git ls-files --others --exclude-standard
```

If a later `verify` in this session gets the same hash and the same
untracked files against that `<verified-head>`, report the previous result
again instead of rerunning it. Comparing against the noted commit, not
the current `HEAD`, keeps the result valid after committing exactly the
verified changes.

## 0. How to run Python

- Cloud session (`CLAUDE_CODE_REMOTE=true`): `python -m pytest`,
  `ruff`, `mkdocs` directly. The SessionStart hook installs the docs extra
  and exports `SKFORECAST_AI_DOCS_PRIVACY=false`, so `mkdocs build` skips
  the privacy plugin, whose downloads the network policy may block. If
  `mkdocs` is missing, install the extra first: `pip install -e ".[docs]"`.
- Local session: when `.claude/settings.local.json` sets
  `SKFORECAST_AI_PYTHON_ENV`, the SessionStart hook puts that environment on
  `PATH` and exports `PYTHONPATH=.`, so `python`, `ruff` and `mkdocs` run
  directly from the repository root. Otherwise use what `CLAUDE.local.md`
  says, and if it does not exist, ask which conda environment to use.

Below, `PY` stands for that Python command.

## 1. Scope

```bash
git status --short
git diff --name-only HEAD
git ls-files --others --exclude-standard
```

Also include the commits not yet in the remote release branch (`X.Y.x`,
from `__version__` in `skforecast_ai/__init__.py`), which the commands
above no longer show once the work is committed. The same command covers a
working branch and unpushed commits on the release branch itself:
`git diff --name-only origin/<release-branch>...HEAD`.

Classify the changed files: package code (`skforecast_ai/`), tests, docs
(`docs/`, `mkdocs.yml`, `tools/docs/`), LLM layer (`skforecast_ai/llm/`,
`recommendation/explanation.py`, `execution/backtesting_runner.py`,
`execution/comparison.py`), rendering (`skforecast_ai/rendering/`).

If no changed file is under one of these paths, nothing can break: report
"nothing to verify" with the list of files and stop here.

- `skforecast_ai/`, `tests/`, `pyproject.toml`
- `docs/`, `mkdocs.yml`, `tools/docs/`
- `README.md`, `AGENTS.md`, `CLAUDE.md`, `plugin/`, `.claude-plugin/`,
  `packages/`, `server.json` (tests read them)
- `.claude/hooks/`

The list names what can break rather than what cannot, so a new folder runs
the checks until it is judged safe. Notes and plans in `dev/`, the other
skills and rules in `.claude/`, and the scripts in `tools/ai/`, `tools/mcp/`
and `tools/perf/` are outside it: no test or build reads them.

When every changed file that counts falls in one of these groups, skip
steps 2 to 4 and run only its checks (files outside the list above do not
count):

- Docs only (`docs/`, `mkdocs.yml`, `tools/docs/`): the tests that read
  the docs, then the docs checks of step 5 (and the release notes check if
  `docs/releases/releases.md` changed).

  ```bash
  PY -m pytest tests/test_docs_cli_page.py tests/test_docs_skills_page.py tests/test_mcp_registry_distribution.py tests/tests_mcp/test_skill_md.py -q -p no:cacheprovider
  ```

- Hooks only (`.claude/hooks/`): the harness check of step 5.

Any other mix runs every step.

## 2. Lint

```bash
ruff check skforecast_ai tests
```

## 3. Affected tests first

Only for quick feedback before the full suite, which runs them again. Skip
this step when this session already ran the affected tests green and no
file changed since; running them while iterating is the usual case.

Map each changed module to its tests and run them with `-q`:

- `skforecast_ai/<sub>/<module>.py` -> `tests/tests_<sub>/`
  (for example `recommendation/` -> `tests/tests_recommendation/`).
- `skforecast_ai/assistant.py` -> `tests/test_assistant_<method>.py` for the
  methods touched.
- `skforecast_ai/cli.py` -> `tests/test_cli*.py`.
- `skforecast_ai/rendering/` -> `tests/tests_rendering/` and
  `tests/test_integration_standalone_script.py`.
- Changed test files -> those files.

```bash
PY -m pytest <paths> -q -p no:cacheprovider
```

## 4. Full suite

```bash
PY -m pytest -n auto -q -p no:cacheprovider
```

Use the worker count that `CLAUDE.local.md` names instead of `auto` when it
names one. When the docs build of step 5 is due, start it in the background
before this step so both run at once.

It must end with no failures and no errors. Warnings are errors in this
project, so a new warning fails here too.

## 5. Conditional checks

- LLM layer changed: `PY -m pytest tests/tests_llm/test_golden_context.py -q`.
  If goldens differ on purpose, follow `/llm-context-change`.
- Docs changed: `mkdocs build -q -d <scratchpad>/site` (never
  into the repo). Report warnings about broken links or references. Also run
  `PY tools/docs/hooks/page_meta.py`: a new or renamed page needs its search
  engine title and description in `tools/docs/hooks/page_meta.yml` (CI runs
  the same check on pull requests).
- Harness changed (`.claude/hooks/`): `PY -m pytest .claude/hooks -q -p
  no:cacheprovider` (outside `testpaths`, so the full suite does not run it).
- User-visible change (API, CLI output, generated scripts, warnings) and no
  entry in `docs/releases/releases.md`: add one with `/release-note`.
- Release notes changed: `PY tools/docs/check_release_notes.py` (undefined
  references, entries over the length ceiling or without a link).

## 6. Report

A short list: each step, the command, pass or fail, and the test count from
the full suite. Mention anything skipped and why.
