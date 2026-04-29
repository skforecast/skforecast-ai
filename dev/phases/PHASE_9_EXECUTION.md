# Phase 9 — Execution & Validation (Post-MVP)

## Goal

Add the ability to actually execute the generated forecasting code and return
results (forecasts, metrics, plots) instead of just code strings.

## Files to Create

```
skforecast_ai/execution/__init__.py    (already exists, add re-exports)
skforecast_ai/execution/runner.py      (safe code execution)
skforecast_ai/execution/validation.py  (output validation)
tests/test_execution.py
```

## Public API Addition

```python
# New method on ForecastingAssistant
result = assistant.run(data=df, target="sales", date_column="date", horizon=30)
# Returns: RunResult

class RunResult(BaseModel):
    profile: DataProfile
    plan: ForecastPlan
    code: str
    metric_value: float
    metric_name: str
    predictions: ...          # DataFrame-compatible
    intervals: ... | None
    warnings: list[str]
```

## Execution Strategy

Do NOT use `exec()` on generated code. Instead:

1. `generate_code()` produces the script for the user.
2. `runner.py` implements the same workflow programmatically by calling
   skforecast functions directly with parameters from `ForecastPlan`.
3. This avoids code injection risks and makes the execution path testable.

## Tests (tests/test_execution.py)

| Test | What it validates |
|------|-------------------|
| `test_run_recursive_single_series` | Runs ForecasterRecursive end-to-end on sample data |
| `test_run_returns_predictions` | Result contains predictions with correct length |
| `test_run_returns_metric` | Result contains metric name and value |
| `test_run_with_backtest` | Backtesting runs and returns metrics |
| `test_run_with_intervals` | Prediction intervals included when requested |
| `test_run_short_series_warning` | Warns about unreliable validation on short data |

## Done Criteria

- [ ] `assistant.run()` works end-to-end on a sample dataset
- [ ] Returns actual forecasts as DataFrames
- [ ] Backtesting metrics are computed and returned
- [ ] No use of `exec()` — all execution is programmatic
- [ ] `pytest tests/test_execution.py` passes (≥ 6 tests)
