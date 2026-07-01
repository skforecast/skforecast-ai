# LLM-Guided Plan Refinement for Time Series Features

## Background & Motivation
Currently, `ForecastingAssistant` computes `lags` and `window_features` deterministically via `compute_series_pacf` and frequency analysis. Users cannot manually override these specific features in the `plan()` or `refine_plan()` methods, nor is there a structured way to leverage domain knowledge (e.g., "This is retail sales data with strong weekly and annual seasonality") via the LLM to guide these configurations. 

This feature will allow users to provide natural language context about their time series to generate an optimized, LLM-guided configuration for `lags` and `window_features`.

## Scope & Impact
*   `skforecast_ai/schemas/plans.py`: `PlanOverrides` and `WindowFeature` schemas.
*   `skforecast_ai/llm/prompts.py`: `_PLAN_REFINEMENT_ROLE_PROMPT`.
*   `skforecast_ai/llm/agent.py`: `PlanRefinementDeps` and `create_plan_refinement_agent`.
*   `skforecast_ai/assistant.py`: `plan()`, `refine_plan()`, `forecast()`, `forecast_code()`, and backtest-resolution helpers accept manual `lags`/`window_features` overrides, validated by `_max_feature_span()`/`_MAX_FEATURE_FRACTION`. New `refine_plan_with_llm()`.
*   `skforecast_ai/cli.py`: `plan`, `refine-plan`, `forecast`, `forecast-code`, `backtest`, `backtest-code` commands expose `--lags`/`--window-features`; `refine-plan` adds `--prompt`. New `_parse_lags`/`_parse_window_features` helpers.
*   `tests/test_assistant_refine_plan.py`, `tests/test_cli.py`: coverage for overrides, the data-budget guard, and CLI parsing.

## Implemented Solution: Structured Agentic Approach

We implemented a **Structured Agentic Approach** to ensure the LLM's recommendations are perfectly formatted and rigorously validated before touching the deterministic plan.
1. **API Expansion:** Explicit overrides for `lags` and `window_features` in the deterministic `plan()` and `refine_plan()` methods.
2. **Structured Agent:** A Pydantic-AI agent (`create_plan_refinement_agent`) constrained to output a `PlanOverrides` schema. It has access to the `feature-engineering` and `autocorrelation-and-lag-selection` skills.
3. **Integration:** A `refine_plan_with_llm()` method in `ForecastingAssistant` that accepts a domain knowledge prompt, calls the agent, and feeds the resulting structured overrides back into `refine_plan()`.
4. **Data-budget guard:** Because explicit overrides (manual or LLM) bypass the PACF-based `finalize_lags` safety net, `plan()` independently validates that the largest lag/window span stays within the same budget (`33%` of observations) that the deterministic path enforces.

## Implementation Summary

