# LLM-Guided Plan Refinement for Time Series Features

## Background & Motivation
Currently, `ForecastingAssistant` computes `lags` and `window_features` deterministically via `compute_series_pacf` and frequency analysis. Users cannot manually override these specific features in the `plan()` or `refine_plan()` methods, nor is there a structured way to leverage domain knowledge (e.g., "This is retail sales data with strong weekly and annual seasonality") via the LLM to guide these configurations. 

This feature will allow users to provide natural language context about their time series to generate an optimized, LLM-guided configuration for `lags` and `window_features`.

## Scope & Impact
*   `skforecast_ai/schemas/plans.py`: Add `PlanOverrides` schema.
*   `skforecast_ai/llm/prompts.py`: Add `_PLAN_REFINEMENT_ROLE_PROMPT`.
*   `skforecast_ai/llm/agent.py`: Create `PlanRefinementDeps` and `create_plan_refinement_agent`.
*   `skforecast_ai/assistant.py`: Update `plan()`, `refine_plan()`, `forecast()`, `forecast_code()` to accept manual overrides. Add `refine_plan_with_llm()`.
*   `skforecast_ai/cli.py`: Update CLI commands to expose the new manual options and the LLM prompt trigger.

## Proposed Solution: Structured Agentic Approach
We will implement a **Structured Agentic Approach** to ensure the LLM's recommendations are perfectly formatted and rigorously validated before touching the deterministic plan.
1. **API Expansion:** Allow explicit overrides for `lags` and `window_features` in the deterministic `plan()` and `refine_plan()` methods.
2. **Structured Agent:** Build a new Pydantic-AI agent (`create_plan_refinement_agent`) constrained to output a `PlanOverrides` schema. It will have access to the `feature-engineering` and `autocorrelation-and-lag-selection` skills.
3. **Integration:** Expose a `refine_plan_with_llm()` method in `ForecastingAssistant` that accepts a domain knowledge prompt, calls the agent, and feeds the resulting structured overrides back into `refine_plan()`.

## Phased Implementation Plan

### Phase 1: Schemas & Prompts
1. **Schema Definition:** In `skforecast_ai/schemas/plans.py`, define a new `PlanOverrides` Pydantic model:
   *   `lags`: `list[int] | int | None`
   *   `window_features`: `list[dict] | None`
   *   `reasoning`: `str` (explanation of why the LLM chose these features based on the user's prompt).
2. **Role Prompt:** In `skforecast_ai/llm/prompts.py`, add `_PLAN_REFINEMENT_ROLE_PROMPT`. Instruct the agent to act as an expert time series feature engineer, analyzing the user's domain knowledge alongside the `DataProfile` and current `ForecastPlan` to output optimized lags and window features.

### Phase 2: Agent Configuration
1. **Dependencies:** In `skforecast_ai/llm/agent.py`, define a `PlanRefinementDeps` dataclass containing the `DataProfile`, `ForecastPlan`, and the user's prompt.
2. **Agent Creation:** Create a `create_plan_refinement_agent(model)` function returning an `Agent[PlanRefinementDeps, PlanOverrides]`.
3. **Dynamic Skills:** Use the `@agent.instructions` decorator to dynamically inject dataset context and load the `feature-engineering` and `autocorrelation-and-lag-selection` skills so the LLM respects maximum data fraction rules and skforecast conventions.

### Phase 3: Core Assistant Updates
1. **`plan()` Method:**
   *   Update the signature to accept `lags: int | list[int] | None = None` and `window_features: list[dict] | None = None`.
   *   Bypass `finalize_lags` if `lags` is explicitly provided.
   *   Bypass `select_window_features` if `window_features` is explicitly provided.
2. **`refine_plan()` Method:**
   *   Add `"lags"` and `"window_features"` to the `allowed_keys` set.
   *   Extract and pass these overrides to the internal `self.plan()` call.
3. **`refine_plan_with_llm()` Method:**
   *   Add this new method to `ForecastingAssistant`.
   *   Signature: `def refine_plan_with_llm(self, profile, plan, prompt) -> tuple[ForecastPlan, str]`
   *   Logic: Validate LLM presence, call `create_plan_refinement_agent` synchronously, extract `lags` and `window_features` from the output schema, call `self.refine_plan()`, and return the updated plan alongside the LLM's `reasoning`.

### Phase 4: CLI & Wrapper Method Updates
1. **Pass-through Arguments:** Update `forecast()`, `forecast_code()`, `backtest()`, and `backtest_code()` in `assistant.py` to accept and forward the new `lags` and `window_features` arguments.
2. **CLI Commands:** In `skforecast_ai/cli.py`:
   *   Add `--lags` and `--window-features` (parsing JSON strings via a helper) to the `plan`, `refine-plan`, `forecast`, `forecast-code`, `backtest`, and `backtest-code` Typer commands.
   *   In the `refine-plan` command, add an optional `--prompt` argument. If provided, display a spinner ("Refining plan with AI..."), call `assistant.refine_plan_with_llm()`, and display the reasoning text alongside the rendered plan.

## Verification & Testing
*   **Unit Tests:**
    *   Verify `plan()` handles `lags` and `window_features` overrides properly.
    *   Verify `refine_plan()` accepts and applies these new keys.
    *   Create a mock test for `refine_plan_with_llm()` ensuring it calls the agent and processes the `PlanOverrides` correctly.
*   **Integration Tests:**
    *   Test the `refine-plan` CLI command with a `--prompt` argument to verify end-to-end execution.

## Migration & Rollback
*   **Safe Additive Change:** The deterministic heuristics remain the default. Existing calls to `plan()` without overrides will behave exactly as before.
*   **Resilience:** If the LLM generation fails or the user does not configure an LLM, standard `LLMRequiredError` or validation errors will safely abort the refinement process without breaking core profiling/planning.