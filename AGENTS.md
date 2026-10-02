# skforecast-ai: conventions for coding agents

`skforecast-ai` wraps the `skforecast` engine in a deterministic forecasting
assistant (`ForecastingAssistant`) with an optional LLM layer that explains
decisions but never makes them. PyPI name `skforecast-ai`, import name
`skforecast_ai`. This file is the entry point for any coding agent; the
detailed docstring and testing rules live in `.github/instructions/` and are
shared with the `skforecast` repository.

## Core principles

1. Deterministic first, LLM second. Every forecasting decision (forecaster,
   estimator, lags, metric, cross-validation) comes from rule-based code in
   `recommendation/` and is reproducible without an LLM. The LLM explains,
   refines lags and window features on request, and translates a
   natural-language scenario into `TimeSeriesFold` parameters; its output is
   always validated by a Pydantic model before it touches execution.
2. The code you see is the code that ran. `forecast()` and `backtest()`
   execute the same script that `forecast_code()` and `backtest_code()`
   return (minus the CSV loading preamble). Rendering lives in `rendering/`,
   execution in `execution/`; never let them drift apart.
3. No silent automation. When something cannot be validated, warn or raise.
   Degrade to a deterministic result only when that result is valid on its
   own (`refine_plan()`, `create_cv()`); `ask()` raises `LLMCallError`
   because it has no answer without the LLM.
4. Privacy by default. Datasets never reach the LLM: profiles hold summary
   statistics only. Results ship the values they own (predictions, metrics)
   and `ask()` warns about it with `DataSentToLLMWarning` when
   `send_data_to_llm=False`.
5. Everything crossing a module boundary is a Pydantic model (`schemas/`),
   and every result is a `DisplayMixin` (renders itself) and an
   `ExplainableResult` (describes itself to the LLM).

## Layout

```
skforecast_ai/
  assistant.py        ForecastingAssistant: public facade, orchestration only
  _utils.py           input resolution and validation helpers
  _display.py         rich rendering shared by every result
  schemas/            Pydantic models: profiles, plans, results, typed overrides
  profiling/          deterministic data inspection (DataProfile)
  recommendation/     rule engine: forecaster, estimator, lags, metric, CV
  rendering/          script generation from a plan (one module per family)
  execution/          runs rendered scripts; comparison helpers
  llm/                pydantic-ai agents, prompts, context, skills, runtime
  mcp/                MCP server (`skforecast-ai mcp`): tools over the assistant;
                      mcp/skills/ is its SKILL.md for agents, written here
  skills/, resources/ synced from skforecast (do not edit by hand)
  cli.py              Typer CLI mirroring the Python API
tests/                mirrors the package: tests_<subpackage>/, fixtures_*.py
tools/                maintenance scripts (see tools/README.md): ai/ for the
                      skforecast assets and the LLM context checks,
                      docs/ for the documentation build
```

## Python environment

Interactive local session: before running any Python command (tests,
scripts, notebooks, `pip install`) for the first time in a session, run
`conda env list` and ask which environment to use. Do not assume the active
environment. Once the user confirms an environment, reuse it for the rest of
the session.

Non-interactive or cloud session (nobody to ask, no conda): install with
`pip install -e ".[test,llm]" ruff` and run the commands below as they are.
No API key or network is needed for the test suite; LLM calls are mocked.

## Commands

```bash
pytest -n auto                                   # full suite
pytest tests/test_assistant_ask.py -q            # one file
ruff check skforecast_ai tests                   # lint (must be clean; CI runs it)
python tools/ai/update_golden_contexts.py        # regenerate LLM context goldens
python tools/ai/check_ask_context.py --dry-run   # ask() contexts, no LLM call
PYTHONPATH=. mkdocs build -q -d /tmp/site        # docs build check
```

## Code style

- PEP 8, max line length 88, enforced by ruff (`E`, `F`). Double quotes.
- Type hints on every public function and method; `X | None`, `list[...]`.
- Relative imports inside the package.
- Aligned keyword arguments in long calls, as in skforecast
  (`profile = self.profile(\n    data   = data,\n    target = target,\n)`).
