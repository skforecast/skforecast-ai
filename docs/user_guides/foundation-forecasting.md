# Foundation models (zero-shot forecasting)

Foundation models are large time series models **pre-trained on large collections of time series**. They forecast a new series *without being trained on it*, or "zero-shot". There is no `fit` in the usual sense: the model stores your recent history as context and predicts from its pre-trained weights.

skforecast-ai treats a foundation model as just another forecaster you can select. The engine stays deterministic: it renders the same `skforecast` foundation code every time, and the optional LLM still only explains.

## When to use one

A foundation model is the right tool when:

- You need a **strong baseline fast**, before investing in feature engineering or tuning.
- You have a **very short history** where regression-based models struggle.
- You're forecasting a **cold-start** series (a new product, a newly instrumented sensor) with little or no history of its own.
- You want to **benchmark** your tuned model against a pre-trained generalist.

For long, stable histories where accuracy is paramount, a tuned gradient-boosting model (the default for larger datasets) often still wins. Use [backtesting](backtesting.md) to compare.

## Install a backend

Foundation backends are **not** bundled, so install only the one you need. The default model is Amazon's **Chronos-2**:

```bash
pip install chronos-forecasting        # Chronos-2 (default)
```

The weights download from HuggingFace on first use, so the first call is slower. Prefer a `*-small` variant while experimenting.

## Use it through the assistant

`ForecasterFoundation` is one of the candidates the assistant considers for a single series. Select it explicitly and the engine generates a Chronos-2 pipeline:

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant()

result = assistant.forecast(
             data        = data,
             target      = "y",
             date_column = "date",
             steps       = 24,
             forecaster  = "ForecasterFoundation",   # zero-shot Chronos-2
         )

print(result.predictions)
print(result.code)        # the exact skforecast foundation script that ran
```

You can confirm it's an option before committing:

```python
profile = assistant.profile(data, target="y", date_column="date")
print(profile.forecaster_candidates)   # includes 'ForecasterFoundation'
```

When the foundation forecaster is selected, the estimator is reported as **Chronos-2**, and lag/feature selection is skipped: a foundation model derives its own representation from the raw context, so the usual PACF-based lags and window features don't apply.

## Prediction intervals come for free

Foundation models output **native quantile forecasts**, so no bootstrapping or conformal calibration is needed. Request an interval the same way as any other forecaster:

```python
result = assistant.forecast(
             data        = data,
             target      = "y",
             date_column = "date",
             steps       = 24,
             forecaster  = "ForecasterFoundation",   # zero-shot Chronos-2
             interval    = [0.1, 0.9],               # 80% interval, taken from the model's quantiles
         )

print(result.predictions.head())
```

## Backtesting

Backtesting works as usual; the generated code uses skforecast's dedicated `backtesting_foundation` runner under the hood. One thing to know: **refit is always disabled** for foundation forecasters: the pre-trained weights are fixed, so each fold reuses the same model and only the context window slides forward. That also makes foundation backtests fast.

```python
profile = assistant.profile(data, target="y", date_column="date")
plan    = assistant.plan(profile, steps=24, forecaster="ForecasterFoundation")
cv, _   = assistant.create_cv(profile, plan)

backtest_results = assistant.backtest(
                       data        = data,
                       target      = "y",
                       date_column = "date",
                       cv          = cv,
                       profile     = profile,
                       plan        = plan
                   )

print(backtest_results.metrics)
```

## Choosing among foundation models

Chronos-2 is the default and the most broadly capable (it accepts exogenous variables and can share information across series). Other backends are available through the underlying `skforecast.foundation` API if you copy and adapt the generated code.

The full per-backend reference (context lengths, supported quantiles, exogenous handling, `cross_learning`) lives in the `foundation-forecasting` skill under `skforecast_ai/skills/`. For the backend-level skforecast API, see the [foundation models user guide](https://skforecast.org/latest/user_guides/foundation-forecasting-models). The [AI assistant](using-the-ai-assistant.md) can walk you through it in plain language.

## Common pitfalls

- **Index needs a frequency.** Set one (`data.asfreq("h")`, `"D"`, `"MS"`, …) before forecasting. See [Troubleshooting](troubleshooting.md).
- **First call is slow.** The model downloads on first use; subsequent calls are fast.

## Next steps

- **[Backtesting & validation](backtesting.md)**: compare the zero-shot baseline against a tuned model.
- **[Customizing the model](customizing-the-model.md)**: switch forecasters and estimators.
- **[Reproducible code](reproducible-code.md)**: export the foundation pipeline as a standalone script.
