# Backtesting & validation

A single train/test split tells you how a model did on *one* slice of the future. **Backtesting** (walk-forward validation) tells you how it does *repeatedly*, across many points in time, which is the honest way to estimate how a forecast will perform in production.

skforecast-ai backtests with the same profile and plan it uses for forecasting, so you're evaluating the exact model you'd deploy.

## The backtesting workflow

```mermaid
flowchart LR
    A[profile] --> B[plan]
    B --> C["create_cv() → TimeSeriesFold + explanation"]
    C --> D["backtest() → BacktestResult"]
```

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant()

# 1. Profile and plan as usual
profile = assistant.profile(data, target="y", date_column="date")
plan    = assistant.plan(profile, steps=12)

# 2. Build a cross-validation strategy (with sensible defaults)
cv, cv_explanation = assistant.create_cv(profile, plan)
print(cv_explanation)

# 3. Run the walk-forward evaluation
result = assistant.backtest(
             data        = data,
             target      = "y",
             date_column = "date",
             cv          = cv,
             profile     = profile,
             plan        = plan,
         )
```

## Defining the cross-validation folds

`backtest()` needs a `cv`: a skforecast `TimeSeriesFold` that describes how the series is split into successive train/test folds. There are three ways to build one.

### Smart defaults with `create_cv()`

`create_cv()` returns a configured `TimeSeriesFold` (skforecast's fold splitter) plus a plain-language `explanation` of the choices. With no overrides it derives defaults from your data; override any of these to match how you actually deploy:

| Parameter | Meaning |
| --- | --- |
| `initial_train_size` | Observations for the first training set. An `int` (count), a `float` in (0, 1) (fraction), or a date string. |
| `refit` | Refit every fold (`True`), never (`False`), or every *n* folds (`int`). |
| `fixed_train_size` | `True` = rolling window (old data dropped); `False` = expanding window (all history kept). |
| `gap` | Observations between the end of training and the start of the test set (models a real-world delay). |
| `fold_stride` | Distance between consecutive test sets. `None` means equal to `steps` (non-overlapping folds). |
| `skip_folds` | Skip folds to save compute (`int` keeps every *n*-th; a list gives indexes to skip). |
| `allow_incomplete_fold` | Whether a final, shorter-than-`steps` fold is allowed. |

```python
# Example: simulate "retrain weekly, with a 1-day data delay, keep all history"
cv, explanation = assistant.create_cv(
                      profile          = profile,
                      plan             = plan,
                      refit            = 7,
                      gap              = 1,
                      fixed_train_size = False,
                  )
```

!!! tip "Match the configuration to your deployment"
    The most useful backtest reproduces your real operating conditions. Retrain monthly? Set `refit` accordingly. Forecasts needed two days ahead of data availability? Set `gap=2`. The closer the configuration matches production, the more trustworthy the metrics.

### Bring your own `TimeSeriesFold`

If you already know how to configure skforecast's [`TimeSeriesFold`](https://skforecast.org/latest/user_guides/backtesting), build one yourself and pass it straight to `backtest()` (or `backtest_code()`), skipping `create_cv()` entirely:

```python
from skforecast.model_selection import TimeSeriesFold

cv = TimeSeriesFold(
         steps              = 12,
         initial_train_size = 120,
         refit              = False,
     )

result = assistant.backtest(
             data        = data,
             target      = "y",
             date_column = "date",
             cv          = cv,
         )
```

`create_cv()` is a convenience wrapper that picks sensible `TimeSeriesFold` defaults for you; when you already know the exact split you want, constructing it directly is equivalent. See skforecast's [backtesting user guide](https://skforecast.org/latest/user_guides/backtesting) for every available option.

### Describe it in words *(requires an LLM)*

If you have [an LLM configured](using-the-ai-assistant.md), describe your evaluation scenario in plain language and let `create_cv()` translate it into fold parameters via the `prompt` argument:

```python
assistant = ForecastingAssistant(llm="openai:gpt-4o-mini", api_key="YOUR_API_KEY")
cv, explanation = assistant.create_cv(
                      profile = profile,
                      plan    = plan,
                      prompt  = "I retrain every Monday and need forecasts for the next 7 days.",
                  )
```

Without an LLM, `prompt` raises `LLMRequiredError`; the deterministic defaults and explicit keyword arguments above cover everything you need in the default mode.

## Reading the result

`backtest()` returns a `BacktestResult`:

| Attribute | What it holds |
| --- | --- |
| `result.metrics` | Backtest metrics across all folds (DataFrame). |
| `result.predictions` | The full set of out-of-sample predictions over every fold. |
| `result.cv_config` | The resolved `TimeSeriesFold` parameters that were used (kept for traceability). |
| `result.code` | The standalone Python script reproducing the entire backtest. |
| `result.explanation` | Human-readable summary of the configuration and results. |
| `result.profile` / `result.plan` | The profile and plan that were evaluated. |

```python
print(result.metrics)
print(result.cv_config)     # exactly which folds were run
print(result.explanation)
```

## Python script 

To get the backtesting script **without** executing it, to audit it or run it elsewhere: use `backtest_code()` instead of `backtest()`. It takes the same arguments and returns a `CodeGenerationResult` whose `.code` is the standalone script. See [Reproducible code](reproducible-code.md).

```python
generated = assistant.backtest_code(
                data        = data,
                target      = "y",
                date_column = "date",
                cv          = cv,
                profile     = profile,
                plan        = plan
            )
print(generated.code)
```

## Next steps

- **[Customizing the model](customizing-the-model.md)**: backtest different models and compare their metrics.
- **[Reproducible code](reproducible-code.md)**: export and deploy the validated pipeline.
- **[Troubleshooting](troubleshooting.md)**: if a backtest raises an error (e.g. not enough data for two folds).
