# Plan: skforecast-ai Repository

## Goal

Create a new experimental repository/package, named `skforecast-ai`, that helps users build, validate, explain, and export reproducible forecasting workflows with skforecast.

The goal is not to create a black-box forecasting agent. The goal is to create an AI-assisted forecasting engineer that turns user intent and data characteristics into validated skforecast workflows.

## Naming and Repository Decisions (resolved)

- **Package name on PyPI**: `skforecast-ai` (hyphen).
- **Importable module**: `skforecast_ai` (underscore).
- **Rationale**: aligned with Python community convention for LLM-augmented wrappers (`pandas-ai`, `langchain-ai`, `vanna-ai`) and with the `<libname>-<purpose>` PyPI pattern (`dask-ml`, `sklearn-onnx`, `pytorch-lightning`). The `-ai` suffix has become the de facto signal that a package adds LLM capabilities on top of an established library.
- **Repository**: 100% separate from the skforecast core repository, from day one. Independent release cycle, independent CI, independent dependency surface (pydantic-ai, LLM SDKs, MCP libs) that must not contaminate the core. The skforecast org should host both repos side by side.

## Product Positioning

`skforecast-ai` should sit above skforecast as an optional assistant layer.

It should help users answer questions such as:

- Which skforecast forecaster should I start with?
- Are my data suitable for recursive, direct, multi-series, statistical, or foundation forecasting?
- What lags, metrics, backtesting strategy, and prediction interval method should I try first?
- How do I turn this dataset into reproducible skforecast code?
- Why did this model perform poorly?
- What experiment should I run next?

The product promise should be:

> AI-assisted forecasting workflows powered by skforecast: from dataset understanding to validated code, backtesting, model comparison, and production-ready recommendations.

Avoid positioning it as fully automated forecasting without validation. Forecasting decisions must remain explainable, reproducible, and backed by metrics.

## Target Users

### 1. Non-technical or semi-technical users

They want to upload or point to a dataset and get a forecast, explanation, and downloadable results.

Useful outputs:

- Data diagnostics.
- Forecast and intervals.
- Plain-language explanation.
- Warnings about missing values, frequency, short history, exogenous variables, or unreliable validation.
- Exportable notebook or Python script.

This audience is best served later through Skforecast Studio or a lightweight web app.

### 2. Data scientists and analysts

They can code, but want faster and safer forecasting workflows.

Useful outputs:

- Recommended forecaster.
- Reproducible skforecast code.
- Backtesting setup.
- Metrics and model comparison.
- Prediction interval strategy.
- Explanation of trade-offs.
- Next experiment suggestions.

This should be the first target audience for the MVP.

### 3. skforecast contributors and maintainers

They need help maintaining examples, docs, API references, and AI context.

Useful outputs:

- API change audits.
- Example migration suggestions.
- Documentation consistency checks.
- Generated tests or review checklists.

This can reuse the same internal planning and validation utilities, but should not drive the initial product UX.

## Reuse of Existing skforecast AI Assets

The skforecast core repository already contains substantial AI-oriented content that should not be duplicated. The strategy is **migrate, don't fork**.

### Assets currently living in skforecast core

- `llms.txt` and `llms-full.txt` — condensed API/workflow reference for LLMs.
- `tools/ai/llms-base.txt` and `tools/ai/ai_context_header.md` — source files used to generate `.github/copilot-instructions.md`.
- `skills/` folder with domain skills:
  - `choosing-a-forecaster/`
  - `forecasting-single-series/`
  - `forecasting-multiple-series/`
  - `foundation-forecasting/`
  - `statistical-models/`
  - `deep-learning-forecasting/`
  - `prediction-intervals/`
  - `hyperparameter-optimization/`
  - `feature-engineering/`
  - `feature-selection/`
  - `drift-detection/`
  - `troubleshooting-common-errors/`
  - `complete-api-reference/`
- `.github/instructions/` — docstrings and testing conventions.