- NumPy-style docstrings on every public class, method and function. Follow
  `.github/instructions/docstrings.instructions.md`: single backticks,
  readable type names (`pandas DataFrame`), `name : type, default value`.
- No en dashes or em dashes anywhere: code, comments, docstrings, string
  literals, error messages, tests or documentation. Use commas, colons,
  semicolons or parentheses. `tests/test_source_conventions.py` enforces it.
- Comments explain why, not what. No emojis in source or messages.
- pydantic-ai is the only LLM abstraction; never import a provider SDK.
- Importing `skforecast_ai` must work without the `[llm]` extra: keep
  pydantic-ai imports inside functions.

## Testing

Follow `.github/instructions/testing.instructions.md`. In short:

- One test file per public function or method, header `# Unit test <name>`.
- Fixtures are module-level variables in `fixtures_<module>.py`.
- Every test has a docstring saying what it verifies; names follow
  `test_<method>_<scenario>` / `test_<method>_<ErrorType>_when_<condition>`.
- Hardcoded expected values; `pd.testing` and `np.testing` for comparisons;
  errors and warnings with `re.escape()` plus `pytest.raises(match=...)`.
- LLM calls are mocked (`patch_agent` in `tests/fixtures_assistant.py`).
  Never call a real provider from tests.
- Generated scripts are compared byte for byte in `tests/tests_rendering/`
  and executed as real files in `tests/test_integration_standalone_script.py`.
  LLM contexts have goldens in `tests/tests_llm/golden/`; regenerate them
  only when the change is intentional and review the diff.
- A new `ExplainableResult` needs a builder in `tests/fixtures_llm.py`; the
  contract test discovers subclasses and fails otherwise.
- Warnings are errors (`filterwarnings = error` in `pyproject.toml`). A test
  that expects a warning wraps the call in `pytest.warns`; a third-party
  warning that cannot be fixed here gets a targeted `ignore` entry in
  `pyproject.toml` with its reason. Never add a blanket ignore.
- `tests/test_import_without_llm_extra.py` guards that importing the package
  does not load pydantic-ai, and `tests/test_integration_determinism.py`
  guards that the same input yields the same profile, plan, script and
  predictions.

## Working with the user

- In a local session, commit finished work without asking, on a working
  branch (`feature/`, `fix/`, `docs/` or `chore/`), never directly on
  `main` or `X.Y.x`. Ask before pushing; once a push is approved, opening
  the pull request needs no further confirmation. Never merge a pull
  request without the author's confirmation.
- An autonomous remote session commits and pushes to its own branch, named
  `feature/<slug>`, `fix/<slug>`, `docs/<slug>` or `chore/<slug>`. Never push
  to `main` or a release branch (`X.Y.x`), never force push, and do not open
  a pull request unless asked.
- Commits and pull requests carry only the author's identity: no
  `Co-Authored-By` trailer for an AI agent, no session link trailer and no
  "Generated with" line.
  The author identity comes from git config or `GIT_AUTHOR_*` and
  `GIT_COMMITTER_*`; do not override it.
- Any user-visible change (API, CLI output, generated scripts, warnings)
  gets an entry in `docs/releases/releases.md` under the unreleased version.
- A change to `llm/context.py`, `llm/prompts.py` or the rendered
  explanations needs a run of `tools/ai/check_ask_context.py` against a real
  model before the release (it costs money, so the user launches it), and
  the reviewed report is saved as described in
  `tools/ai/ask_context_reports/README.md`.
- `skforecast_ai/skills/` and `skforecast_ai/resources/llms-base.txt` are
  synced from the skforecast repository with
  `tools/ai/sync_skforecast_assets.py`; `.github/copilot-instructions.md` is
  generated upstream. Do not edit any of them here. When a sync adds,
  removes or renames a skill, the script lists the change and the files
  maintained by hand: `llm/skills.py` (`ALL_SKILLS` and the routing
  tables, plus `tools/ai/measure_skill_tokens.py --update`), the table in
  `docs/user-guides/skills.md` (`tests/test_docs_skills_page.py` checks it
  against `ALL_SKILLS`) and the upstream-order test in
  `tests/tests_llm/test_select_skills.py`.
