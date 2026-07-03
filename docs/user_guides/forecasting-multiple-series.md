# Forecasting multiple series

When you have more than one related series (stores, SKUs, sensors, regions), the question is *how* they should share information. skforecast-ai detects the multi-series case automatically and defaults to a global model; understanding the options helps you override it deliberately.

## The two strategies

When the profile sees more than one series, the assistant considers two forecasters, in this order:

| Forecaster | Task type | What it does |
| --- | --- | --- |
| **`ForecasterRecursiveMultiSeries`** *(default)* | `multi_series` | One **global** model trained across all series. Each series is predicted on its own history, but they share learned parameters. |
| **`ForecasterDirectMultiVariate`** | `multivariate` | Predicts **one target series** using the lagged values of *all* series as features. |

For the underlying skforecast mechanics, see the [independent multi-series forecasting](https://skforecast.org/latest/user_guides/independent-multi-time-series-forecasting) and [multivariate forecasting](https://skforecast.org/latest/user_guides/dependent-multi-series-multivariate-forecasting) user guides.

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

This is the default: it scales to many series and handles different-length histories.

**Reach for the multivariate model (`ForecasterDirectMultiVariate`) when:**

- You care about **one specific target** and the other series are **leading indicators** for it (e.g. forecast demand using upstream traffic and price).
- The series are **strongly correlated and influence each other**.

**Consider alternatives when:**

- Series are **completely unrelated**: separate single-series models ([first forecast](first-forecast.md)) may be cleaner than forcing them into one model.
- You have **very short histories** and want a zero-shot baseline: a [foundation model](foundation-forecasting.md) (Chronos-2) forecasts multiple series without training.

## Running it through the assistant

The default works without any override. Pass `test_size` to evaluate the global model on a held-out test set (reporting one row of metrics per series); omit it to forecast the future:

```python
result = assistant.forecast(
             data        = data, 
             target      = ["store_a", "store_b", "store_c"], 
             date_column = "date",
             steps       = 14, 
             test_size   = 14,   # evaluate: hold out the last 14 observations
         )
print(result.metrics)   # one row of metrics per series
```

Switch to the multivariate strategy by overriding the forecaster (it must be a candidate):

```python
result = assistant.forecast(
             data        = data, 
             target      = ["store_a", "store_b", "store_c"], 
             date_column = "date",
             steps       = 14, 
             forecaster  = "ForecasterDirectMultiVariate",
         )
```

With the multivariate strategy, only the **first** column in `target` is forecast (the `level`); the remaining columns are used as predictors. To forecast a different series, list it first.

## A few things to know

- **Per-series metrics.** Backtesting a global model reports both per-series and aggregated metrics; use them to find which series are hardest to forecast and why ([backtesting](backtesting.md)).
- **Encoding.** The global model encodes the series identity; with categorical-native estimators (LightGBM, CatBoost) this is handled automatically.
- **Long vs wide data.** Pass wide-format (one column per series) or use `series_id_column` for long format. See [Understanding your data](understanding-your-data.md).

The full mechanics (data formats, per-series transformers, reshaping utilities) live in the `forecasting-multiple-series` skill under `skforecast_ai/skills/`, which also grounds the [AI assistant's](using-the-ai-assistant.md) answers on the topic.

## Next steps

- **[Backtesting & validation](backtesting.md)**: evaluate per-series performance.
- **[Going further](going-further.md)**: features and tuning across many series.
- **[Foundation models](foundation-forecasting.md)**: zero-shot multi-series forecasting.