### What to migrate to `skforecast-ai`

- The entire `skills/` folder. It is forecasting domain knowledge consumed by an AI layer, not by the library itself. Keeping it in the core repo creates a maintenance dependency that does not belong there.
- A copy of `llms.txt` / `llms-full.txt` packaged as a resource the assistant can load at runtime as the canonical source of truth for the recommendation engine and prompts.

### What to keep in skforecast core

- `llms.txt` / `llms-full.txt` (the source of truth lives in core, mirrored into the assistant via a sync script).
- `.github/copilot-instructions.md` and `.github/instructions/*` — these target contributors of the core library.
- `tools/ai/generate_ai_context_files.py` — generator of `llms*.txt`.

### Sync mechanism

Add a small script in `skforecast-ai` (`tools/sync_skforecast_assets.py`) that pulls a pinned version of `llms-full.txt` from the core repo into `skforecast_ai/resources/`. CI checks that the pinned version matches the latest skforecast release the assistant claims to support. This keeps a single source of truth without coupling release cycles.

### Skills as the source of truth for the recommendation engine

The deterministic rules in `recommendation/rules.py` should be derived from (and link back to) the migrated `skills/` content. Each rule cites the skill that justifies it. This avoids drift between docs and assistant behavior, and means improving a skill automatically improves the assistant.

## LLM Backend Strategy

The assistant must work for three distinct user profiles, with no LLM lock-in. The architecture is built around a **provider-agnostic abstraction** rather than a single chosen model.

### Three-tier backend strategy

| Tier | Backend | Target user | Cost | Data leaves machine? |
|------|---------|-------------|------|----------------------|
| **0. No LLM** | Deterministic rules + code templates | Users who do not want any LLM in the loop | 0 | No |
| **1. Local LLM** | Ollama, LM Studio, vLLM, llama.cpp server | Users without an API key, sensitive data, offline | 0 + local compute | No |
| **2. Cloud LLM** | OpenAI, Anthropic, Google, Groq, Mistral, etc. | Users who prioritize quality over privacy/cost | API key | Yes (controlled by `send_data_to_llm`) |

**Tier 0 must exist and be fully usable.** It is the differentiator versus a generic OpenAI wrapper. Many forecasting decisions (which forecaster, initial lags, CV strategy, interval method) are perfectly expressible as deterministic rules. The LLM only adds value for: (a) parsing natural-language intent, (b) explaining results, (c) answering open-ended questions.

### Provider abstraction via Pydantic AI

Pydantic AI supports OpenAI, Anthropic, Google, Groq, Mistral, Cohere, Bedrock natively, and **any OpenAI-compatible endpoint** via `OpenAIModel` + custom `base_url`. Local backends (Ollama, LM Studio, vLLM, llama.cpp server) are therefore not a separate integration — they reuse the OpenAI provider with a different `base_url`.

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

ollama_model = OpenAIModel(
    model_name="qwen2.5:7b-instruct",
    provider=OpenAIProvider(base_url="http://localhost:11434/v1", api_key="ollama"),
)
agent = Agent(ollama_model, output_type=ForecastPlan)
```

### Public API shape

A single string identifies the backend, parsed internally into the right Pydantic AI model:

```python
from skforecast_ai import ForecastingAssistant

# Tier 0 — deterministic, no network, no model
assistant = ForecastingAssistant(llm=None)

# Tier 1 — local via Ollama (default base_url http://localhost:11434/v1)
assistant = ForecastingAssistant(llm="ollama:qwen2.5:7b-instruct")

# Tier 1 — remote Ollama / any OpenAI-compatible endpoint
assistant = ForecastingAssistant(
    llm="ollama:qwen2.5:14b-instruct",
    base_url="http://192.168.1.50:11434/v1",
)