### Phase 1: Schemas & Prompts
1. **Schema Definition:** In `skforecast_ai/schemas/plans.py`:
   *   `WindowFeature` — a typed sub-model with `stats: list[str]` and `window_sizes: int | list[int]`, used instead of a bare `dict` so the LLM gets a precise JSON schema and malformed entries are caught at parse time.
   *   `PlanOverrides`:
       *   `lags`: `list[int] | int | None`
       *   `window_features`: `list[WindowFeature] | None`
       *   `reasoning`: `str` (explanation of why the LLM chose these features based on the user's prompt).
2. **Role Prompt:** In `skforecast_ai/llm/prompts.py`, `_PLAN_REFINEMENT_ROLE_PROMPT` instructs the agent to act as an expert time series feature engineer, analyzing the user's domain knowledge alongside the `DataProfile` and current `ForecastPlan` to output optimized lags and window features, keeping `max_lag` under `~33%` of observations.

### Phase 2: Agent Configuration
1. **Dependencies:** In `skforecast_ai/llm/agent.py`, `PlanRefinementDeps` is a dataclass containing the `ForecastingProfile`, `ForecastPlan`, and the user's prompt.
2. **Agent Creation:** `create_plan_refinement_agent(model)` returns an `Agent[PlanRefinementDeps, PlanOverrides]`.
3. **Dynamic Skills:** The `@agent.instructions` decorator dynamically injects dataset context (observations, frequency, horizon, current lags/window features) and loads the `feature-engineering` and `autocorrelation-and-lag-selection` skills.

### Phase 3: Core Assistant Updates
1. **`plan()` Method:**
   *   Accepts `lags: int | list[int] | None = None` and `window_features: list[dict] | None = None`.
   *   Bypasses `finalize_lags` when `lags` is explicitly provided; bypasses the profile's `window_features` when `window_features` is explicitly provided.
   *   **Validates the data budget** for any explicit override via `_max_feature_span()` before building `forecaster_kwargs`, raising `ValueError` if the largest lag/window exceeds `int(span_index_length * 0.33)`.
2. **`refine_plan()` Method:**
   *   `"lags"` and `"window_features"` are part of `allowed_keys`.
   *   When not explicitly overridden, `lags`/`window_features` default to the values already stored in `plan.forecaster_kwargs` — so refining an unrelated field (e.g. `steps`) preserves existing features instead of re-running PACF-based selection. Documented in the method's docstring.
3. **`refine_plan_with_llm()` Method:**
   *   Signature: `def refine_plan_with_llm(self, profile, plan, prompt) -> tuple[ForecastPlan, str]`.
   *   Logic: validates LLM presence (raises `LLMRequiredError` if none configured), runs `create_plan_refinement_agent` synchronously, converts the typed `WindowFeature` models back to plain dicts (the format the deterministic plan pipeline stores/renders), calls `self.refine_plan()`, and returns the updated plan alongside the LLM's `reasoning`.
   *   **Failure contract:** a broad `except Exception` catches agent/network/budget-validation failures, emits a `UserWarning`, and returns `(plan, "LLM refinement failed: {exc}")` — the `"LLM refinement failed:"` prefix lets callers distinguish a failure message from genuine reasoning text.

### Phase 4: CLI & Wrapper Method Updates
1. **Pass-through Arguments:** `forecast()`, `forecast_code()`, `backtest()`, and `backtest_code()` in `assistant.py` accept and forward `lags` and `window_features`.
2. **CLI Commands:** In `skforecast_ai/cli.py`:
   *   `--lags` (validated to be positive integers via `_parse_lags`) and `--window-features` (JSON array, parsed via `_parse_window_features`) are available on `plan`, `refine-plan`, `forecast`, `forecast-code`, `backtest`, and `backtest-code`.
   *   The `refine-plan` command has an optional `--prompt` argument. The deterministic override spinner ("Refining plan...") completes and closes *before* the LLM spinner ("Refining plan with AI...") opens — Rich only supports one active `console.status` at a time, so the two steps run sequentially, not nested.

## Verification & Testing

Implemented in `tests/test_assistant_refine_plan.py` and `tests/test_cli.py`:
*   `plan()` / `refine_plan()` correctly apply `lags` and `window_features` overrides (`test_refine_plan_output_when_lags_within_budget`).
*   The data-budget guard raises `ValueError` when an override exceeds the allowed fraction of observations (`test_refine_plan_ValueError_when_lags_exceed_data_budget`).
*   `refine_plan`'s `allowed_keys` error message includes `lags`/`window_features` (`test_refine_plan_ValueError_when_invalid_override_key`).
*   `_parse_lags` CLI helper: parses single ints and comma lists, rejects non-numeric input and non-positive lags (`TestParseLags`).
*   Full suite (`pytest -q`) passes end-to-end, including execution/backtesting tests that exercise `forecaster_kwargs` built from these overrides.

Not yet covered: a mocked end-to-end test for `refine_plan_with_llm()` itself (agent call + `PlanOverrides` → `refine_plan`), and a CLI integration test for `refine-plan --prompt`. Both require mocking the LLM call and are good follow-up additions.

## Migration & Rollback
*   **Safe Additive Change:** The deterministic heuristics remain the default. Existing calls to `plan()` without overrides behave exactly as before.
*   **Resilience:** If the LLM generation fails, the user has no LLM configured, or an override violates the data budget, the assistant raises a clear `ValueError`/`LLMRequiredError` (deterministic path) or falls back to the original plan with a `UserWarning` (LLM path) — core profiling/planning is never broken.