# Understanding your data

Before the assistant picks a model, it inspects your dataset. That inspection (**profiling**) is the foundation everything else is built on: the frequency it detects, the gaps it finds, and the columns it recognizes all drive which forecaster and preprocessing get chosen.

It's also the **first place to look when a forecast looks wrong.** If predictions seem off, a quick read of the profile usually reveals the cause (an undetected frequency, missing values, an exogenous column mistaken for the target).

## Getting a profile

`profile()` runs only the inspection stage: no models are fitted: and returns a `ForecastingProfile`:

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant()
profile = assistant.profile(data, target="y", date_column="date")
```

A `ForecastingProfile` has two layers:

- **`profile.data_profile`**: the structural facts about your dataset (this guide).
- The coarse modeling decisions (`task_type`, `forecaster`, `estimator`, candidates), covered in [Customizing the model](customizing-the-model.md).

```python
dp = profile.data_profile
```

## What the profile tells you

### Shape and series

| Field | Meaning |
| --- | --- |
| `dp.data_format` | `'single'`, `'wide'` (one column per series), or `'long'` (a `series_id_column` distinguishes series). |
| `dp.n_series` | Number of individual time series detected. |
| `dp.series_lengths` | Per-series start, end, and observation count. |
| `dp.n_total_observations` | Pooled total across all series. |

Each entry in `dp.series_lengths` is a `SeriesLengthInfo` with `.start`, `.end`, and `.length` attributes:

```python
for name, info in dp.series_lengths.items():
    print(f"{name}: {info.length} obs  ({info.start} -> {info.end})")
```

The number of observations matters: it directly influences estimator choice (small datasets favor simpler models). See [Customizing the model](customizing-the-model.md).

### Time index

```python
print(dp.index_type)        # 'datetime', 'range', or 'other'
print(dp.frequency)         # e.g. 'MS' (month start), 'D', 'h'
print(dp.frequency_is_set)  # is index.freq already set?
print(dp.index_is_monotonic)# timestamps sorted ascending?
print(dp.has_gaps)          # missing timestamps within the range?
```

| Field | Why it matters |
| --- | --- |
| `dp.index_type` | A `datetime` index unlocks frequency-aware forecasting. |
| `dp.frequency` | The inferred pandas frequency (`'h'`, `'D'`, `'MS'`, …). A reliable frequency is essential. |
| `dp.frequency_is_set` | Whether the index already carries a frequency. |
| `dp.index_is_monotonic` | Whether timestamps are sorted ascending. |
| `dp.has_gaps` | Whether timestamps are missing inside the series' range. |
| `dp.has_duplicate_timestamps` | Whether the same timestamp appears more than once. |

!!! warning "Frequency is the most common cause of trouble"
    `skforecast` needs a datetime index with a known frequency. If `frequency` comes back `None` or `has_gaps` is `True`, that's usually the root cause of a poor or failed forecast. The assistant inserts preprocessing to set the frequency where it can, but irregular or duplicated timestamps may need cleaning on your side first.

### The target

```python
print(dp.target)         # name(s) of the target column(s)
print(dp.target_dtype)   # 'numeric', 'categorical', or 'other'
print(dp.target_stats)   # min / max / mean / std per series
print(dp.missing_target) # count of NaNs per series (only if any exist)
```

`missing_target` is worth checking: NaNs in the target constrain which estimators and preprocessing are viable (some estimators handle them natively, others require dropping or imputing rows).

### Exogenous (predictor) variables

Any column that isn't the target or the date/series identifier is treated as a potential exogenous predictor.

```python
print(dp.exog_columns)      # detected predictor columns
print(dp.categorical_exog)  # which of those are categorical
print(dp.missing_exog)      # count of NaNs per exog column (only if any exist)
```

If a column you intended as the target shows up in `exog_columns` (or vice versa), fix the `target` / `date_column` / `series_id_column` arguments to `profile()`.

### Diagnostics

```python
for w in dp.warnings:
    print(w)
```

`dp.warnings` collects human-readable notes raised during profiling: short series, unset frequency, duplicates, and similar issues. Read these first when something looks off.

## A quick health check

A compact snippet to sanity-check any dataset before forecasting:

```python
dp = assistant.profile(data, target="y", date_column="date").data_profile

print(f"format:         {dp.data_format}  (n_series={dp.n_series})")
print(f"observations:   {dp.n_total_observations}")
print(f"index:          {dp.index_type}  freq={dp.frequency}  (set={dp.frequency_is_set})")
print(f"monotonic:      {dp.index_is_monotonic}")
print(f"gaps/dupes:     {dp.has_gaps} / {dp.has_duplicate_timestamps}")
print(f"missing target: {dp.missing_target}")
print(f"exog columns:   {dp.exog_columns}")
for w in dp.warnings:
    print("warning:", w)
```

!!! tip "Ask the assistant to interpret the profile (optional LLM)"
    If a warning isn't clear, or you want an opinion on how the detected
    frequency or missing values should affect your modeling, `ask()` profiles
    the data first (deterministically) and then the LLM explains the findings:

    ```python
    assistant = ForecastingAssistant(
        llm="openai:gpt-4o-mini", api_key="your_api_key_here"
    )

    prompt = "My series has gaps and missing target values. What should I fix before forecasting?"

    answer = assistant.ask(
                 prompt      = prompt,
                 data        = data,
                 target      = "y",
                 date_column = "date",
                 steps       = 12,
             )
    print(answer.explanation)
    ```

    The assistant will not change the profile or make decisions for you —
    it advises on what to address and how.

## Next steps

- **[Customizing the model](customizing-the-model.md)**: how these data facts drive the model choice, and how to override it.
- **[Backtesting & validation](backtesting.md)**: evaluate the chosen model properly.
- **[Troubleshooting](troubleshooting.md)**: fixes for frequency, NaN, and exogenous-variable errors.
- **[Human-in-the-loop forecasting](human-in-the-loop.md)** *(optional)*: use `ask()` to get advice on a forecast that ran but produced poor results.