# Tier 2 — cloud
assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")
assistant = ForecastingAssistant(llm="anthropic:claude-sonnet-4-5")
```

### Recommended local models

Not every small model handles tool calling and Pydantic-strict JSON output reliably. Verified-working starting points for Ollama:

| Model | Size | Notes |
|-------|------|-------|
| `qwen2.5:7b-instruct` | 7B | Best size/quality/tool-calling tradeoff. **Default recommendation.** |
| `qwen2.5:14b-instruct` | 14B | Higher quality, needs ~10 GB VRAM or fast CPU |
| `llama3.1:8b-instruct` | 8B | Solid reasoning, weaker on strict JSON |
| `mistral-small:24b` | 24B | Strong, requires a decent GPU |
| `phi-4:14b` | 14B | Good reasoning |

Avoid models smaller than 7B for the main agent — they fail too often when generating JSON conforming to a Pydantic schema. Sub-7B models are fine for auxiliary tasks (intent classification, summarization).

### Operational risks for the local tier

1. **Inconsistent tool calling**: even `qwen2.5:7b` occasionally fails. Rely on Pydantic AI's built-in retry-on-validation-error and keep schemas tight.
2. **Default context window**: many local models start at 2k–4k tokens in Ollama. Set `num_ctx >= 8192` via Modelfile or per-call options.
3. **Latency**: a 7B model on CPU may take 10–30 s per response. Document expectations clearly and show progress indicators in the CLI.
4. **Backend not running**: detect Ollama unreachable and surface an actionable error (`ollama serve`, `ollama pull <model>`), not a stack trace.
5. **Tier 0 fallback**: when an LLM call fails, the assistant should fall back to Tier 0 with a warning, not crash.

### Decision summary

- **Provider**: Pydantic AI as the abstraction layer. No direct dependency on any single LLM SDK.
- **Default for users without API key**: Ollama with `qwen2.5:7b-instruct`.
- **Default for cloud users**: `openai:gpt-4o-mini` (cheap, fast, reliable structured output).
- **No LLM mode**: first-class, not an afterthought. Used by the `inspect` command and as fallback path.

## Recommended Framework

Use Pydantic AI for the first implementation.

Reasons:

- Python-first and easy to integrate with skforecast.
- Structured outputs with Pydantic models.
- Tool calling without a heavy multi-agent framework.
- Easier to test than free-form agent loops.
- Supports multiple LLM providers.
- Keeps business logic in deterministic Python functions.

Use LangGraph only later if workflows require explicit long-lived state, branching, retries, or multi-step orchestration that becomes hard to manage with Pydantic AI alone.

## Architecture

Separate the system into deterministic forecasting logic and LLM-assisted interaction.

```text
User input / dataset
        |
        v
Data profiler (deterministic)
        |
        v
Recommendation engine (mostly deterministic)
        |
        v
LLM planner/explainer (structured output)
        |
        v
Executor / validator (skforecast real code)
        |
        v
Report + code + forecast outputs
```

### 1. Data Profiler

Deterministic functions that inspect the input data.

Responsibilities:

- Detect date/time column and target column when possible.
- Infer or validate frequency.
- Detect single-series vs multi-series structure.
- Detect exogenous variables.
- Detect categorical exogenous variables.
- Detect missing values and gaps.
- Check series length vs requested steps.
- Estimate seasonality candidates.
- Identify whether future exogenous values are required.
- Generate warnings.

Example output model:

```python
class DataProfile(BaseModel):
    n_observations: int
    n_series: int
    index_type: str
    frequency: str | None
    target: str
    date_column: str | None
    series_id_column: str | None
    exog_columns: list[str]
    categorical_exog: list[str]
    missing_values: dict[str, int]
    inferred_seasonalities: list[int]
    warnings: list[str]
