# Phase 3 — Recommendation Engine (Deterministic)

## Goal

Given a `DataProfile` and a user-specified horizon, produce a `ForecastPlan`
using deterministic rules. No LLM.

## Files to Create

```
skforecast_ai/recommendation/rules.py                (rule functions)
skforecast_ai/recommendation/forecaster_selection.py  (orchestrator)
tests/test_recommendation_rules.py
```

## Public API

```python
from skforecast_ai.recommendation import recommend_plan

plan = recommend_plan(
    profile=data_profile,
    horizon=30,
    prefer_foundation=False,   # optional hints
    prefer_statistical=False,
)
# Returns: ForecastPlan
```

## Rules to Implement

Each rule is a pure function `DataProfile + options → partial ForecastPlan fields`.
Rules are derived from the `choosing-a-forecaster` skill and the other domain skills.

| Rule | Input signal | Output |
|------|-------------|--------|
| `select_task_type` | `n_series`, `series_id_column`, user flags | `task_type` |
| `select_forecaster` | `task_type`, user flags | `forecaster` class name |
| `select_estimator` | `task_type`, `n_observations`, exog presence | `estimator` (e.g., `"LGBMRegressor"`) or `None` |
| `select_lags` | `frequency`, `inferred_seasonalities`, `n_observations` | `lags` |
| `select_metric` | `task_type` | `metric` (default `"mean_absolute_error"`) |
| `select_backtesting` | `n_observations`, `horizon` | `backtesting_strategy` description |
| `select_interval_method` | `forecaster`, `n_observations` | `interval_method` or `None` |
| `check_exog_usage` | `exog_columns` | `use_exog` |
| `build_data_requirements` | Profile warnings | `data_requirements` list |
| `build_rationale` | All above outputs | `rationale` string |

## Tests (tests/test_recommendation_rules.py)

| Test | Profile shape | Key assertion |
|------|--------------|---------------|
| `test_single_series_defaults` | 1 series, daily, 365 obs, 0 exog | `ForecasterRecursive`, `lags` includes 7, metric is MAE |
| `test_single_series_with_exog` | 1 series, hourly, 2 exog | `use_exog=True`, lags include 24 |
| `test_multi_series` | 5 series, long format | `ForecasterRecursiveMultiSeries` |
| `test_short_series_suggests_stats` | 1 series, 50 obs | `ForecasterStats` or warning |
| `test_foundation_preference` | User sets `prefer_foundation=True` | `ForecasterFoundation` |
| `test_horizon_larger_than_data_warning` | horizon > n_observations | warning in plan |
| `test_categorical_exog_noted` | Has categorical exog | `data_requirements` mentions categorical handling |
| `test_rationale_not_empty` | Any valid profile | `rationale` is a non-empty string |

## Done Criteria

- [ ] `from skforecast_ai.recommendation import recommend_plan` works
- [ ] Deterministic: same input always produces same output
- [ ] Covers single-series, multi-series, statistical, foundation task types
- [ ] Rules trace back to skills (comments cite skill name)
- [ ] `pytest tests/test_recommendation_rules.py` passes (≥ 8 tests)
