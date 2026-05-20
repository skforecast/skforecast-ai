# skforecast-ai — Package Evaluation

## Purpose

`skforecast-ai` is an AI-powered forecasting assistant that wraps the `skforecast` library to provide an automated, opinionated pipeline from raw data to forecasting results. It aims to:

1. **Automate forecaster selection** — given a dataset, deterministically choose the right forecaster class and estimator based on data characteristics (single vs multi-series, observation count, presence of exog, etc.).
2. **Generate production-ready code** — output a self-contained Python script that users can inspect, copy, and customize.
3. **Execute forecasts programmatically** — run the generated code and return structured results (predictions, metrics, intervals).
4. **Provide LLM-powered explanations** — optionally use an LLM (OpenAI, Ollama) to explain decisions and answer questions, augmented with domain-specific skills.

The core design principle is **deterministic-first**: all modeling decisions (forecaster, estimator, lags, preprocessing) are made by rule-based logic. The LLM is only used for natural-language explanations and Q&A — never for forecasting decisions.

---

## What's Good

### Architecture & Design

- **Clean separation of concerns** — Profiling, recommendation, code generation, execution, and LLM layers are well-isolated modules with clear boundaries.
- **Deterministic-first philosophy** — The LLM is a presentation layer, not a decision-maker. This makes the package reproducible and testable without LLM mocking for the core pipeline.
- **Two-stage workflow (profile → plan)** — Gives users control: inspect the profile, override the forecaster/estimator, then generate the plan. The `refine_plan()` method makes iteration ergonomic.
- **Code fidelity guarantee** — The exact code shown to users is the same code that runs internally (`run_forecast` executes the output of `generate_template`). No hidden logic.
- **Graceful LLM degradation** — If the LLM call fails, the assistant still returns deterministic results with a warning. Non-LLM methods (`profile`, `generate_plan`, `forecast`, `generate_code`) work fully offline.

### Implementation Quality

- **PACF-based lag selection** — Data-driven rather than fixed heuristics. Uses `calculate_lag_autocorrelation` from skforecast itself, enriches with seasonal lags, prunes redundant lags when rolling windows cover them.
- **Pydantic schemas throughout** — `DataProfile`, `ForecastingProfile`, `ForecastPlan`, `ForecastResult` are all strongly typed. Makes serialization, validation, and IDE support seamless.
- **Skill system** — 14 curated markdown skills with token budgets, deterministic routing (task_type → skills), keyword augmentation, and conflict resolution. Well thought-out token management for Ollama's limited context.
- **Comprehensive code templates** — Handles 5 forecaster types (single ML, multi-series, multivariate, statistical, foundation) with proper imports, preprocessing, train/test split, metrics, and intervals.
- **Privacy-conscious** — `send_data_to_llm=False` by default; only metadata goes to the LLM. Good default for enterprise use.
- **Ollama-first local LLM support** — Dynamic context sizing, reachability checks, sensible defaults. Cloud and local LLMs work through the same interface.

### Testing

- Good coverage of the deterministic pipeline (profiling, recommendation, plan generation, execution).
- Tests use real data fixtures — not just mocks — ensuring the generated code actually runs.
- End-to-end `forecast()` tests cover all 5 forecaster types, intervals, custom kwargs, and error paths.

### Developer Experience

- Single entry point (`ForecastingAssistant`) with sensible defaults and progressive complexity.
- Jupyter-friendly (`nest_asyncio` patching, rich output).
- `generate_code_from_plan()` for power users who want to tweak the plan before code generation.

---

## What's Bad / Needs Improvement

### Code Execution via `exec()`

- **Security risk** — `_exec_generated_code` uses `exec()` on generated code strings. While the code is self-generated (not user-provided), it executes in the caller's Python process without sandboxing. A malformed template or edge case could cause side effects.
- **Debugging difficulty** — Stack traces from `exec()`'d code are hard to map back to the template. The `ForecastExecutionError` captures the traceback, but users can't set breakpoints or step through it.
- **No timeout or resource limits** — A large dataset + complex model could run indefinitely.

### Forecaster Selection Logic is Too Simplistic

- **Binary decision** — `n_series > 1 → ForecasterRecursiveMultiSeries`, else `ForecasterRecursive`. Doesn't consider:
  - Whether series are correlated (multivariate might be better)
  - Whether the user has very few series with many observations (single-series per series might outperform global)
  - Data frequency and horizon length (direct might beat recursive for long horizons)
- **Estimator selection** — Only considers `n_observations`: LightGBM if ≥250, Ridge otherwise. Doesn't account for feature count, non-linearity, or presence of categorical variables.

### Missing Features in Recommendation Engine

- **No differentiation logic** — `differentiation` parameter is in `build_forecaster_kwargs` but never actually selected (always None). Non-stationary series detection is marked TODO.
- **No trend/seasonality decomposition** — `target_has_trend` is always None. Would improve lag/window selection.
- **Encoding strategy for multi-series** — Hardcoded to `'ordinal'`. No consideration of series count (onehot might be better for few series).
- **No weight_func recommendation** — For series with imputed NaN regions, weighting is the recommended approach per skforecast docs but isn't surfaced.

### Code Generation Limitations