```

### 2. Recommendation Engine

Mostly deterministic rules that map data characteristics and user objective to a starting strategy.

Responsibilities:

- Recommend forecaster family:
  - `ForecasterRecursive`
  - `ForecasterDirect`
  - `ForecasterRecursiveMultiSeries`
  - `ForecasterDirectMultiVariate`
  - `ForecasterStats`
  - `ForecasterFoundation`
  - `ForecasterRecursiveClassifier`
  - `ForecasterEquivalentDate`
- Recommend initial lags.
- Recommend metric.
- Recommend cross-validation strategy.
- Recommend interval method.
- Recommend whether to use `dropna_from_series`.
- Recommend categorical feature handling.
- Explain why alternatives were not selected.

Example output model:

```python
class ForecastPlan(BaseModel):
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
    estimator: str | None
    steps: int
    frequency: str | None
    lags: int | list[int] | None
    metric: str
    backtesting_strategy: str
    interval_method: str | None
    use_exog: bool
    data_requirements: list[str]
    warnings: list[str]
    rationale: str
```

### 3. LLM Planner and Explainer

The LLM should not be the source of truth for forecasting logic. It should:

- Translate user intent into structured configuration.
- Ask clarifying questions when required inputs are missing.
- Explain deterministic recommendations.
- Generate readable code from a validated plan.
- Summarize backtesting results.
- Answer user questions using actual computed outputs.

All LLM outputs that affect execution should be validated with Pydantic schemas.

### 4. Executor and Validator

Runs actual skforecast workflows.

Responsibilities:

- Build the forecaster.
- Fit the model.
- Run backtesting.
- Compare with baseline.
- Generate prediction intervals when requested.
- Return forecasts as pandas DataFrames.
- Produce reproducible code.
- Surface warnings and failures clearly.

Execution should be optional in early MVP. Code generation and recommendation can ship before full auto-run.

## MVP Scope

Build a package/CLI that targets analysts and developers first.

### MVP Commands

```bash
skforecast-ai inspect data.csv
skforecast-ai recommend data.csv --date date --target sales --steps 30
skforecast-ai generate-code data.csv --date date --target sales --steps 30
```

Optional after MVP:

```bash
skforecast-ai run data.csv --date date --target sales --steps 30
skforecast-ai explain results.json --question "Why is the error high?"
```

### MVP Python API

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")

result = assistant.recommend(
    data=data,
    target="sales",
    date_column="date",
    steps=30,
)

print(result.plan)
print(result.code)
print(result.warnings)
```

### MVP Outputs

- `DataProfile`
- `ForecastPlan`
- Generated Python script
- Human-readable explanation
- Warnings and assumptions

Do not require an LLM for `inspect`. Ideally, `recommend` should have a deterministic mode and an LLM-enhanced mode.

## Suggested Repository Structure

```text
skforecast-ai/
├── pyproject.toml
├── README.md
├── docs/
├── examples/
├── tests/
├── skforecast_ai/
│   ├── __init__.py
│   ├── assistant.py
│   ├── cli.py
│   ├── schemas.py
│   ├── profiling/
│   │   ├── __init__.py
│   │   ├── data_profile.py
│   │   └── frequency.py
│   ├── recommendation/
│   │   ├── __init__.py
│   │   ├── rules.py
│   │   └── forecaster_selection.py
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── code_templates.py
│   │   └── notebooks.py
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── runner.py
│   │   └── validation.py
│   └── llm/
│       ├── __init__.py
│       ├── pydantic_ai_agent.py
│       └── prompts.py
└── tests/
    ├── test_data_profile.py
    ├── test_recommendation_rules.py
    ├── test_code_generation.py
    └── test_cli.py
```

## Core Design Principles

1. Deterministic first, LLM second.
2. Every recommendation must be reproducible as skforecast code.
3. Every executed forecast should include validation or an explicit warning when validation is not possible.
4. Use structured outputs, not free-form agent decisions.
5. Keep the package optional and separate from skforecast core initially.
6. Avoid heavy foundation-model dependencies in the MVP.
7. Treat data privacy as a first-class concern.
8. Prefer clear warnings over silent automation.

## Data Privacy

The assistant should make clear what is sent to an LLM provider.

