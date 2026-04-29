"""Fixtures for profiling tests."""

import numpy as np
import pandas as pd

# --- Single series, daily, 365 observations ---
df_single_daily = pd.DataFrame(
    {"y": np.arange(365, dtype=float)},
    index=pd.date_range("2023-01-01", periods=365, freq="D"),
)

# --- Single series, hourly, 720 observations with exog ---
_hourly_index = pd.date_range("2023-01-01", periods=720, freq="h")
df_single_hourly_exog = pd.DataFrame(
    {
        "sales": np.arange(720, dtype=float),
        "temperature": np.tile(np.linspace(5.0, 35.0, 24), 30),
        "promo_budget": np.arange(720, dtype=float) * 0.5,
        "holiday": (["no"] * 700 + ["yes"] * 20),
    },
    index=_hourly_index,
)

# --- Multi-series, long format, 3 series ---
_multi_dates = pd.date_range("2023-01-01", periods=100, freq="D")
df_multi_long = pd.DataFrame(
    {
        "date": np.tile(_multi_dates, 3),
        "series_id": np.repeat(["A", "B", "C"], 100),
        "value": np.arange(300, dtype=float),
        "exog_1": np.arange(300, dtype=float) * 0.1,
    }
)

# --- Single series with missing values ---
_missing_values = np.arange(100, dtype=float)
_missing_values[10] = np.nan
_missing_values[20] = np.nan
_missing_values[30] = np.nan
_exog_missing = np.arange(100, dtype=float) * 2
_exog_missing[5] = np.nan
_exog_missing[15] = np.nan
df_with_missing = pd.DataFrame(
    {"target": _missing_values, "exog": _exog_missing},
    index=pd.date_range("2023-01-01", periods=100, freq="D"),
)

# --- RangeIndex, no datetime ---
df_range_index = pd.DataFrame(
    {"value": np.arange(100, dtype=float)},
)

# --- Short series, 20 observations ---
df_short = pd.DataFrame(
    {"y": np.arange(20, dtype=float)},
    index=pd.date_range("2023-01-01", periods=20, freq="D"),
)
