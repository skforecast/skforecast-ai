# Test Structure Analysis

> Generated: 2026-06-01  
> Compared: `tests/` vs `skforecast_ai/` source layout

---

## Executive Summary

The test suite covers **~70%** of source modules with well-structured subdirectories that mirror the source layout. Key findings:

- **6 source modules** have no dedicated test file (varying priority)
- **1 duplicate test file** exists (`test_assistant_forecast_code.py` ≈ `test_assistant_render_code.py`)
- Fixture pattern and naming conventions are followed consistently
- No `conftest.py` files exist (correct per project conventions)
- All test subdirectories have `__init__.py` (correct)

---

## Current Structure

### Tests Directory

```
tests/
├── __init__.py
├── fixtures_assistant.py
├── test_assistant_ask.py
├── test_assistant_backtest.py
├── test_assistant_create_cv.py
├── test_assistant_forecast.py
├── test_assistant_forecast_code.py     ← DUPLICATE of test_assistant_render_code.py
├── test_assistant_init.py
├── test_assistant_plan.py
├── test_assistant_profile.py
├── test_assistant_refine_plan.py
├── test_assistant_render_code.py       ← DUPLICATE of test_assistant_forecast_code.py
├── test_cli.py
├── test_cli_config.py
├── test_cli_pipe.py
├── test_integration_backtest.py
├── test_schemas.py
├── test_utils.py
├── tests_execution/
│   ├── __init__.py
│   ├── fixtures_execution.py
│   └── test_run_forecast.py
├── tests_llm/
│   ├── __init__.py
│   ├── test_build_context_message.py
│   ├── test_llm_agent.py
│   ├── test_provider.py
│   └── test_select_skills.py
├── tests_profiling/
│   ├── __init__.py
│   ├── fixtures_profiling.py
│   ├── test_create_data_profile.py
│   ├── test_forecasting_analysis.py
│   └── test_infer_frequency.py
├── tests_recommendation/
│   ├── __init__.py
│   ├── fixtures_recommendation.py
│   ├── test_compatibility.py
│   ├── test_rules.py
│   ├── test_select_autoregressive.py
│   ├── test_select_lags_and_window_features.py
│   └── test_select_metric.py
└── tests_rendering/
    ├── __init__.py
    ├── fixtures_rendering.py
    ├── test_emit_imports.py
    ├── test_helpers.py
    ├── test_render_backtesting.py
    ├── test_render_forecast_foundation.py
    ├── test_render_forecast_multi_series.py
    ├── test_render_forecast_single_series.py
    └── test_render_forecast_statistical.py
```

### Source Directory

```
skforecast_ai/
├── __init__.py
├── _constants.py
├── _utils.py
├── assistant.py
├── cli.py
├── config.py
├── exceptions.py
├── execution/
│   ├── __init__.py
│   ├── backtesting_runner.py
│   └── forecast_runner.py
├── llm/
│   ├── __init__.py
│   ├── agent.py
│   ├── context.py
│   ├── prompts.py
│   ├── provider.py
│   └── skills.py
├── profiling/
│   ├── __init__.py
│   ├── data_profile.py
│   └── forecasting_analysis.py
├── recommendation/
│   ├── __init__.py
│   ├── autoregressive.py
│   ├── backtesting.py
│   ├── explanation.py
│   ├── forecaster_selection.py
│   ├── metric_selection.py
│   └── preprocessing.py
├── rendering/
│   ├── __init__.py
│   ├── _helpers.py
│   ├── backtesting.py
│   ├── foundation.py
│   ├── multi_series.py
│   ├── single_series.py
│   └── statistical.py
├── schemas/
│   ├── __init__.py
│   ├── plans.py
│   ├── profiles.py
│   └── results.py
└── skills/
    └── [14 skill subdirectories with SKILL.md files]
```

---

## Source-to-Test Mapping

