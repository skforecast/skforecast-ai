# `compare()` — Design for Comparing Multiple Forecasters

Status: proposed (future implementation)
Scope: `ForecastingAssistant.compare()` + `ComparisonResult` schema + CLI command

## 1. Motivation

Users routinely want to answer a single question: *"Given my data, which forecaster
and estimator combination performs best?"* Today they must call `backtest()` once per
configuration and compare the metrics by hand.

`compare()` orchestrates the existing `backtest()` path across several configurations
using the **same** cross-validation strategy, then returns a metric-ranked table plus
the winning configuration in a form that can be fed straight into the other assistant
methods (`forecast()`, `backtest()`, `forecast_code()`).

Design principles (consistent with the rest of the assistant):

- **Deterministic-first.** Ranking is a pure metric sort. The LLM never influences the
  outcome; it only narrates the leaderboard in `explanation`.
- **Reuse, do not rebuild.** Each configuration goes through the existing
  `_prepare_backtest()` -> `run_backtest()` render-and-exec path, so every candidate
  already carries reproducible `code`.
- **Profile once.** The dataset is profiled a single time and the profile is shared
  across all candidates; only the `plan` varies per candidate.

## 2. Method signature

```python
def compare(
    self,
    data,
    cv: TimeSeriesFold,
    target=None,
    date_column=None,
    series_id_column=None,
    forecasters: list[tuple[str, dict]] | None = None,
    metric: str | list[str] | None = None,
    interval: list[float] | None = None,
    profile: ForecastingProfile | None = None,
    show_progress: bool = True,
) -> ComparisonResult:
    ...
```

## 3. Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `data` | pandas Series or DataFrame, str, Path | (required) | Input dataset, single series, or path to a CSV file. |
| `cv` | `TimeSeriesFold` | (required) | Cross-validation strategy applied identically to every candidate. |
| `target` | str, list of str, None | `None` | Column(s) to forecast. Optional when `data` is a pandas Series. |
| `date_column` | str, None | `None` | Name of the timestamp column. When `None`, the index is assumed to be a DatetimeIndex. |
| `series_id_column` | str, None | `None` | Series identifier column for long-format multi-series input. |
| `forecasters` | list of (str, dict), None | `None` | Configurations to compare. Each entry is a `(name, config)` tuple, where `name` labels the row in the results table and `config` holds the forecaster/estimator settings. When `None`, the set is built automatically from `profile.forecaster_candidates`. |
| `metric` | str, list of str, None | `None` | Metric(s) computed per candidate. When a list is passed, the **first** metric is used to rank (matching `grid_search_forecaster`). When `None`, the plan default is used. |
| `interval` | list of float, None | `None` | Prediction interval quantiles `[lower, upper]` computed for every candidate. |
| `profile` | `ForecastingProfile`, None | `None` | Pre-computed profile to skip profiling and guarantee a shared profile across candidates. |
| `show_progress` | bool | `True` | Whether to display a progress bar across candidates. |

### 3.1 Example input for each argument

```python
from skforecast.model_selection import TimeSeriesFold
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant()

# data: path to a CSV (str), a pandas Series, or a DataFrame
data = "dev/h2o_exog.csv"

# cv: shared cross-validation strategy
cv = TimeSeriesFold(steps=12, initial_train_size=180, refit=False)

# target: single column name (str) or list of columns for wide multi-series
target = "y"                       # single series
# target = ["item_1", "item_2"]    # wide multi-series

# date_column: name of the timestamp column when data is not indexed by date
date_column = "date"

# series_id_column: only for long-format multi-series
series_id_column = None            # e.g. "series_id" for long format

# forecasters: list of (label, config) tuples
forecasters = [
    ("recursive_lgbm", {
        "forecaster": "ForecasterRecursive",
        "estimator": "LGBMRegressor",
        "estimator_kwargs": {"n_estimators": 200, "learning_rate": 0.05},
    }),
    ("recursive_hgb", {
        "forecaster": "ForecasterRecursive",
        "estimator": "HistGradientBoostingRegressor",
    }),
    ("direct_ridge", {
        "forecaster": "ForecasterDirect",
        "estimator": "Ridge",
        "lags": [1, 2, 3, 12],
    }),
]
# forecasters = None  -> auto-build from profile.forecaster_candidates

# metric: single metric (str) or list; first ranks the table
metric = "mean_absolute_scaled_error"
# metric = ["mean_absolute_scaled_error", "mean_absolute_error"]

# interval: prediction interval quantiles
interval = [0.1, 0.9]              # 80% interval, or None

# profile: reuse a precomputed profile (optional)
profile = assistant.profile(data=data, target=target, date_column=date_column)

# show_progress
show_progress = True

comparison = assistant.compare(
    data             = data,
    cv               = cv,
    target           = target,
    date_column      = date_column,
    forecasters      = forecasters,
    metric           = metric,
    interval         = interval,
    profile          = profile,
    show_progress    = show_progress,
)
```

### 3.2 `forecasters` config dictionary keys

Each `config` dict accepts the same override keys already understood by `plan()` /
`backtest()`, so no new configuration vocabulary is introduced:

