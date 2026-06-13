# Forecasting multiple series

When you have more than one related series (stores, SKUs, sensors, regions), you have a choice to make about *how* they share information. skforecast-ai detects the multi-series case automatically and defaults to a sensible global model, but understanding the options helps you override well.

## The two strategies

When the profile sees more than one series, the assistant considers two forecasters, in this order:

| Forecaster | Task type | What it does |
| --- | --- | --- |
| **`ForecasterRecursiveMultiSeries`** *(default)* | `multi_series` | One **global** model trained across all series. Each series is predicted on its own history, but they share learned parameters. |
| **`ForecasterDirectMultiVariate`** | `multivariate` | Predicts **one target series** using the lagged values of *all* series as features. |

```python
profile = assistant.profile(data, target=["store_a", "store_b", "store_c"], date_column="date")
print(profile.forecaster_candidates)
# ['ForecasterRecursiveMultiSeries', 'ForecasterDirectMultiVariate']
```

## Which one should you use?

**Reach for the global model (`ForecasterRecursiveMultiSeries`) when:**

- You have **many series that behave similarly** (e.g. sales across stores), they reinforce each other and short/cold-start series borrow strength from the rest.
- You want to forecast **all of them**, not just one.
- The series are related but not necessarily *causally* linked.

This is the default for a reason: it scales to many series, handles different-length histories, and is the strongest general-purpose choice.

**Reach for the multivariate model (`ForecasterDirectMultiVariate`) when:**

- You care about **one specific target** and the other series are **leading indicators** for it (e.g. forecast demand using upstream traffic and price).
- The series are **strongly correlated and influence each other**.

**Consider alternatives when:**

- Series are **completely unrelated**: separate single-series models ([first forecast](first-forecast.md)) may be cleaner than forcing them into one model.
- You have **very short histories** and want a zero-shot baseline: a [foundation model](foundation-forecasting.md) (Chronos-2) forecasts multiple series without training.

## Running it through the assistant

The default works without any override:

```python
result = assistant.forecast(
    data, target=["store_a", "store_b", "store_c"], steps=14, date_column="date",
)
print(result.metrics)   # per-series and aggregated metrics
```

Switch to the multivariate strategy by overriding the forecaster (it must be a candidate):

```python
result = assistant.forecast(
    data, target=["store_a", "store_b", "store_c"], steps=14, date_column="date",
    forecaster="ForecasterDirectMultiVariate",
)
```

## A few things to know

- **Per-series metrics.** Backtesting a global model reports both per-series and aggregated metrics; use them to find which series are hardest to forecast and why ([backtesting](backtesting.md)).
- **Encoding.** The global model encodes the series identity; with categorical-native estimators (LightGBM, CatBoost) this is handled automatically.
- **Long vs wide data.** Pass wide-format (one column per series) or use `series_id_column` for long format. See [Understanding your data](understanding-your-data.md).

The full mechanics (data formats, per-series transformers, reshaping utilities) live in the `forecasting-multiple-series` skill under `skforecast_ai/skills/`, which also grounds the [AI assistant's](using-the-ai-assistant.md) answers on the topic.

## Next steps

- **[Backtesting & validation](backtesting.md)**: evaluate per-series performance.
- **[Going further](going-further.md)**: features and tuning across many series.
- **[Foundation models](foundation-forecasting.md)**: zero-shot multi-series forecasting.
