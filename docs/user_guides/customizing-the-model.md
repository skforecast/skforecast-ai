# Customizing the model

The assistant's defaults are good starting points, not mandates. When you want a different forecaster, a different estimator, tuned hyperparameters, a longer horizon, or prediction intervals, you override the relevant decision and run again.

This guide is about **how to override**. For *why* the assistant chose what it did — the rules behind forecaster and estimator selection — see [How it works & trust](how-it-works-and-trust.md) and [The forecasting workflow](the-forecasting-workflow.md).

## What you can override

There are five override keys, accepted everywhere overrides are allowed:

| Key | Type | What it controls |
| --- | --- | --- |
| `forecaster` | `str` | The skforecast forecaster class (e.g. `"ForecasterRecursive"`, `"ForecasterDirect"`). |
| `estimator` | `str` | The scikit-learn-compatible estimator (e.g. `"LGBMRegressor"`, `"Ridge"`). |
| `estimator_kwargs` | `dict` | Constructor arguments for the estimator (e.g. `{"n_estimators": 200}`). |
| `steps` | `int` | The forecast horizon (number of steps ahead). |
| `interval` | `list[int]` | Prediction interval percentiles `[lower, upper]`, e.g. `[10, 90]`. |

## See your options first

The profile already lists the alternatives the assistant considered, in preference order. Inspect them before overriding:

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant()
profile = assistant.profile(data, target="y", date_column="date")

print(profile.forecaster)             # the chosen forecaster
print(profile.forecaster_candidates)  # ordered alternatives you can switch to
print(profile.estimator)              # the chosen estimator
print(profile.estimator_candidates)   # ordered alternatives
print(profile.explanation)            # why these were picked
```

Switching to a candidate is the safest kind of override — it's a model the assistant already deemed compatible with your data.

## Two ways to override

### Option A — inline, on `forecast()`

The quickest path: pass the overrides straight to `forecast()`. Anything you don't specify keeps its recommended default.

```python
result = assistant.forecast(
    data=data,
    target="y",
    steps=12,
    date_column="date",
    estimator="LGBMRegressor",
    estimator_kwargs={"n_estimators": 200, "learning_rate": 0.05},
)
```

### Option B — explicit, with `refine_plan()`

When you want to inspect or reuse the modified plan, refine it as a separate step. This mirrors the [step-by-step workflow](the-forecasting-workflow.md):

```python
profile = assistant.profile(data, target="y", date_column="date")
plan    = assistant.plan(profile, steps=12)

# Override only what you want; the rest of the plan is preserved.
plan = assistant.refine_plan(
    profile, plan,
    forecaster="ForecasterDirect",
    estimator="Ridge",
    steps=24,
)

print(plan.forecaster, plan.estimator, plan.steps)   # inspect before running

result = assistant.forecast(data, target="y", steps=24, date_column="date",
                            profile=profile, plan=plan)
```

`refine_plan(profile, plan, **overrides)` returns a new `ForecastPlan` with your changes applied and everything else (lags, metric, preprocessing) intact.

## Adding prediction intervals

Use `interval=[lower, upper]` (percentiles) to get uncertainty bounds. `[10, 90]` is an 80% interval; `[5, 95]` is 90%.

```python
result = assistant.forecast(
    data=data,
    target="y",
    steps=12,
    date_column="date",
    interval=[10, 90],
)

print(result.intervals.head())
```

The assistant selects an appropriate interval method automatically based on the forecaster — bootstrapping or conformal for the regression-based forecasters, and native intervals for statistical and foundation models. You don't set the method yourself through this API.

## Tuning hyperparameters

Pass estimator constructor arguments via `estimator_kwargs`. These are merged on top of the assistant's built-in defaults (such as `random_state` and verbosity flags), so you only specify what you want to change:

```python
result = assistant.forecast(
    data=data,
    target="y",
    steps=12,
    date_column="date",
    estimator="LGBMRegressor",
    estimator_kwargs={"n_estimators": 500, "num_leaves": 64, "learning_rate": 0.03},
)
```

## A note on which estimator fits

The assistant's default estimator depends on how much data you have — smaller datasets favor a simpler, regularized model (`Ridge`) to avoid overfitting, while larger ones use gradient boosting (`LGBMRegressor`). If you override `estimator`, choose one suited to your dataset size; you can always compare options with [backtesting](backtesting.md). The full rule is described in [How it works & trust](how-it-works-and-trust.md).

## Next steps

- **[Backtesting & validation](backtesting.md)** — measure whether your override actually improved the forecast.
- **[Reproducible code](reproducible-code.md)** — export the customized model as a standalone script.
- **[Troubleshooting](troubleshooting.md)** — if an override produces an error at execution time.
