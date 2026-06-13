# Troubleshooting

Most problems fall into one of three buckets: the generated code failed at runtime, your data isn't in a shape `skforecast` can use, or an LLM-only feature was called without a model configured. This guide walks through each, with the fix.

When a forecast simply looks *wrong* rather than erroring, start one level up: a quick read of the profile usually reveals the cause. See [Understanding your data](understanding-your-data.md).

## When the generated code fails: `ForecastExecutionError`

Because the assistant runs real, generated code, a runtime failure surfaces as a `ForecastExecutionError`. It carries everything you need to debug it:

```python
from skforecast_ai import ForecastingAssistant, ForecastExecutionError

try:
    result = ForecastingAssistant().forecast(data, target="y", steps=12, date_column="date")
except ForecastExecutionError as err:
    print(err.original_error)        # the underlying exception
    print(err.generated_code)        # the exact script that failed
    print(err.execution_traceback)   # the full traceback from execution
```

| Attribute | What it holds |
| --- | --- |
| `err.original_error` | The underlying exception object raised inside the script. |
| `err.generated_code` | The exact script that was executed. |
| `err.execution_traceback` | The full formatted traceback. |

!!! tip "Read the traceback against the code"
    The traceback line numbers refer to `err.generated_code`. Print both side by side to land directly on the failing line, then either fix the underlying data issue below, or adjust the plan (see [Customizing the model](customizing-the-model.md)).

!!! tip "Ask the assistant to diagnose an error (optional LLM)"
    If the traceback isn't immediately clear, embed the error text in a prompt
    and pass it to `ask()`. There is no `error=` parameter; include the
    description in the prompt string:

    ```python
    assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")

    try:
        result = assistant.forecast(data, target="y", steps=12, date_column="date")
    except ForecastExecutionError as err:
        answer = assistant.ask(
            f"My forecast failed with this error:\n\n{err.original_error}\n\n"
            f"Traceback:\n{err.execution_traceback}\n\n"
            "What is likely wrong and how should I fix it?",
        )
        print(answer.explanation)
    ```

    For data-related failures, also include relevant profile fields
    (frequency, gaps, missing values) in the prompt for better context.

## Common data issues

These are the failures you'll hit most often. The root cause is almost always visible in the profile first: check it before changing anything else.

### `index must be a DatetimeIndex with frequency`

The series has no usable frequency. Check `profile.data_profile.frequency` and `has_gaps`:

```python
dp = assistant.profile(data, target="y", date_column="date").data_profile
print(dp.frequency, dp.has_gaps, dp.has_duplicate_timestamps)
```

If the frequency is `None`, set it explicitly before forecasting:

```python
data = data.asfreq("MS")   # month start; use 'D', 'h', 'QS', … to match your data
```

Irregular or duplicated timestamps need cleaning first: deduplicate, then reindex onto a regular grid. See [Understanding your data](understanding-your-data.md).

### `y contains NaN values`

Missing values in the target. You have three options:

- **Keep them** and use a NaN-tolerant estimator (e.g. `LGBMRegressor` handles `NaN` natively).
- **Drop** the affected rows before fitting.
- **Impute** them: `data.ffill()` or `data.interpolate(method="linear")`.

### `exog does not cover the forecast horizon`

Exogenous predictors must include rows for **every future step** you forecast. If you predict 12 steps ahead, the future exogenous frame needs 12 rows with matching timestamps. Pass them via `exog_future` on `forecast()`.

## Not enough data for backtesting

Backtesting needs enough history for the initial training window **plus** at least one test fold. On short series, `backtest()` can fail with a fold-sizing error. To fix it, give the splitter more room:

