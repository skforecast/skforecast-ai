# Phase 2 — Data Profiler

## Goal

Given a pandas DataFrame (or a CSV path), produce a validated `DataProfile`.
Fully deterministic — no LLM needed.

## Files to Create

```
skforecast_ai/profiling/data_profile.py    (main profiler function)
skforecast_ai/profiling/frequency.py       (frequency inference logic)
tests/test_data_profile.py
tests/conftest.py                          (shared fixtures: sample DataFrames)
```

## Public API

```python
from skforecast_ai.profiling import create_data_profile

profile = create_data_profile(
    data=df,
    target="sales",
    date_column="date",           # optional, auto-detected if index is datetime
    series_id_column=None,        # for multi-series
)
# Returns: DataProfile
```

## Logic to Implement

| Function | Responsibility |
|----------|----------------|
| `create_data_profile()` | Orchestrator: calls each sub-detector, assembles DataProfile |
| `detect_date_column()` | Finds datetime column in columns or index |
| `infer_frequency()` | Infers pandas frequency string from datetime index |
| `detect_series_structure()` | Determines single-series vs multi-series (n_series, series_id_column) |
| `detect_exog_columns()` | Identifies exogenous columns (everything except target, date, series_id) |
| `detect_categorical_exog()` | Identifies categorical dtype columns among exog |
| `count_missing_values()` | Per-column NaN counts |
| `estimate_seasonality()` | Heuristic seasonality from frequency (hourly→24, daily→7, monthly→12) |
| `generate_warnings()` | Warnings for short series, high missing rate, no frequency, etc. |

## Tests (tests/test_data_profile.py)

| Test | Input | Key assertion |
|------|-------|---------------|
| `test_single_series_daily` | 365 rows, daily DatetimeIndex, 1 target | `n_series=1`, `frequency="D"` |
| `test_single_series_hourly_with_exog` | Hourly, target + 2 exog columns | `exog_columns` has 2 items, `inferred_seasonalities` contains 24 |
| `test_multi_series_long_format` | Long format with `series_id` column | `n_series > 1`, `series_id_column` set |
| `test_missing_values_detected` | Series with NaNs | `missing_values` dict correct |
| `test_no_datetime_index_warning` | RangeIndex, no date column | warning in `warnings`, `index_type="range"` |
| `test_short_series_warning` | 20 rows | warning about short series |
| `test_frequency_inference` | Various pd frequencies | `infer_frequency()` returns correct string |
| `test_categorical_exog_detected` | DataFrame with `object`/`category` columns | `categorical_exog` populated |
| `test_csv_path_input` | Path to temp CSV | Works the same as DataFrame input |

## Done Criteria

- [ ] `from skforecast_ai.profiling import create_data_profile` works
- [ ] Returns a valid `DataProfile` for single-series and multi-series DataFrames
- [ ] Detects frequency, missing values, exog columns, categorical exog
- [ ] Produces meaningful warnings
- [ ] `pytest tests/test_data_profile.py` passes (≥ 9 tests)
