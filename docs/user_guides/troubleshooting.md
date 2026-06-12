---
title: Troubleshooting
status: draft
---

# Troubleshooting

!!! note "Draft — outline"
    This guide will collect the common errors and their fixes. Outline below; seed content lives in the `troubleshooting-common-errors` skill.

## When the generated code fails: `ForecastExecutionError`

Because the assistant runs real generated code, a runtime failure surfaces as a `ForecastExecutionError` that carries everything you need to debug it:

```python
from skforecast_ai import ForecastingAssistant, ForecastExecutionError

try:
    result = ForecastingAssistant().forecast(data, target="y", steps=12, date_column="date")
except ForecastExecutionError as err:
    print(err.generated_code)        # the exact script that failed
    print(err.execution_traceback)   # the full traceback from execution
    print(err.original_error)        # the underlying exception
```

Read the traceback against the printed code to find the failing line.

## Common data issues

- **"index must be a DatetimeIndex with frequency"** — the series has no usable frequency. Check `profile.data_profile.frequency` and `has_gaps` first (see [Understanding your data](understanding-your-data.md)).
- **"y contains NaN values"** — missing values in the target; impute, drop, or use a NaN-tolerant estimator.
- **"exog does not cover the forecast horizon"** — exogenous data must include rows for every future step (`exog_future`).

## `LLMRequiredError`

- Raised when an LLM-only feature (`ask()`, or `create_cv(prompt=...)`) is called with no model configured.
- Fix: configure a provider — see [Using the AI assistant](using-the-ai-assistant.md) — or use the deterministic path.

---

<!-- To expand later: deprecated imports, wrong backtesting/search function per forecaster, interval-method support, ETS API.
  Seed: skforecast_ai/skills/troubleshooting-common-errors/SKILL.md; skforecast_ai/exceptions.py.
  API to cover: ForecastExecutionError(.original_error/.generated_code/.execution_traceback), LLMRequiredError. -->