- Lower `initial_train_size` in [`create_cv()`](backtesting.md#configuring-the-cross-validation).
- Reduce `steps` so each fold is smaller.
- Set `allow_incomplete_fold=True` to permit a final shorter fold.

## `LLMRequiredError`

Raised when an LLM-only feature is used without a model configured. Two methods require one:

- `ask(...)`: the natural-language Q&A interface.
- `create_cv(prompt=...)`: describing a backtesting scenario in words.

The fix is either to configure a provider (see [Using the AI assistant](using-the-ai-assistant.md)) or to use the deterministic path (the explicit `create_cv()` keyword arguments cover everything `prompt` does).

## If you've edited the generated script

The assistant emits correct, current `skforecast` code. If you adapt the script by hand and hit an error, these are the most common pitfalls: they reflect API changes that older examples and pre-trained models often get wrong.

**Deprecated imports and renamed classes** (skforecast `0.14.0`+):

| Old (deprecated) | Current |
| --- | --- |
| `ForecasterAutoreg` | `ForecasterRecursive` (`from skforecast.recursive`) |
| `ForecasterAutoregMultiSeries` | `ForecasterRecursiveMultiSeries` (`from skforecast.recursive`) |
| `ForecasterAutoregDirect` | `ForecasterDirect` (`from skforecast.direct`) |
| `ForecasterAutoregMultiVariate` | `ForecasterDirectMultiVariate` (`from skforecast.direct`) |
| `regressor=...` | `estimator=...` (all forecasters, `0.22.0`+) |

**Use the right backtesting/search function for the forecaster.** A `ForecasterStats` model needs `backtesting_stats`, and multi-series models need the `_multiseries` variants:

| Task | Single series | Multi-series | Statistical |
| --- | --- | --- | --- |
| Backtesting | `backtesting_forecaster` | `backtesting_forecaster_multiseries` | `backtesting_stats` |
| Grid search | `grid_search_forecaster` | `grid_search_forecaster_multiseries` | `grid_search_stats` |

**Prediction-interval methods are forecaster-specific.** The regression-based forecasters support `'bootstrapping'` and `'conformal'`; statistical and foundation models produce intervals natively. If you call `predict_interval(method="bootstrapping")`, the forecaster must have been fitted with `store_in_sample_residuals=True`.

!!! note "The full reference"
    These rules (plus categorical-exog handling, the ETS model API, and loading forecasters pickled by older versions) live in the `troubleshooting-common-errors` skill (`skforecast_ai/skills/`). The same skill grounds the LLM's answers, so [the assistant](using-the-ai-assistant.md) can walk you through any of them in plain language.

## Handling errors gracefully in code

In a script or service you'll often want to recover from these errors rather than crash. Two patterns cover most cases.

**Fall back to deterministic mode when no LLM is available.** `ask()` is the only thing that needs a model, so guard it:

```python
from skforecast_ai import ForecastingAssistant, LLMRequiredError

assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")
result = assistant.forecast(data, target="y", steps=12, date_column="date")

try:
    answer = assistant.ask("Why this model?", forecast_result=result)
    explanation = answer.explanation
except LLMRequiredError:
    explanation = result.plan.explanation   # deterministic, always available
```

**Capture a failed run for debugging instead of crashing the pipeline:**

```python
from skforecast_ai import ForecastExecutionError

try:
    result = assistant.forecast(data, target="y", steps=12, date_column="date")
except ForecastExecutionError as err:
    # Log everything needed to reproduce the failure, then re-raise or degrade
    log.error("Forecast failed: %s", err.original_error)
    log.debug("Generated code:\n%s", err.generated_code)
    log.debug("Traceback:\n%s", err.execution_traceback)
    raise
```

Because the error carries the exact generated code and traceback, the failure is fully reproducible from the log alone, no need to re-run to find out what happened.

## Next steps

- **[Understanding your data](understanding-your-data.md)**: diagnose frequency, gap, and NaN issues at the source.
- **[Customizing the model](customizing-the-model.md)**: change the forecaster or estimator when a default doesn't fit.
- **[How it works & trust](how-it-works-and-trust.md)**: why a failure always comes with the exact code that produced it.
- **[Human-in-the-loop forecasting](human-in-the-loop.md)** *(optional)*: after fixing an error, use `ask()` to evaluate whether the result looks healthy.
