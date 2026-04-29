---
description: 'Master conventions for the skforecast-ai project. Covers project layout, Python style, docstrings, type hints, testing, dependencies, LLM/agent code patterns, deterministic-first principles, and security. Apply to all source and test files in skforecast-ai.'
applyTo: '**/*.py'
---
# skforecast-ai Project Conventions

These rules mirror the conventions established in the skforecast core library and adapt them for the AI-assistant project. Follow them strictly when generating, editing, or reviewing code in `skforecast-ai`.

## 0. Core Principles

1. **Deterministic first, LLM second.** The LLM is never the source of truth for forecasting decisions. Every recommendation must be reproducible from deterministic Python code.
2. **Structured outputs only.** Any LLM output that affects execution must be validated by a Pydantic model. Free-form text is allowed only for human-facing explanations.
3. **No silent automation.** When the assistant cannot validate something (e.g., short series, missing future exog), it warns explicitly. Never hide assumptions.
4. **Privacy by default.** Raw datasets are never sent to an LLM unless the user explicitly opts in (`send_data_to_llm=True`). Only schema, summary stats, and small sanitized samples may leave the machine.
5. **Reuse, don't reinvent.** Domain knowledge lives in `skforecast_ai/skills/` (migrated from skforecast core). Recommendation rules cite the skill that justifies them.
6. **Avoid over-engineering.** Implement only what is requested or clearly necessary. No speculative features, helpers, or abstractions for one-time operations.

## 1. Project Layout

```
skforecast-ai/
├── pyproject.toml
├── README.md
├── ruff.toml
├── .github/
│   ├── instructions/
│   │   ├── docstrings.instructions.md
│   │   ├── testing.instructions.md
│   │   └── llm-agent.instructions.md
│   └── workflows/
├── docs/
├── examples/
├── skforecast_ai/                  # Importable module (underscore)
│   ├── __init__.py
│   ├── assistant.py                # Public ForecastingAssistant
│   ├── cli.py                      # Typer-based CLI
│   ├── schemas.py                  # Pydantic models (DataProfile, ForecastPlan)
│   ├── profiling/                  # Deterministic data inspection
│   ├── recommendation/             # Deterministic rule engine
│   ├── generation/                 # Code/notebook templates
│   ├── execution/                  # Optional: run forecasts and validate
│   ├── llm/                        # Pydantic AI integration
│   ├── skills/                     # Migrated from skforecast core
│   ├── resources/                  # Synced llms-full.txt, prompts, etc.
│   └── exceptions/                 # Custom warnings and errors
├── tests/
│   ├── __init__.py
│   ├── tests_profiling/
│   ├── tests_recommendation/
│   ├── tests_generation/
│   ├── tests_llm/                  # Mocked LLM tests
│   └── fixtures_*.py               # Shared fixtures
└── tools/
    └── sync_skforecast_assets.py   # Pulls pinned llms-full.txt
```

- **PyPI name**: `skforecast-ai` (hyphen). **Importable**: `skforecast_ai` (underscore).
- One responsibility per subpackage. No god-modules.
- Tests mirror source structure: `skforecast_ai/profiling/` → `tests/tests_profiling/`.

## 2. Dependencies

### Core (always installed)

- `python>=3.11`
- `pydantic>=2.7`
- `pandas>=2.1,<3.0`
- `numpy>=1.26`
- `skforecast>=0.22`            # Pinned in `tools/sync_skforecast_assets.py`
- `typer>=0.12`                 # CLI
- `rich>=13.9`                  # CLI output

### Optional extras

- `[llm]`: `pydantic-ai>=0.0.14`
- `[ollama]`: `pydantic-ai>=0.0.14` (same dependency, separate extra for clarity)
- `[mcp]`: `mcp>=1.0` (when MCP server is added)
- `[dev]`: `pytest`, `pytest-cov`, `pytest-xdist`, `ruff`, `mypy`

The Tier 0 deterministic mode must work with **only the core dependencies installed**. Importing `skforecast_ai` without the `[llm]` extra must succeed.

## 3. Python Style

- **Ruff** is the single source of truth. Reuse the skforecast core `ruff.toml` (selected rules `E`, `F`; ignored `E221`, `E251`, `E501`, `E241`; `quote-style = "double"`; `max-line-length = 88`).
- **PEP 8** compliant.
- **Double quotes** for strings.
- **Relative imports** within the package (`from .schemas import ForecastPlan`, not `from skforecast_ai.schemas import ...`).
- **Type hints required** on every public function, method, and class attribute. Use `|` union syntax (Python 3.11+), `list[...]`, `dict[...]` — not `Union[]` or `List[]`.
- **No comments** unless they explain *why*, not *what*. The code itself documents *what*.
- **No emojis** in source code or messages.
- **Aligned keyword arguments** in long constructor calls (mirroring skforecast):
  ```python
  assistant = ForecastingAssistant(
                  llm              = "ollama:qwen2.5:7b-instruct",
                  send_data_to_llm = False,
                  base_url         = "http://localhost:11434/v1",
              )
  ```

