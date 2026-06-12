---
title: Reproducible code
status: draft
---

# Reproducible code

!!! note "Draft — outline"
    This guide will show how to obtain the standalone `skforecast` script the assistant generates, why it's guaranteed to match the executed forecast, and how to audit and deploy it. Outline below.

The headline guarantee — *the code shown is exactly the code that ran* — is explained in [How it works & trust](how-it-works-and-trust.md). This page is the practical how-to.

## Get the script without running it

- `forecast_code(...)` returns a `CodeGenerationResult` (it does **not** execute anything).
- Read the script from `result.code`; the `result.profile` and `result.plan` show the decisions behind it.
- `backtest_code(...)` does the same for a backtesting workflow.

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant()
generated = assistant.forecast_code(data, target="y", steps=12, date_column="date")
print(generated.code)        # standalone, runnable skforecast script
```

## The fidelity guarantee

- `forecast()` and `forecast_code()` produce the *same* script for the same inputs — one runs it, one hands it over.
- Cross-link to [How it works & trust](how-it-works-and-trust.md) for the `exec()` mechanism and isolation.

## Audit, modify, deploy

- Read the script to confirm the model, lags, and preprocessing before trusting it.
- Save it to a `.py` file and run it with plain `skforecast` — no runtime dependency on skforecast-ai.
- Edit it freely for production (logging, persistence, scheduling).

---

<!-- To expand later:
  - The RenderedScript sections (imports / data_loading / core) and full standalone vs exec-only forms.
  - Saving and versioning generated scripts.
  Seed: forecast_code docstring; architecture-and-logic_detailed.md (rendering stage).
  API to cover: forecast_code(), backtest_code(), CodeGenerationResult(.code/.profile/.plan). -->