| Source Module | Test File(s) | Status |
|:---|:---|:---:|
| `assistant.py` | `test_assistant_*.py` (9 files) | ✅ Full |
| `cli.py` | `test_cli.py`, `test_cli_config.py`, `test_cli_pipe.py` | ✅ Full |
| `_utils.py` | `test_utils.py` | ✅ Full |
| `config.py` | `test_cli_config.py` (indirect) | ⚠️ Indirect |
| `_constants.py` | — | ⬜ N/A (no logic) |
| `exceptions.py` | — | ⚠️ Missing |
| `schemas/` | `test_schemas.py` | ✅ Full |
| **execution/** | | |
| `forecast_runner.py` | `tests_execution/test_run_forecast.py` | ✅ Full |
| `backtesting_runner.py` | — | ❌ Missing |
| **llm/** | | |
| `agent.py` | `tests_llm/test_llm_agent.py` | ✅ Full |
| `context.py` | `tests_llm/test_build_context_message.py` | ✅ Full |
| `provider.py` | `tests_llm/test_provider.py` | ✅ Full |
| `skills.py` | `tests_llm/test_select_skills.py` | ✅ Full |
| `prompts.py` | — | ⬜ N/A (constants only) |
| **profiling/** | | |
| `data_profile.py` | `tests_profiling/test_create_data_profile.py`, `test_infer_frequency.py` | ✅ Full |
| `forecasting_analysis.py` | `tests_profiling/test_forecasting_analysis.py` | ✅ Full |
| **recommendation/** | | |
| `autoregressive.py` | `tests_recommendation/test_select_autoregressive.py`, `test_select_lags_and_window_features.py` | ✅ Full |
| `metric_selection.py` | `tests_recommendation/test_select_metric.py` | ✅ Full |
| `preprocessing.py` | `tests_recommendation/test_compatibility.py` | ✅ Full |
| `forecaster_selection.py` | `tests_recommendation/test_rules.py` (partial) | ⚠️ Partial |
| `backtesting.py` | — | ❌ Missing |
| `explanation.py` | — | ❌ Missing |
| **rendering/** | | |
| `_helpers.py` | `tests_rendering/test_helpers.py`, `test_emit_imports.py` | ✅ Full |
| `backtesting.py` | `tests_rendering/test_render_backtesting.py` | ✅ Full |
| `foundation.py` | `tests_rendering/test_render_forecast_foundation.py` | ✅ Full |
| `multi_series.py` | `tests_rendering/test_render_forecast_multi_series.py` | ✅ Full |
| `single_series.py` | `tests_rendering/test_render_forecast_single_series.py` | ✅ Full |
| `statistical.py` | `tests_rendering/test_render_forecast_statistical.py` | ✅ Full |

---

## Convention Compliance Checklist

| Convention | Status | Notes |
|:---|:---:|:---|
| One test file per public method/unit | ✅ | Assistant methods each have dedicated files |
| `__init__.py` in every test directory | ✅ | Present in all subdirectories |
| File header comment | ✅ | All files have `# Unit test ...` headers |
| No `conftest.py` | ✅ | None found |
| Fixtures in separate `fixtures_*.py` | ✅ | Root + 4 subdirectory fixture files |
| Module-level variables (not `@pytest.fixture`) | ✅ | Fixtures use hardcoded DataFrames/arrays |
| Relative imports for fixtures | ✅ | `from .fixtures_...` or `from tests.fixtures_...` |
| Test naming: `test_<method>_<scenario>` | ✅ | Consistently applied |
| Parametrize for variations | ✅ | Used in recommendation and rendering tests |
| `pd.testing.assert_frame_equal` for DataFrames | ✅ | Used where applicable |
| `re.escape()` with `pytest.raises(match=)` | ✅ | Error tests follow pattern |
| Multi-line docstrings on tests | ⚠️ | Most tests have them; some simpler tests omit |

---

## Coverage Gaps

| Source Module | Priority | Rationale |
|:---|:---:|:---|
| `execution/backtesting_runner.py` | 🔴 High | Core execution path with `run_backtest()`, branching dispatch logic, exec-based execution, error wrapping |
| `recommendation/backtesting.py` | 🔴 High | `derive_cv_defaults()` computes critical CV parameters deterministically — untested logic |
| `recommendation/forecaster_selection.py` | 🟡 Medium | `select_forecaster_and_candidates()` and `select_estimator()` partially tested via `test_rules.py` but lack dedicated unit tests |
| `recommendation/explanation.py` | 🟡 Medium | `build_plan_explanation()` assembles user-facing text — regression-prone string logic |
| `exceptions.py` | 🟢 Low | Custom exception classes with message formatting logic; indirectly tested when other code raises them |
| `config.py` | 🟢 Low | `load_config()`, `save_config()`, `get_config_value()` — tested indirectly via CLI tests, but no unit-level file I/O tests |
| `_constants.py` | ⬜ None | Pure constant definitions (frozen sets) — no executable logic |
| `llm/prompts.py` | ⬜ None | String constants only — no executable logic |

---

## Issues Found

### 1. Duplicate Test File

`test_assistant_forecast_code.py` and `test_assistant_render_code.py` have **identical content** (same header comment is the only difference: "forecast_code" vs "forecast_code"). Both test the `render_code()` method with the same assertions.

**Recommendation:** Remove `test_assistant_forecast_code.py` and keep `test_assistant_render_code.py` as the canonical file (matches the current method name `render_code()`).

### 2. Missing `fixtures_llm.py`

The `tests_llm/` subdirectory has no fixture file. Test data is defined inline in each test. As the test count grows, a shared fixture file would improve maintainability.

**Recommendation:** Create `tests_llm/fixtures_llm.py` when adding new tests to this subdirectory.

---

## Proposed Ideal Structure

```
tests/
├── __init__.py
├── fixtures_assistant.py
├── test_assistant_ask.py
├── test_assistant_backtest.py
├── test_assistant_create_cv.py
├── test_assistant_forecast.py
├── test_assistant_init.py
├── test_assistant_plan.py
├── test_assistant_profile.py
├── test_assistant_refine_plan.py
├── test_assistant_render_code.py            ← keep (remove duplicate)
├── test_cli.py
├── test_cli_config.py
├── test_cli_pipe.py
├── test_config.py                           ← NEW (unit tests for load/save/get)
├── test_exceptions.py                       ← NEW (message formatting, attributes)
├── test_integration_backtest.py
├── test_schemas.py
├── test_utils.py
│
├── tests_execution/
│   ├── __init__.py
│   ├── fixtures_execution.py
│   ├── test_run_backtest.py                 ← NEW (dispatch, exec, error wrapping)
│   └── test_run_forecast.py
│
├── tests_llm/
│   ├── __init__.py
│   ├── fixtures_llm.py                      ← NEW (shared LLM test data)
│   ├── test_build_context_message.py
│   ├── test_llm_agent.py
│   ├── test_provider.py
│   └── test_select_skills.py
│
├── tests_profiling/
│   ├── __init__.py
│   ├── fixtures_profiling.py
│   ├── test_create_data_profile.py
│   ├── test_forecasting_analysis.py
│   └── test_infer_frequency.py
│
├── tests_recommendation/
│   ├── __init__.py
│   ├── fixtures_recommendation.py
│   ├── test_compatibility.py
│   ├── test_derive_cv_defaults.py           ← NEW (CV parameter computation)
│   ├── test_explanation.py                  ← NEW (plan explanation assembly)
│   ├── test_forecaster_selection.py         ← NEW (dedicated unit tests)
│   ├── test_rules.py                        ← existing (integration-level rules)
│   ├── test_select_autoregressive.py
│   ├── test_select_lags_and_window_features.py
│   └── test_select_metric.py
│
└── tests_rendering/
    ├── __init__.py
    ├── fixtures_rendering.py
    ├── test_emit_imports.py
    ├── test_helpers.py
    ├── test_render_backtesting.py
    ├── test_render_forecast_foundation.py
    ├── test_render_forecast_multi_series.py
    ├── test_render_forecast_single_series.py
    └── test_render_forecast_statistical.py
```

---

## Recommendations

### Immediate Actions

1. **Delete** `test_assistant_forecast_code.py` (duplicate of `test_assistant_render_code.py`)
2. **Create** `tests_execution/test_run_backtest.py` — test the dispatch logic, successful execution, and `ForecastExecutionError` wrapping
3. **Create** `tests_recommendation/test_derive_cv_defaults.py` — test `derive_cv_defaults()` with various profile/plan combinations

### Short-Term

4. **Create** `tests_recommendation/test_forecaster_selection.py` — dedicated unit tests for `select_forecaster_and_candidates()` and `select_estimator()` (extract from `test_rules.py` or complement it)
5. **Create** `tests_recommendation/test_explanation.py` — test `build_plan_explanation()` output strings
6. **Create** `tests_llm/fixtures_llm.py` — consolidate inline test data

### Low Priority

7. **Create** `test_config.py` — unit tests for `load_config()`, `save_config()` (file I/O with `tmp_path`)
8. **Create** `test_exceptions.py` — verify message formatting and attribute storage
9. No tests needed for `_constants.py` or `llm/prompts.py` (no executable logic)

---

## Summary Statistics

| Metric | Value |
|:---|:---|
| Total source modules (with logic) | 22 |
| Modules with full test coverage | 16 (73%) |
| Modules with partial coverage | 2 (9%) |
| Modules with no coverage | 4 (18%) |
| Total test files | 30 |
| Duplicate test files | 1 |
| Test subdirectories | 5 |
| Fixture files | 5 |
| Convention violations | 0 major, 1 minor (missing docstrings on some tests) |