## 4. Docstrings

Use **NumPy-style** docstrings for every public class, method, and function. Follow the skforecast core conventions exactly:

- **Single backticks** only — never double.
- **Readable type names** in docstrings: `pandas Series`, `pandas DataFrame`, `numpy ndarray` (not `pd.Series`, `np.ndarray`).
- **Section order**: Summary → Parameters → Attributes (classes only) → Returns → Notes → References.
- **Never** add `Raises`, `Warnings`, `See Also`, or `Yields` sections.
- **Default values** on the type line: `name : type, default value`.
- **Description indentation**: 4 spaces from the parameter name.
- **No rST cross-reference directives** (`:class:`, `:func:`, `:meth:`). Use plain single backticks.

Example:

```python
def recommend(
    data: pd.DataFrame,
    target: str,
    horizon: int,
    date_column: str | None = None,
) -> ForecastPlan:
    """
    Generate a deterministic forecasting plan from a dataset and user intent.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset containing the target series and optional exogenous variables.
    target : str
        Name of the column to forecast.
    horizon : int
        Number of steps ahead to predict.
    date_column : str, default None
        Name of the column with timestamps. If None, the index is assumed
        to be a DatetimeIndex.

    Returns
    -------
    plan : ForecastPlan
        Structured plan with the recommended forecaster, lags, metric,
        backtesting strategy, and rationale.

    Notes
    -----
    The recommendation is fully deterministic. The LLM is not invoked by
    this function. To add an LLM-generated explanation on top, use
    `ForecastingAssistant.recommend(..., explain=True)`.
    """
```

For full docstring rules see the skforecast core file `.github/instructions/docstrings.instructions.md` (keep a copy in `skforecast-ai/.github/instructions/`).

## 5. Pydantic Schemas

Every artifact crossing a module boundary must be a typed Pydantic model.

```python
from pydantic import BaseModel, Field
from typing import Literal


class ForecastPlan(BaseModel):
    """Validated plan produced by the recommendation engine."""

    task_type: Literal[
        "single_series",
        "multi_series",
        "multivariate",
        "statistical",
        "foundation",
        "classification",
        "baseline",
    ]
    forecaster: str
    estimator: str | None = None
    horizon: int = Field(gt=0)
    frequency: str | None = None
    lags: int | list[int] | None = None
    metric: str
    backtesting_strategy: str
    interval_method: Literal["bootstrapping", "conformal"] | None = None
    use_exog: bool = False
    data_requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rationale: str
```

Rules:

- Use `Literal` for closed enums, not bare strings.
- Validate ranges with `Field(gt=..., ge=..., le=...)`.
- Default mutable types via `Field(default_factory=list)`, never `default=[]`.
- LLM-produced models must round-trip through `.model_validate_json()` to guarantee the LLM output conforms to the schema.

## 6. LLM and Agent Code

### Provider abstraction

Use **Pydantic AI** as the only abstraction layer. Do not import `openai`, `anthropic`, or any provider SDK directly.

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider


def build_model(llm: str, base_url: str | None = None):
    """Resolve an `llm` string into a Pydantic AI model instance."""
    if llm.startswith("ollama:"):
        model_name = llm.split(":", 1)[1]
        return OpenAIModel(
            model_name=model_name,
            provider=OpenAIProvider(
                base_url=base_url or "http://localhost:11434/v1",
                api_key="ollama",
            ),
        )
    # OpenAI, Anthropic, Google, etc. resolved by Pydantic AI directly
    return llm