- **No backtesting in generated code** — Generated scripts only do a single train/test split with `predict()`. No `backtesting_forecaster` call, which is the proper evaluation method per skforecast best practices.
- **No hyperparameter tuning** — The generated code uses fixed hyperparameters. No template for grid/random/bayesian search.
- **Fixed 80% train/test split** — No consideration of forecast horizon, seasonality, or minimum training requirements.

### CLI is Empty

- The CLI (`cli.py`) is scaffolded but has zero commands. This is a declared public entry point (`skforecast-ai`) that does nothing.

### Error Handling Gaps

- **`_coerce_to_dataframe`** — If a CSV path doesn't exist, the error message won't clearly tell the user what went wrong (just a generic pandas error).
- **No validation of `interval` parameter** — User can pass `[90, 10]` (inverted), `[0, 100]`, or `[-5, 105]` without validation.
- **No steps vs data length check** — If `steps > n_observations`, the generated code will fail at runtime with a cryptic error.

### LLM Layer

- **No streaming support** — `agent.run_sync()` blocks until the full response is ready. For long explanations, this gives no feedback to the user.
- **No conversation memory** — Each `ask()` call is stateless. Can't follow up on a previous answer.
- **Hardcoded retry count** — 2 retries with no exponential backoff or configurable strategy.
- **No token counting for cloud providers** — Token budget management only applies to Ollama. OpenAI/Anthropic calls don't track usage or warn about costs.

### Testing Gaps

- **No tests for the CLI** — `test_cli.py` exists but probably has minimal coverage since the CLI is empty.
- **No integration tests with real LLMs** — All LLM tests likely mock the agent. No validation that the skills + prompts produce useful outputs.
- **No edge-case tests for code templates** — Templates with all optional features (intervals + exog + window features + preprocessing) combined.
- **No fuzz testing for data profiling** — Edge cases like: all-NaN columns, single-row DataFrames, constant series, mixed timezones.

---

## What's Missing

### High Priority

1. **Backtesting template** — Generated code should include `backtesting_forecaster()` with `TimeSeriesFold` as the primary evaluation method, not just a single predict-and-compare.
2. **Hyperparameter search integration** — At minimum, a `suggest_search_space()` method that returns an Optuna search space dict based on the chosen estimator.
3. **CLI commands** — At least: `profile`, `plan`, `generate-code`, `forecast`, `ask`. This is the most visible gap for new users.
4. **Input validation** — Validate `interval`, `steps` vs data length, forecaster/estimator string typos, and exog_future shape.
5. **Stationarity detection** — Use ADF/KPSS tests to recommend `differentiation` parameter.

### Medium Priority

6. **Multi-step plan comparison** — Run 2-3 candidate forecasters via backtesting, return a comparison table. This is what most users actually need to make a decision.
7. **Explain generated code** — A method that takes a `ForecastResult` and produces a section-by-section explanation of the code (what each block does and why).
8. **Exogenous variable analysis** — Correlation with target, lead/lag relationships, feature importance ranking.
9. **Persistence** — Save/load profiles, plans, and results. Resume a session without re-profiling.
10. **Streaming `ask()`** — Yield tokens as they arrive for better UX in notebooks and CLIs.
11. **Logging / observability** — Structured logging for the pipeline stages. Currently silent (except warnings).

### Lower Priority

12. **Custom estimator support** — Allow users to pass a fitted estimator instance, not just a class name string.
13. **Data visualization recommendations** — Suggest plots (ACF/PACF, seasonal decomposition, residual analysis) based on the profile.
14. **Deployment template** — Generate code for production deployment (model serialization, monitoring, retraining schedule).
15. **Multi-language code generation** — R code generation for the same pipeline (niche but differentiating).
16. **Benchmarking mode** — Compare against naive baselines (last value, seasonal naive, drift) to contextualize metrics.

---

## Suggested Next Steps (Priority Order)

| # | Task | Impact | Effort |
|---|------|--------|--------|
| 1 | **Implement CLI commands** (profile, plan, generate-code, forecast) | High — makes the package usable without Python | Medium |
| 2 | **Add backtesting to generated code** | High — current evaluation is unreliable | Medium |
| 3 | **Input validation layer** (interval, steps, exog shapes) | High — prevents confusing runtime errors | Low |
| 4 | **Stationarity detection → differentiation** | Medium — improves forecast quality | Low |
| 5 | **Streaming `ask()`** | Medium — UX improvement | Low-Medium |
| 6 | **Multi-forecaster comparison** | High — key user need | High |
| 7 | **Hyperparameter search template** | Medium — next step after baseline | Medium |
| 8 | **Better estimator selection heuristics** | Medium — more intelligent defaults | Medium |
| 9 | **Add logging throughout pipeline** | Low-Medium — helps debugging | Low |
| 10 | **Conversation memory for `ask()`** | Medium — enables follow-up questions | Medium |

---

## Summary

`skforecast-ai` is a well-architected v0.1 with a strong deterministic core and a thoughtful LLM integration pattern. The separation between "decision logic" and "explanation layer" is the right approach for a forecasting tool — you don't want an LLM choosing your lag structure.

The main gaps are around **evaluation quality** (no backtesting in generated code), **user-facing completeness** (empty CLI, no comparison mode), and **robustness** (input validation, stationarity detection). The code generation templates are solid for single-run forecasting but don't yet reflect the iterative workflow that real forecasting projects require (backtest → tune → compare → deploy).

The foundation is strong. The next milestone should focus on making the deterministic pipeline production-quality before expanding the LLM features.