| Key | Type | Example |
|-----|------|---------|
| `forecaster` | str | `"ForecasterRecursive"` |
| `estimator` | str | `"LGBMRegressor"` |
| `estimator_kwargs` | dict | `{"n_estimators": 200, "learning_rate": 0.05}` |
| `lags` | int, list of int | `24` or `[1, 2, 3, 12]` |
| `window_features` | list of dict | `[{"stats": ["mean", "std"], "window_sizes": 7}]` |

## 4. Return schema: `ComparisonResult`

Follows the existing `BacktestResult` pattern (Pydantic + `DisplayMixin` with
`_rich_body`).

```python
class ComparisonResult(DisplayMixin, BaseModel):
    profile: ForecastingProfile           # shared profile used for every candidate
    cv_config: dict                        # resolved TimeSeriesFold parameters
    results: Any                           # pd.DataFrame, ranked best -> worst
    detailed_results: list[BacktestResult] # one BacktestResult per candidate
    best_forecaster: BacktestResult        # the top-ranked candidate
    ranking_metric: str                    # metric used to sort `results`
    explanation: str                       # human-readable summary of the comparison
```

- `results` is the ranked comparison table. One row per candidate with columns
  `['rank', 'name', 'forecaster', 'estimator', <metric columns...>]`, sorted by
  `ranking_metric`. `results` is the term skforecast search users already expect for a
  sorted comparison table.
- `detailed_results` preserves the full `BacktestResult` for every candidate (metrics,
  predictions, reproducible `code`, profile, plan) for drill-down.
- `best_forecaster` is the single top-ranked `BacktestResult`.

### 4.1 Display (`_rich_body`)

Renders in this order, reusing existing helpers:

1. `render_explanation(self.explanation)`
2. the ranked `results` table (via `render_metrics` / `render_dataframe`)
3. `render_cv_config(self.cv_config)`
4. `render_profile(self.profile)`

## 5. Seeing and reusing the best configuration (key requirement)

`return_best` is intentionally **not** included. A boolean flag does not solve the real
need, which is: *"How do I inspect the winning configuration and then actually use it?"*

Because every candidate is a full `BacktestResult`, the winning configuration is already
a first-class object carrying both a `profile` and a `plan`. These are exactly the two
objects the other assistant methods accept, so the best configuration is reusable with
no new plumbing.

### 5.1 See it

```python
best = comparison.best_forecaster        # BacktestResult

print(comparison.results)                # ranked leaderboard
print(best.plan)                         # full plan: forecaster, estimator, lags, ...
print(best.metrics)                      # its backtest metrics
print(best.code)                         # exact reproducible script
```

### 5.2 Use it in other methods

The winning `profile` and `plan` flow directly into the rest of the API:

```python
# Fit on all data and forecast the future with the winning configuration
forecast = assistant.forecast(
    data    = data,
    steps   = 12,
    target  = target,
    profile = best.profile,
    plan    = best.plan,
)

# Re-run backtesting with the winning configuration (e.g. a different cv)
backtest = assistant.backtest(
    data    = data,
    cv      = cv,
    target  = target,
    profile = best.profile,
    plan    = best.plan,
)

# Get the standalone script for the winning configuration
code = assistant.forecast_code(
    data    = data,
    steps   = 12,
    target  = target,
    profile = best.profile,
    plan    = best.plan,
)

# Or simply reuse the code that compare() already generated
print(best.code)
```

This makes the "pick the winner and run with it" flow explicit and object-based, rather
than relying on hidden state toggled by a flag.

## 6. Ranking behavior

- Candidates are backtested independently with the shared `cv`.
- The results table is sorted ascending by `ranking_metric` (all default metrics are
  error metrics where lower is better). `ranking_metric` is the first entry of `metric`,
  or the plan default when `metric` is `None`.
- Ties keep input order, so the table is deterministic and reproducible.
- If a candidate fails to run, its row records the error and it is sorted last, so one
  bad configuration never aborts the whole comparison.

## 7. Auto-generated candidates (`forecasters=None`)

When `forecasters` is `None`, the comparison set is derived from
`profile.forecaster_candidates` (the alternatives already computed by `profile()`),
each paired with the recommended estimator. This gives a zero-configuration call that
"just works":

```python
comparison = assistant.compare(data=data, cv=cv, target=target)
```

## 8. CLI (brief)

A `compare` command mirrors `backtest`:

- Table output: the ranked `results` leaderboard.
- `--json`: the full serialized `ComparisonResult`.
- Consumes an upstream profile via `--from-profile -`, consistent with the existing
  pipe model.

## 9. Suggested build order

1. `ComparisonResult` schema + `_rich_body`.
2. `compare()` in `assistant.py`: profile once -> loop `forecasters` -> `backtest` each
   -> assemble and rank `results` -> select `best_forecaster`.
3. Tests in `tests/test_assistant_compare.py` (error -> basic output -> feature-rich ->
   reuse/edge cases).
4. CLI `compare` command + pipe/JSON tests.
5. (Optional) a single standalone `render_comparison` script that reproduces the whole
   comparison in one file.

## 10. Open questions

- Should `metric` default to a small fixed panel (e.g. MASE + MAE) so the table is
  informative even when the user passes nothing?
- For multi-series tasks, should the ranking use the pooled metric or a per-level
  aggregate, and should the table expose per-level columns?