```

Supported `llm` string formats:

- `None` → Tier 0, no LLM
- `"ollama:<model>"` → local via Ollama (or any OpenAI-compatible endpoint)
- `"openai:<model>"`, `"anthropic:<model>"`, `"google-gla:<model>"`, etc. → cloud

### Agent construction

- One `Agent` per task. Do not share agents across unrelated workflows.
- Always set `output_type=<PydanticModel>` to force structured output.
- Always set `system_prompt` from a constant in `skforecast_ai/llm/prompts.py`. Never inline long prompts.
- Configure retries on validation errors (Pydantic AI default) — do not silence them.
- On any LLM failure, fall back to Tier 0 deterministic mode and emit a warning. Never crash because the LLM was unreachable.

### What the LLM must NOT do

- Decide hyperparameters or lags numerically — those come from rules + search.
- Execute generated code without sandboxing.
- See raw datasets unless `send_data_to_llm=True`.
- Replace deterministic validation. Backtesting metrics always come from real skforecast runs.

## 7. Skills as the Source of Truth

- `skforecast_ai/skills/` contains the migrated `SKILL.md` files.
- Every recommendation rule in `recommendation/rules.py` must cite the skill it derives from in a docstring tag:
  ```python
  def recommend_forecaster_for_single_series(profile: DataProfile) -> str:
      """
      Choose between ForecasterRecursive and ForecasterDirect for a single series.

      Notes
      -----
      Source: `skforecast_ai/skills/choosing-a-forecaster/SKILL.md`
      """
  ```
- When a skill is updated, the corresponding rule must be reviewed in the same PR.
- Skills are loaded as plain text into LLM prompts; do not parse them as structured data.

## 8. Testing

Follow the skforecast core testing conventions. Summary of the most important rules:

- **One test file per public method/function**: `test_<method_name>.py`.
- **Test docstrings** are mandatory and explain what the test verifies.
- **Naming**: `test_<method>_<scenario>`, `test_<method>_<ErrorType>_when_<condition>`, `test_<method>_output_when_<condition>`.
- **Fixtures** are module-level variables (not `@pytest.fixture`) in `fixtures_<module>.py`, imported with relative imports.
- **Hardcoded expected values** — never compute the expected result inside the test.
- **Parametrize** to combine variations of the same logic; group related assertions in one test.
- **Errors and warnings** asserted with `re.escape()` + `pytest.raises(match=...)` / `pytest.warns(match=...)`.
- **Pandas comparisons**: `pd.testing.assert_frame_equal` / `assert_series_equal`.
- **Numpy comparisons**: `np.testing.assert_array_almost_equal`.
- **Never** use `pytest.approx` for arrays.
- Mark long tests with `@pytest.mark.slow`.

### LLM-specific testing

- **Mock the model** in unit tests. Use `pydantic_ai.models.test.TestModel` (Pydantic AI's built-in mock) with deterministic outputs.
- **Golden prompt corpus**: maintain `tests/golden/` with `(user_input, expected_plan.json)` pairs. Run them against `TestModel` for unit tests and optionally against real Ollama in a separate `@pytest.mark.integration` suite.
- **Never call real cloud APIs from CI** unless explicitly marked `@pytest.mark.live` and gated behind an env var.
- **Snapshot tests** for generated code: compare the generated script against a stored expected file. Update via a `--snapshot-update` flag, never silently.

For full testing rules see the skforecast core file `.github/instructions/testing.instructions.md` (keep a copy in `skforecast-ai/.github/instructions/`).

## 9. Code Generation

Generated code (the output of `generate-code` and `recommend(..., return_code=True)`) must be:

- **Self-contained**: every import explicit, no reliance on REPL state.
- **Reproducible**: every random source seeded with `random_state=123` (matching skforecast convention).
- **Backtestable**: include a `backtesting_forecaster` block with a defined `TimeSeriesFold`.
- **Commented with rationale**: each non-obvious choice (lags, metric, CV strategy) carries a one-line `# Rationale: ...` comment citing the skill or rule.
- **Smoke-tested in CI**: every template must execute end-to-end against a built-in skforecast dataset.

Templates live in `skforecast_ai/generation/templates/` as Jinja2 files. Do not f-string complex code generation.

## 10. CLI Conventions

- Use **Typer** (not argparse, not click directly).
- Subcommands: `inspect`, `recommend`, `generate-code`, `run` (later), `explain-error` (later).
- Output format: human-readable by default (Rich tables/panels), JSON via `--json` flag.
- Exit codes: `0` success, `1` user error (bad inputs), `2` runtime error, `3` LLM unavailable (with fallback message).
- Never print a stack trace to the user. Catch known errors and translate to actionable messages.

## 11. Security

- **No `eval`, no `exec`** on LLM output. Generated code is **written to disk** and the user runs it explicitly. The `run` command (Phase 3) executes in a subprocess with a timeout, in a temporary cwd, never in the parent process.
- **No URL fabrication**. Documentation links must come from a curated constant or from `skforecast_ai/resources/`.
- **No secrets in logs**. Mask API keys (`sk-***`) in any logged HTTP error.
- **Validate file paths** from user input. Reject paths outside the working directory.
- **Pin LLM provider versions** in `pyproject.toml` to avoid breaking changes from upstream SDKs.

## 12. Versioning and Releases

- Semantic versioning. Pre-1.0 versions may break public API; document every break in `changelog.md`.
- The `skforecast` version against which the assistant is validated is recorded in `skforecast_ai/_skforecast_compat.py`:
  ```python
  SUPPORTED_SKFORECAST_MIN = "0.22.0"
  SUPPORTED_SKFORECAST_MAX = "0.23.0"  # exclusive
  ```
- The sync script (`tools/sync_skforecast_assets.py`) refuses to run if the local skforecast version is outside this range.

## 13. What NOT to Do

- Do not couple `skforecast-ai` releases to `skforecast` releases — they ship independently.
- Do not duplicate forecasting logic that already exists in skforecast. Always call into the library.
- Do not add a "decision-making" LLM agent that picks forecasters without consulting the deterministic rule engine.
- Do not store user data, prompts, or LLM responses unless the user opts in to telemetry.
- Do not introduce a multi-agent framework. One agent per task is sufficient.
- Do not add Studio-related code in this repo. Studio integration is a separate product decision.
- Do not auto-install Ollama or any LLM provider on import. Detect, instruct, and let the user decide.
