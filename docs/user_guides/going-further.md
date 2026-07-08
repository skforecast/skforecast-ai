# Going further: customizing & tuning

The assistant gives you a deterministic baseline and the exact code behind it. That baseline is already feature-rich: profiling picks the **lags** (from the series autocorrelation), builds **rolling window features**, and adds **calendar features** when the frequency supports them, and all three are wired into the forecaster for you. "Going further" means *adjusting* those choices, not adding them from scratch.

!!! note "Two ways to customize"
    - **Through the assistant** with `refine_plan()`, for the knobs it exposes (`forecaster`, `estimator`, `estimator_kwargs`, `steps`, `interval`). The plan and the generated code stay in sync.
    - **By editing the exported code** (`result.code`, see [Reproducible code](reproducible-code.md)) for everything else: the lags, the window/calendar features, or any other forecaster argument. These are derived deterministically from the profile and are not exposed as overrides.

## What the baseline already includes

Run `profile()` then `plan()` and inspect what was chosen before changing anything. The concrete decisions (lags, window/calendar features, encoding) live in `plan.forecaster_kwargs`, and the estimator settings in `plan.estimator_kwargs`:

```python
profile = assistant.profile(data, target="y", date_column="date")
plan    = assistant.plan(profile, steps=24)

print(plan.forecaster_kwargs)   # lags, window_features, calendar_features, encoding, ...
print(plan.estimator_kwargs)    # estimator hyperparameters (n_estimators, learning_rate, ...)
```

In the generated script these become real `skforecast` objects, for example:

```python
window_features = RollingFeatures(
    stats        = ["mean", "std", "min", "max"],
    window_sizes = [24, 24, 24, 24],
)
calendar_features = CalendarFeatures(
    features = ["month", "week", "day_of_week", "hour"],
    encoding = "cyclical",
)
```

## Tune what the assistant exposes (`refine_plan`)

To change the estimator, its hyperparameters, the horizon, or the interval, refine the plan. Everything else is re-derived deterministically, so the rest of the pipeline (and the code) stays consistent:

```python
plan = assistant.refine_plan(
           profile          = profile,
           plan             = plan,
           estimator        = "LGBMRegressor",
           estimator_kwargs = {"n_estimators": 300, "learning_rate": 0.05},
       )

result = assistant.forecast(
             data        = data, 
             target      = "y",
             date_column = "date", 
             steps       = 24, 
             profile     = profile, 
             plan        = plan
         )

# The complete, standalone Python script that was executed
print(result.code)
```

Then re-[backtest](backtesting.md) to confirm the change actually helped. This is the [human-in-the-loop workflow](human-in-the-loop.md) applied to tuning.

## Customize lags, features, or any forecaster argument

Lags, `window_features`, and `calendar_features` are not exposed by `refine_plan` (they come from the profile). To change them, start from the exported `result.code` and edit the forecaster construction directly: tweak `lags=...`, adjust the `RollingFeatures` / `CalendarFeatures` definitions, or set any other `skforecast` argument such as `differentiation` (to make a non-stationary series stationary) or `transformer_y`. After adding features, prune redundant ones with `select_features` (the assistant ships a `feature-selection` skill that explains this) so the model stays tractable. For the full range of `skforecast` options, see its [user guides table of contents](https://skforecast.org/latest/user_guides/table-of-contents).

## Hyperparameter optimization *(manual for now)*

Automated hyperparameter search is **not yet built into the assistant**; it is on the roadmap. In the meantime you can run a search yourself over the exported forecaster with `skforecast`, then feed the winning configuration back with `refine_plan(estimator_kwargs=...)`. For the full reference, see skforecast's [hyperparameter tuning and lag selection guide](https://skforecast.org/latest/user_guides/hyperparameter-tuning-and-lags-selection). `skforecast` offers three strategies:

| Strategy | When | Speed |
| --- | --- | --- |
| **Bayesian** (Optuna) | Recommended default | Fastest to converge |
| Random | Large space, limited budget | Medium |
| Grid | Small, exhaustive space | Slowest |

Bayesian search, including `lags` (often the single most impactful parameter) in the space:

```python
from skforecast.recursive import ForecasterRecursive
from skforecast.model_selection import bayesian_search_forecaster, TimeSeriesFold
from lightgbm import LGBMRegressor

forecaster = ForecasterRecursive(estimator=LGBMRegressor(random_state=123), lags=24)
cv = TimeSeriesFold(steps=12, initial_train_size=len(data) - 100, refit=False)

def search_space(trial):
    return {
        "lags": trial.suggest_categorical("lags", [12, 24, [1, 2, 3, 23, 24]]),
        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
        "max_depth": trial.suggest_int("max_depth", 3, 15),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
    }

results, study = bayesian_search_forecaster(
                     forecaster   = forecaster, 
                     y            = data["target"], 
                     cv           = cv,
                     search_space = search_space, 
                     metric       = "mean_absolute_error",
                     n_trials     = 50, 
                     return_best  = True, 
                     random_state = 123,
                 )
```

Tips that save the most time and grief:

- **Set `return_best=True`** or the forecaster is *not* updated with the winning parameters.
- **Screen fast, then validate.** Use `OneStepAheadFold` for a quick first pass over many trials, then confirm the top candidates with `TimeSeriesFold`.
- **Use ≥ 20–50 trials** for Bayesian search to explore meaningfully.
- Multi-series and statistical models have matching functions (`bayesian_search_forecaster_multiseries`, `grid_search_stats`).

## Fold the result back in

Once a search settles on good estimator hyperparameters, feed them back through the assistant with `refine_plan(estimator_kwargs=...)` so the plan and the generated code stay consistent, then re-[backtest](backtesting.md) to confirm the gain is real. That is the [human-in-the-loop workflow](human-in-the-loop.md) applied to tuning.

## Next steps

- **[Customizing the model](customizing-the-model.md)**: apply a tuned configuration via overrides.
- **[Backtesting & validation](backtesting.md)**: measure whether the change actually helped.
- **[Multiple series](forecasting-multiple-series.md)**: features and tuning across many series at once.
