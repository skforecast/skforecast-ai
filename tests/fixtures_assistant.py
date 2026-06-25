# Fixtures for assistant tests

import numpy as np
import pandas as pd


# Seed for reproducibility
_rng = np.random.default_rng(42)

# --- Single series fixture (100 daily observations with exog) ---
_n_obs = 100
_dates = pd.date_range("2023-01-01", periods=_n_obs, freq="D")

df_single = pd.DataFrame(
    {
        "date": _dates,
        "sales": np.arange(_n_obs, dtype=float),
        "promo": np.tile([0.0, 1.0], _n_obs // 2),
    }
)

# --- Single series without exog (100 daily observations) ---
df_no_exog = pd.DataFrame(
    {
        "date": _dates,
        "sales": np.arange(_n_obs, dtype=float),
    }
)

# --- Short series fixture (25 daily observations) ---
_n_obs_short = 25
_dates_short = pd.date_range("2023-01-01", periods=_n_obs_short, freq="D")

df_short = pd.DataFrame(
    {
        "date": _dates_short,
        "sales": np.arange(_n_obs_short, dtype=float) + 10.0,
    }
)

# --- Multi-series long format (2 series, 100 observations each) ---
_n_obs_per_series = 100
_dates_multi = pd.date_range("2023-01-01", periods=_n_obs_per_series, freq="D")

df_multi_long = pd.DataFrame(
    {
        "date": np.tile(_dates_multi, 2),
        "series_id": (
            ["store_a"] * _n_obs_per_series
            + ["store_b"] * _n_obs_per_series
        ),
        "value": np.concatenate([
            np.arange(_n_obs_per_series, dtype=float),
            np.arange(_n_obs_per_series, dtype=float) + 50.0,
        ]),
    }
)

# --- Multi-series wide format (2 series as columns) ---
df_multi_wide = pd.DataFrame(
    {
        "date": _dates,
        "series_a": np.arange(_n_obs, dtype=float),
        "series_b": np.arange(_n_obs, dtype=float) + 50.0,
    }
)

# --- Data with missing values in target and exog ---
_target_with_nan = np.arange(_n_obs, dtype=float)
_target_with_nan[10] = np.nan
_target_with_nan[50] = np.nan
_exog_with_nan = _rng.normal(50, 10, _n_obs)
_exog_with_nan[20] = np.nan

df_with_missing = pd.DataFrame(
    {
        "date": _dates,
        "sales": _target_with_nan,
        "promo": _exog_with_nan,
    }
)

# --- Constant target (zero variance) ---
df_constant_target = pd.DataFrame(
    {
        "date": _dates,
        "sales": np.full(_n_obs, 42.0),
    }
)

# --- Single series as a named pandas Series with DatetimeIndex ---
series_single = pd.Series(
    np.arange(_n_obs, dtype=float),
    index=_dates,
    name="sales",
)

# --- Single series as an unnamed pandas Series with DatetimeIndex ---
series_unnamed = pd.Series(
    np.arange(_n_obs, dtype=float),
    index=_dates,
)