Recommended default:

- Do not send raw full datasets to the LLM.
- Send only schema, inferred metadata, summary statistics, and small sanitized samples when needed.
- Allow a local/no-LLM mode.
- Expose a `send_data_to_llm=False` option.

Example:

```python
assistant = ForecastingAssistant(
    llm="openai:gpt-4o-mini",
    send_data_to_llm=False,
)
```

## Testing Strategy

### Unit Tests

- Frequency inference.
- Missing value detection.
- Data shape classification.
- Single-series vs multi-series detection.
- Exog detection.
- Forecaster recommendation rules.
- Code generation snapshots.
- Pydantic schema validation.

### Golden Prompt Tests

Maintain a set of user requests and expected structured outputs.

Examples:

- "I have one daily sales series and want 30 days ahead."
- "I have 100 stores with daily demand."
- "I have hourly data and weather exog."
- "I want zero-shot forecasting with Chronos."
- "My series has missing values."

### Integration Tests

Use small built-in skforecast datasets.

- Generate code.
- Execute generated code.
- Verify forecast shape.
- Verify backtesting output has expected columns.
- Verify warnings are produced for missing future exog.

## Documentation Plan

Initial docs:

- What is skforecast-ai?
- Installation and LLM provider setup.
- No-LLM deterministic mode.
- CLI quickstart.
- Python API quickstart.
- Data privacy and what is sent to the LLM.
- From recommendation to executable skforecast code.
- Troubleshooting common inputs.

Examples:

- Single-series daily demand.
- Multiple-series retail sales.
- Exogenous variables with known future values.
- Bad data diagnostics.

## Roadmap

### Phase 0: Design Spike

- Decide package name.
- Decide whether repository is separate or under skforecast organization.
- Prototype `DataProfile` and `ForecastPlan` schemas.
- Prototype CLI shape.
- Pick LLM provider abstraction.

### Phase 1: Deterministic Assistant

- Implement `inspect`.
- Implement rule-based `recommend`.
- Implement code generation for `ForecasterRecursive`.
- Add tests for data profiling and recommendation.
- Add README with first examples.

### Phase 2: LLM-Enhanced Assistant

- Add Pydantic AI integration.
- Add natural-language question parsing.
- Add structured plan validation.
- Add explanation generation from deterministic plan.
- Add provider configuration and privacy controls.

### Phase 3: Execution and Evaluation

- Add `run` command.
- Execute generated workflows.
- Add backtesting and baseline comparison.
- Add prediction intervals.
- Export markdown reports and notebooks.

### Phase 4: Multi-Series and Exog

- Add robust support for wide, long, and dict-style multi-series inputs.
- Add exog future-steps validation.
- Add categorical feature recommendations.
- Add `ForecasterRecursiveMultiSeries` workflows.

> **Out of scope for this roadmap**: Studio integration is a separate product decision and will be planned independently if and when the assistant reaches sufficient maturity.

## Open Questions

- Should generated code target only stable skforecast APIs or also optional dependencies like LightGBM?
- Should the assistant execute forecasts by default or only generate code until the user opts in?
- How should sensitive data handling be communicated in CLI and docs?
- Should the assistant also be exposed as an MCP server (in addition to the CLI/Python API) so it can be consumed from Claude Desktop, Cursor, and Copilot without re-implementing an agent loop?

## First Implementation Milestone

A realistic first milestone:

1. Create the new repository.
2. Add `pyproject.toml`, CLI entrypoint, and package skeleton.
3. Implement `DataProfile`.
4. Implement deterministic recommendations for single-series forecasting.
5. Generate executable code for `ForecasterRecursive` with backtesting.
6. Add tests and example datasets.
7. Publish an internal preview.

Success criteria:

- A user can run one command on a CSV and get a clear recommendation plus executable skforecast code.
- The output explains assumptions and warnings.
- The generated code passes a smoke test.
- No raw dataset is sent to an LLM by default.
