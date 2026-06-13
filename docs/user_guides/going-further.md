# Going further: features & tuning

The assistant gives you a solid, deterministic baseline and the exact code behind it. Two levers usually move accuracy the most from there: **better features** and **tuned hyperparameters**. Both live in `skforecast` itself: you apply them to the generated script, and the [AI assistant](using-the-ai-assistant.md) can explain the options (it ships `feature-engineering`, `feature-selection`, and `hyperparameter-optimization` skills that ground its answers).

!!! note "Where this runs"
    These are `skforecast` capabilities you apply to the exported baseline, not `ForecastingAssistant` methods. Start from `result.code` ([Reproducible code](reproducible-code.md)) and extend it.

## Feature engineering

The biggest, cheapest wins are usually calendar and rolling features. All of these are built into `skforecast.preprocessing`, with no extra dependencies.

**Calendar features** with `DateTimeFeatureTransformer` (use as `transformer_exog`):

```python
from skforecast.preprocessing import DateTimeFeatureTransformer

transformer_exog = DateTimeFeatureTransformer(
    features=["month", "day_of_week", "week", "hour"],
    encoding="cyclical",   # 'cyclical' | 'onehot' | 'spline' | None
)
```

**Rolling statistics** with `RollingFeatures` (mean, std, min, max, … over a window), passed via the `window_features` argument the assistant already configures for you. For non-stationary series, the `differentiation` argument makes the target stationary before modelling.

After adding features, prune redundant ones with `select_features` (the `feature-selection` skill covers this) so the model (and any search) stays tractable.

## Hyperparameter optimization

The assistant fixes a sensible estimator configuration deterministically. To push accuracy, run a search over the exported forecaster. `skforecast` offers three strategies:

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
    forecaster=forecaster, y=data["target"], cv=cv,
    search_space=search_space, metric="mean_absolute_error",
    n_trials=50, return_best=True, random_state=123,
)
```

Tips that save the most time and grief:

- **Set `return_best=True`** or the forecaster is *not* updated with the winning parameters.
- **Screen fast, then validate.** Use `OneStepAheadFold` for a quick first pass over many trials, then confirm the top candidates with `TimeSeriesFold`.
- **Use ≥ 20–50 trials** for Bayesian search to explore meaningfully.
- Multi-series and statistical models have matching functions (`bayesian_search_forecaster_multiseries`, `grid_search_stats`).

## Fold it back into the loop

Feed a tuned configuration back through the assistant with `refine_plan(estimator=..., estimator_kwargs=...)` so the rest of your pipeline (and the generated code) stays consistent, then re-[backtest](backtesting.md) to confirm the gain is real. That's the [human-in-the-loop workflow](human-in-the-loop.md) applied to tuning.

## Next steps

- **[Customizing the model](customizing-the-model.md)**: apply a tuned configuration via overrides.
- **[Backtesting & validation](backtesting.md)**: measure whether the change actually helped.
- **[Multiple series](forecasting-multiple-series.md)**: features and tuning across many series at once.
