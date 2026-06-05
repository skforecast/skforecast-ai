# Refactor: Remove `ForecastingAnalysis`

## Reasoning

`ForecastingAnalysis` and its factory `create_forecasting_analysis()` are a premature
abstraction. The class holds eight fields; only one justifies its existence at runtime.

| Field | Problem |
|---|---|
| `effective_n_observations` | Derivable in two lines from `DataProfile.series_lengths` and `DataProfile.n_observations` |
| `min_series_length` / `max_series_length` / `series_length_ratio` / `short_series` | Derivable from `DataProfile.series_lengths` (already computed in Stage 1); never consumed internally |
| `target_variance` | Derivable from `DataProfile.target_stats`; never consumed internally |
| `target_has_trend` | Always `None` — never implemented |
| `viable_context_length` | One-liner (`min(n_observations, 2048)`); never consumed internally |
| **`target_series`** | **The only field with real work:** a cleaned `pd.Series` for PACF lag selection. Cannot be reconstructed from the serialized `DataProfile`. This is the sole reason the class exists. |

The abstraction also fails its stated purpose (separating data access from recommendation
logic): `_analyze_multi_series` and `_analyze_single_ml` both touch raw `data` directly.

**Net result:** one indirection layer, one extra Pydantic model, one extra module, and one
extra call in `assistant.py` — all to pass a single `pd.Series` downstream.

---

## Plan

### Step 1 — Add `extract_target_series` and `_prepare_series_for_pacf` to `recommendation/autoregressive.py`

Move `_prepare_series_for_pacf` verbatim from `profiling/forecasting_analysis.py` and add a
new `extract_target_series` function that consolidates the wide/long/single dispatch
currently spread across `_analyze_multi_series` and `_analyze_single_ml`.

Also update the error message in `select_lags_and_window_features` (line 84) to remove
the now-incorrect reference to `ForecastingAnalysis.target_series`.

**Add at the bottom of `recommendation/autoregressive.py`:**

```python
def extract_target_series(
    data: pd.DataFrame | None,
    profile: "DataProfile",
) -> pd.Series | None:
    """
    Extract and clean the target series from data for PACF lag selection.

    Handles single, wide (list of target columns), and long (series_id)
    formats. Returns None when data is None or no valid series is found.
    """
    if data is None:
        return None

    if isinstance(profile.target, list):
        # Wide format: use first non-empty target column
        for col in profile.target:
            if col in data.columns:
                s = _prepare_series_for_pacf(data[col])
                if len(s) > 0:
                    return s

    elif (
        profile.series_id_column is not None
        and profile.series_id_column in data.columns
        and isinstance(profile.target, str)
        and profile.target in data.columns
    ):
        # Long format: use first series group
        first_id = data[profile.series_id_column].iloc[0]
        subset = data.loc[
            data[profile.series_id_column] == first_id, profile.target
        ]
        s = _prepare_series_for_pacf(subset.reset_index(drop=True))
        if len(s) > 0:
            return s

    elif isinstance(profile.target, str) and profile.target in data.columns:
        # Single series
        s = _prepare_series_for_pacf(data[profile.target])
        if len(s) > 0:
            return s

    return None


def _prepare_series_for_pacf(series: pd.Series) -> pd.Series:
    """
    Prepare a series for PACF computation by trimming edge NaNs and
    interpolating interior ones.
    """
    first_valid = series.first_valid_index()
    last_valid = series.last_valid_index()

    if first_valid is None:
        return series.iloc[0:0]

    trimmed = series.loc[first_valid:last_valid]

    if trimmed.isna().any():
        trimmed = trimmed.interpolate(method="linear")

    return trimmed
```

**Update the error message** in `select_lags_and_window_features` (line 82–85):

```python
# Before
raise ValueError(
    "`target_series` is required for lag selection. The series "
    "must be available from `ForecastingAnalysis.target_series`."
)

# After
raise ValueError(
    "`target_series` is required for lag selection. Pass a non-empty "
    "pd.Series (NaN-free) extracted from the target column."
)
```

---

### Step 2 — Add `target_series` to `ForecastingProfile` and drop `ForecastingAnalysis`

`target_series` must survive from `profile()` into `plan()` (where raw `data` is no longer
available). The current code stores it inside `ForecastingAnalysis`, which is nested in
`ForecastingProfile`. After the refactor, store it flat on `ForecastingProfile` directly.

