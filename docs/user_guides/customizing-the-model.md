# Customizing the model

The assistant's defaults are good starting points, not mandates. When you want a different forecaster, a different estimator, tuned hyperparameters, a longer horizon, or prediction intervals, you override the relevant decision and run again.

This guide is about **how to override**. For *why* the assistant chose what it did (the rules behind forecaster and estimator selection: see [How it works & trust](how-it-works-and-trust.md) and [The forecasting workflow](the-forecasting-workflow.md).

## What you can override

There are five override keys, accepted everywhere overrides are allowed:

| Key | Type | What it controls |
| --- | --- | --- |
| `forecaster` | `str` | The skforecast forecaster class (e.g. `"ForecasterRecursive"`, `"ForecasterDirect"`). |
| `estimator` | `str` | The scikit-learn-compatible estimator (e.g. `"LGBMRegressor"`, `"Ridge"`). |
| `estimator_kwargs` | `dict` | Constructor arguments for the estimator (e.g. `{"n_estimators": 200}`). |
| `steps` | `int` | The forecast horizon (number of steps ahead). |
| `interval` | `list[float]` | Prediction interval quantiles `[lower, upper]`, e.g. `[0.1, 0.9]`. |

!!! tip "Overriding lags and window features"
    The feature-engineering knobs, `lags` and `window_features`, are also
    accepted by `plan()` and `refine_plan()`. They have their own guide,
    [AI-guided plan refinement](llm-plan-refinement.md), which covers both
    setting them manually and letting a natural-language prompt derive them.

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

Switching to a candidate is the safest kind of override: it's a model the assistant already deemed compatible with your data.

!!! tip "Ask the assistant to reason through a tradeoff (optional LLM)"
    `profile.explanation` is deterministic text. If you want a deeper discussion
    of whether a candidate would actually improve accuracy on your specific data,
    pass the profile to `ask()`:

    ```python
    assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")
    profile = assistant.profile(data, target="y", date_column="date")

    answer = assistant.ask(
        prompt  = "Should I switch to LGBMRegressor given my dataset size and frequency?",
        profile = profile,
        steps   = 12,
    )
    print(answer.explanation)
    ```

    The decision and the override are still yours; apply them with `refine_plan()`
    as shown below.

## Two ways to override

### Option A: inline, on `forecast()`

The quickest path: pass the overrides straight to `forecast()`. Anything you don't specify keeps its recommended default.

```python
result = assistant.forecast(
             data             = data,
             target           = "y",
             date_column      = "date",
             steps            = 12,
             estimator        = "LGBMRegressor",
             estimator_kwargs = {"n_estimators": 200, "learning_rate": 0.05},
         )
```

### Option B: explicit, with `refine_plan()`

When you want to inspect or reuse the modified plan, refine it as a separate step. This mirrors the [step-by-step workflow](the-forecasting-workflow.md):

```python
profile = assistant.profile(data, target="y", date_column="date")
plan    = assistant.plan(profile, steps=12)

# Override only what you want; the rest of the plan is preserved.
plan = assistant.refine_plan(
           profile    = profile,
           plan       = plan,
           forecaster = "ForecasterDirect",
           estimator  = "Ridge",
           steps      = 24,
       )

print(plan.forecaster, plan.estimator, plan.steps)   # inspect before running

result = assistant.forecast(
             data        = data,
             target      = "y",
             date_column = "date",
             steps       = 24,
             profile     = profile,
             plan        = plan
         )
```

`refine_plan(profile, plan, **overrides)` returns a new `ForecastPlan` with your changes applied and everything else (lags, metric, preprocessing) intact.

For an end-to-end example of using `ask()` suggestions to drive `refine_plan()` and
validating the change with a backtest, see [Human-in-the-loop forecasting](human-in-the-loop.md).

## Adding prediction intervals

Use `interval=[lower, upper]` (quantiles) to get uncertainty bounds. `[0.1, 0.9]` is an 80% interval; `[0.05, 0.95]` is 90%.

```python
result = assistant.forecast(
             data        = data,
             target      = "y",
             date_column = "date",
             steps       = 12,
             interval    = [0.1, 0.9],  # 80% prediction interval
         )

print(result.predictions.head())
```

The assistant selects an appropriate interval method automatically based on the forecaster: bootstrapping or conformal for the regression-based forecasters, and native intervals for statistical and foundation models. You don't set the method yourself through this API.

## Tuning hyperparameters

Pass estimator constructor arguments via `estimator_kwargs`. These are merged on top of the assistant's built-in defaults (such as `random_state` and verbosity flags), so you only specify what you want to change:

```python
result = assistant.forecast(
             data             = data,
             target           = "y",
             date_column      = "date",
             steps            = 12,
             estimator        = "LGBMRegressor",
             estimator_kwargs = {"n_estimators": 500, "num_leaves": 64, "learning_rate": 0.03}
         )
```

## A note on which estimator fits

The assistant's default estimator depends on how much data you have: smaller datasets favor a simpler, regularized model (`Ridge`) to avoid overfitting, while larger ones use gradient boosting (`LGBMRegressor`). If you override `estimator`, choose one suited to your dataset size; you can always compare options with [backtesting](backtesting.md). The full rule is described in [How it works & trust](how-it-works-and-trust.md).

## Next steps

- **[Backtesting & validation](backtesting.md)**: measure whether your override actually improved the forecast.
- **[Reproducible code](reproducible-code.md)**: export the customized model as a standalone script.
- **[Troubleshooting](troubleshooting.md)**: if an override produces an error at execution time.
- **[Human-in-the-loop forecasting](human-in-the-loop.md)** *(optional)*: let `ask()` suggest the override, then apply and measure it.
