# Phase 4 — Code Generation

## Goal

Given a `ForecastPlan` and a `DataProfile`, generate a complete, executable
Python script that the user can run as-is with their data.

## Files to Create

```
skforecast_ai/generation/code_templates.py   (template rendering)
tests/test_code_generation.py
```

## Public API

```python
from skforecast_ai.generation import generate_code

code = generate_code(
    plan=forecast_plan,
    profile=data_profile,
    data_path="data.csv",         # path to embed in the script
)
# Returns: str (valid Python code)
```

## Templates to Implement

One template per `task_type` (start with the most common, add others
incrementally):

| Priority | task_type | Forecaster | Template covers |
|----------|-----------|------------|-----------------|
| **P0** | `single_series` | `ForecasterRecursive` | Import, load data, set freq, train/test split, create forecaster, fit, predict, backtest, intervals |
| **P0** | `single_series` | `ForecasterDirect` | Same as above, with `steps` at init |
| **P1** | `multi_series` | `ForecasterRecursiveMultiSeries` | Long/wide format handling, encoding |
| **P1** | `statistical` | `ForecasterStats` | ARIMA/ETS wrapper |
| **P2** | `foundation` | `ForecasterFoundation` | Model adapter, zero-shot |
| **P2** | `multivariate` | `ForecasterDirectMultiVariate` | Multi-series as features |

## Code Generation Strategy

Use Python string templates (f-strings or `textwrap.dedent` blocks) for Phase 4.
Avoid introducing Jinja2 dependency unless templates grow complex enough to
justify it. Each template is a function that takes `plan` + `profile` and
returns a string.

## Tests (tests/test_code_generation.py)

| Test | What it validates |
|------|-------------------|
| `test_recursive_single_series_syntax` | Generated code compiles (`compile(code, "<test>", "exec")`) |
| `test_recursive_includes_backtest` | Code contains `backtesting_forecaster` call |
| `test_recursive_with_exog` | Code includes exog handling when `use_exog=True` |
| `test_direct_includes_steps` | Code passes `steps=` to ForecasterDirect |
| `test_code_uses_correct_metric` | Metric from plan appears in backtest call |
| `test_code_uses_correct_lags` | Lags from plan appear in forecaster init |
| `test_code_respects_interval_method` | Interval code present when `interval_method` set |
| `test_multi_series_template_syntax` | Multi-series code compiles |

## Done Criteria

- [ ] `from skforecast_ai.generation import generate_code` works
- [ ] Generated code for `ForecasterRecursive` compiles and is syntactically valid
- [ ] Generated code includes all key workflow steps (load, split, fit, predict, backtest)
- [ ] Exog and interval variations are correctly handled
- [ ] `pytest tests/test_code_generation.py` passes (≥ 6 tests, P0 templates)