**`schemas/profiles.py` — remove `ForecastingAnalysis` and update `ForecastingProfile`:**

```python
# Remove the entire ForecastingAnalysis class.

class ForecastingProfile(BaseModel):
    """..."""

    model_config = ConfigDict(arbitrary_types_allowed=True)  # needed for pd.Series

    data_profile: DataProfile
    task_type: Literal[
        "single_series",
        "multi_series",
        "multivariate",
        "statistical",
        "foundation",
    ]
    forecaster: str
    forecaster_candidates: list[str] = Field(default_factory=list)
    estimator: str | None = None
    estimator_candidates: list[str] = Field(default_factory=list)
    target_series: Any = Field(default=None, exclude=True)  # excluded from serialization
    explanation: str
```

The `exclude=True` mirrors the existing behaviour: `target_series` was already excluded from
serialization inside `ForecastingAnalysis`.

---

### Step 3 — Add `_effective_n_observations` helper in `assistant.py`

This replaces the only non-trivial computation that `ForecastingAnalysis` performed.
For multi-series the total observations across all series is `sum(series_lengths.values())`;
for every other task type it is simply `n_observations`.

**Add as a module-level private function in `assistant.py`:**

```python
def _effective_n_observations(data_profile: DataProfile, task_type: str) -> int:
    """
    Compute the observation count to use for lag and estimator sizing.

    For multi-series tasks, returns the total observations across all series
    (sum of series_lengths) because each series contributes independent
    training rows. For all other tasks, returns the per-series length.
    """
    if task_type == "multi_series" and data_profile.series_lengths:
        return sum(data_profile.series_lengths.values())
    return data_profile.n_observations
```

---

### Step 4 — Update `assistant.py`

#### 4a. Update imports

```python
# Remove
from .profiling import create_forecasting_analysis, create_data_profile

# Add
from .profiling import create_data_profile
from .recommendation import extract_target_series  # new export (see Step 5)
```

#### 4b. Update `profile()` method

```python
# Before (lines 188–213)
forecaster, forecaster_candidates = select_forecaster_and_candidates(data_profile)
task_type = select_task_type_from_forecaster(forecaster)
analysis_context = create_forecasting_analysis(data, data_profile, forecaster)

estimator, estimator_candidates = select_estimator_and_candidates(
    task_type=task_type, n_observations=analysis_context.effective_n_observations
)

...

return ForecastingProfile(
    data_profile          = data_profile,
    task_type             = task_type,
    forecaster            = forecaster,
    forecaster_candidates = forecaster_candidates,
    estimator             = estimator,
    estimator_candidates  = estimator_candidates,
    analysis_context      = analysis_context,
    explanation           = explanation,
)

# After
forecaster, forecaster_candidates = select_forecaster_and_candidates(data_profile)
task_type = select_task_type_from_forecaster(forecaster)
n_obs = _effective_n_observations(data_profile, task_type)
target_series = extract_target_series(data, data_profile)

estimator, estimator_candidates = select_estimator_and_candidates(
    task_type=task_type, n_observations=n_obs
)

...

return ForecastingProfile(
    data_profile          = data_profile,
    task_type             = task_type,
    forecaster            = forecaster,
    forecaster_candidates = forecaster_candidates,
    estimator             = estimator,
    estimator_candidates  = estimator_candidates,
    target_series         = target_series,
    explanation           = explanation,
)
```

#### 4c. Update `plan()` method

The `plan()` method currently:
1. Reads `context = profile.analysis_context`
2. On forecaster override, calls `create_forecasting_analysis(None, ...)` and copies
   `target_series` back from the original profile.
3. Uses `context.effective_n_observations` and `context.target_series` downstream.

After the refactor, `target_series` lives on `profile` directly and `effective_n_observations`
is computed inline.

