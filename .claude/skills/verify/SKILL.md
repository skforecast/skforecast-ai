---
name: verify
description: Definition of done for skforecast-ai. Lints, runs the tests affected by the current diff and then the full suite, and builds the docs or checks the LLM goldens when those areas changed. Use before reporting any code, test or docs change as finished.
---

# Verify the current change

Run every step, in order, and report each result. Stop at the first failure,
fix it, and start again from that step. Never report the task as done with a
failing step; if a failure is unrelated to the change, say so explicitly with
the output.

## 0. How to run Python

- Cloud session (`CLAUDE_CODE_REMOTE=true`): `python -m pytest`,
  `ruff`, `mkdocs` directly. The SessionStart hook installs the docs extra
  and exports `SKFORECAST_AI_DOCS_PRIVACY=false`, so `mkdocs build` skips
  the privacy plugin, whose downloads the network policy may block. If
  `mkdocs` is missing, install the extra first: `pip install -e ".[docs]"`.
- Local session: use the environment and the command prefix in
  `CLAUDE.local.md` (`PYTHONPATH=.` and the conda env binaries). If it does
  not exist, ask which conda environment to use.

Below, `PY` stands for that Python command.

## 1. Scope

```bash
git status --short
git diff --name-only HEAD
git ls-files --others --exclude-standard
```

Classify the changed files: package code (`skforecast_ai/`), tests, docs
(`docs/`, `mkdocs.yml`), LLM layer (`skforecast_ai/llm/`,
`recommendation/explanation.py`, `execution/backtesting_runner.py`,
`execution/comparison.py`), rendering (`skforecast_ai/rendering/`).

## 2. Lint

```bash
ruff check skforecast_ai tests
```

## 3. Affected tests first

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

It must end with no failures and no errors. Warnings are errors in this
project, so a new warning fails here too.

## 5. Conditional checks

- LLM layer changed: `PY -m pytest tests/tests_llm/test_golden_context.py -q`.
  If goldens differ on purpose, follow `/llm-context-change`.
- Docs changed: `PYTHONPATH=. mkdocs build -q -d <scratchpad>/site` (never
  into the repo). Report warnings about broken links or references.
- Harness changed (`.claude/hooks/`): `PY -m pytest .claude/hooks -q -p
  no:cacheprovider` (outside `testpaths`, so the full suite does not run it).
- User-visible change (API, CLI output, generated scripts, warnings) and no
  entry in `docs/releases/releases.md`: add one with `/release-note`.

## 6. Report

A short list: each step, the command, pass or fail, and the test count from
the full suite. Mention anything skipped and why.
