# Reproducible code

Every forecast skforecast-ai produces comes with the **exact, standalone `skforecast` script** that generated it. You can read it, audit it, save it, and run it anywhere, with no runtime dependency on skforecast-ai. This page is the practical how-to.

The guarantee behind it (that the code shown is exactly the code that ran) is explained in [How it works & trust](how-it-works-and-trust.md). Here we focus on getting the script and putting it to use.

## Get the script without running it

When you want the code but not the results, use `forecast_code()`. It runs the deterministic profiling and planning stages, renders the script, and hands it back **without executing anything**:

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant()
generated = assistant.forecast_code(data, target="y", steps=12, date_column="date")

print(generated.code)   # the complete, standalone skforecast script
```

`forecast_code()` returns a `CodeGenerationResult`:

| Attribute | What it holds |
| --- | --- |
| `generated.code` | The full standalone `skforecast` script, as a string. |
| `generated.profile` | The `ForecastingProfile` behind the script: what the assistant learned about your data. |
| `generated.plan` | The `ForecastPlan`: the concrete modeling decisions the script encodes. |

For the walk-forward variant, `backtest_code()` does the same for a backtesting workflow and returns the same `CodeGenerationResult` type:

```python
cv, _ = assistant.create_cv(generated.profile, generated.plan)
backtest_script = assistant.backtest_code(
    data, target="y", date_column="date", cv=cv,
    profile=generated.profile, plan=generated.plan,
)
print(backtest_script.code)
```

## The fidelity guarantee

`forecast()` and `forecast_code()` produce the **same script** for the same inputs: one executes it and returns results, the other simply hands it to you. So `forecast_code()` is the natural choice when you want to review the code *before* trusting it.

```python
# These two scripts are identical for the same inputs:
forecast_result = assistant.forecast(data, target="y", steps=12, date_column="date")
code_result     = assistant.forecast_code(data, target="y", steps=12, date_column="date")

assert forecast_result.code == code_result.code   # same code, every time
```

The deterministic engine guarantees this: identical data and configuration always yield byte-for-byte identical code. The `exec()` mechanism and execution isolation that make this hold are described in [How it works & trust](how-it-works-and-trust.md).

## What's inside the script

The generated script is a complete, self-contained program. Internally the renderer assembles it from three logical sections:

| Section | Contents |
| --- | --- |
| **Imports** | Every `skforecast`, scikit-learn, and pandas import the script needs. |
| **Data loading** | Reads your dataset from a CSV path and sets up the datetime index. |
| **Core** | Preprocessing, the train/test split, forecaster creation, `fit`, `predict`, and metrics. |

`generated.code` is the **full** script (imports + data loading + core): runnable on its own. When `forecast()` executes the pipeline, it runs the imports and core against an in-memory copy of your DataFrame and skips the CSV-loading section, which is why the results are produced without any disk I/O.

!!! note "Where the script reads its data"
    The data-loading section reads from a CSV path. If you passed a file path to the assistant, the script points at that file; if you passed a DataFrame in memory, it defaults to `data.csv`. Before running the script standalone, make sure your data is available at that path, or edit the loading line to match.

## Audit, modify, deploy

The script is yours to own. Three common uses:

1. **Audit before you trust.** Read the code to confirm the forecaster, lags, preprocessing, and metrics are what you expect, *before* committing to the result.
2. **Reproduce anywhere.** Save it to a `.py` file and run it with plain `skforecast`. There is no runtime dependency on skforecast-ai.
3. **Adapt for production.** Treat the script as a starting point: add logging, model persistence, scheduling, or a different data source, and ship it.

```python
# Save the generated script for version control or deployment
with open("forecast_pipeline.py", "w", encoding="utf-8") as f:
    f.write(generated.code)
```

!!! tip "Version the script, not just the model"
    Because the script is the literal source of a forecast, checking it into version control gives you a precise, human-readable record of how each forecast was produced: far more transparent than a pickled model object.

## Taking it to production

Because the script depends only on `skforecast` (not on skforecast-ai), it slots into a production stack like any other Python file. A typical path:

1. **Commit the generated script** alongside the data schema it expects. It is your reproducible source of truth.
2. **Persist the fitted forecaster** so serving doesn't refit on every call. `skforecast` integrates with `joblib`/`skforecast.utils.save_forecaster`; add the persistence call to the script's core section.
3. **Schedule retraining** on a cadence that matches how fast your data evolves (daily, weekly, …). Re-run skforecast-ai on fresh data to regenerate the script, or re-`fit` the existing pipeline.
4. **Monitor for drift** between scheduled retrains so you retrain *when the data changes*, not just on a fixed clock. See [Monitoring & drift detection](drift-detection.md).
5. **Track error over time** with rolling [backtests](backtesting.md) to catch silent degradation.

```python
# Inside (or appended to) the exported script: persist the fitted model
from skforecast.utils import save_forecaster
save_forecaster(forecaster, file_name="forecaster.joblib", verbose=False)
```

!!! note "Retraining closes the loop"
    When drift fires or error climbs, re-profile and refine on fresh data ([Human-in-the-loop](human-in-the-loop.md)), regenerate the script, and redeploy. The new script is just as auditable and reproducible as the first.

## Next steps

- **[How it works & trust](how-it-works-and-trust.md)**: why the code shown is guaranteed to be the code that ran.
- **[Customizing the model](customizing-the-model.md)**: change the forecaster or estimator, then export the customized script.
- **[Backtesting & validation](backtesting.md)**: generate and export a full walk-forward evaluation script with `backtest_code()`.