```python
# Before (lines 261–317)
data_profile = profile.data_profile
context      = profile.analysis_context

...

if task_type != profile.task_type:
    context = create_forecasting_analysis(None, data_profile, fc)
    if context.target_series is None:
        context = context.model_copy(
            update={"target_series": profile.analysis_context.target_series}
        )
    est, _ = select_estimator_and_candidates(
        task_type      = task_type,
        n_observations = context.effective_n_observations,
    )
else:
    est = profile.estimator

...

if context.target_series is None or len(context.target_series) == 0:
    n_lags = min(5, max(context.effective_n_observations // 3, 1))
    lags = list(range(1, n_lags + 1))
    window_features = None
else:
    lags, window_features = select_lags_and_window_features(
        n_observations = context.effective_n_observations,
        frequency      = data_profile.frequency,
        target_series  = context.target_series,
    )

# After
data_profile  = profile.data_profile
target_series = profile.target_series  # flat field now

...

if task_type != profile.task_type:
    n_obs = _effective_n_observations(data_profile, task_type)
    est, _ = select_estimator_and_candidates(
        task_type      = task_type,
        n_observations = n_obs,
    )
else:
    n_obs = _effective_n_observations(data_profile, task_type)
    est   = profile.estimator

...

if target_series is None or len(target_series) == 0:
    n_lags = min(5, max(n_obs // 3, 1))
    lags = list(range(1, n_lags + 1))
    window_features = None
else:
    lags, window_features = select_lags_and_window_features(
        n_observations = n_obs,
        frequency      = data_profile.frequency,
        target_series  = target_series,
    )
```

---

### Step 5 — Export `extract_target_series` from `recommendation/__init__.py`

```python
# Add to recommendation/__init__.py
from .autoregressive import extract_target_series, select_lags_and_window_features
```

(Adjust to match whatever the existing `__init__.py` already exports.)

---

### Step 6 — Clean up `profiling/`

**`profiling/__init__.py`:**

```python
# Before
from .forecasting_analysis import create_forecasting_analysis
from .data_profile import create_data_profile

__all__ = ["create_forecasting_analysis", "create_data_profile"]

# After
from .data_profile import create_data_profile

__all__ = ["create_data_profile"]
```

**Delete** `profiling/forecasting_analysis.py`.

---

### Step 7 — Clean up `schemas/`

**`schemas/__init__.py`:**

```python
# Before
from .profiles import DataProfile, ForecastingAnalysis, ForecastingProfile

__all__ = [
    ...,
    "ForecastingAnalysis",
    ...
]

# After
from .profiles import DataProfile, ForecastingProfile

__all__ = [
    ...,
    # ForecastingAnalysis removed
    ...
]
```

---

### Step 8 — Clean up public API `__init__.py`

```python
# Before
from .schemas import (
    ForecastingAnalysis,
    ...
)

__all__ = [
    "ForecastingAnalysis",
    ...
]

# After
# Remove ForecastingAnalysis from both the import and __all__
```

---

## Files changed summary

| File | Action |
|---|---|
| `profiling/forecasting_analysis.py` | **Delete** |
| `profiling/__init__.py` | Remove `create_forecasting_analysis` export |
| `recommendation/autoregressive.py` | Add `extract_target_series` + `_prepare_series_for_pacf`; update error message |
| `recommendation/__init__.py` | Export `extract_target_series` |
| `schemas/profiles.py` | Delete `ForecastingAnalysis`; add `target_series` + `model_config` to `ForecastingProfile` |
| `schemas/__init__.py` | Remove `ForecastingAnalysis` import and export |
| `assistant.py` | Update imports; replace `analysis_context` usages with `target_series` and `_effective_n_observations`; add helper |
| `__init__.py` | Remove `ForecastingAnalysis` import and export |

---

## What is intentionally not migrated

- `min_series_length`, `max_series_length`, `series_length_ratio`, `short_series` — never
  consumed internally. Drop them. If a user-facing display ever needs them, derive on the fly
  from `ForecastingProfile.data_profile.series_lengths`.
- `target_variance` — never consumed internally; derivable from `DataProfile.target_stats`.
- `viable_context_length` — a one-liner; inline at the rendering call site when needed.
- `target_has_trend` — always `None`, never implemented.

---

## Testing checklist

- [ ] `assistant.profile()` returns a valid `ForecastingProfile` (no `analysis_context`)
- [ ] `assistant.plan()` produces correct lags for single-series, multi-series (wide), multi-series (long), and foundation/statistical (lags=None) cases
- [ ] Forecaster override in `plan()` (`forecaster=...`) still works — `target_series` is preserved from the original profile
- [ ] `ForecastingProfile.model_dump()` / `.model_dump_json()` does not include `target_series` (excluded=True)
- [ ] `ForecastingAnalysis` import from `skforecast_ai` raises `ImportError` (public API removed)
- [ ] CLI `profile` and `plan` commands still work end-to-end
