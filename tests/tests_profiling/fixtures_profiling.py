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

# --- Duplicate timestamps ---
# The first 5 dates appear twice. In the `*_duplicate_values` frames the
# repeated rows hold other values, which profiling rejects; in the
# `*_identical_duplicates` frames they are copies, which are dropped. One
# copied row has a missing exog value: two NaN count as identical.
_dup_dates = pd.date_range("2023-01-01", periods=50, freq="D")
df_single_duplicate_values = pd.DataFrame(
    {"y": np.arange(55, dtype=float)},
    index=_dup_dates.append(_dup_dates[:5]),
)
_single_no_dup = pd.DataFrame(
    {
        "y": np.arange(50, dtype=float),
        "exog": np.arange(50, dtype=float) * 2,
    },
    index=_dup_dates,
)
_single_no_dup.iloc[2, 1] = np.nan
df_single_identical_duplicates = pd.concat(
    [_single_no_dup, _single_no_dup.iloc[:5]]
)
df_wide_duplicate_values = pd.DataFrame(
    {
        "a": np.arange(55, dtype=float),
        "b": np.arange(55, dtype=float) * 2,
    },
    index=_dup_dates.append(_dup_dates[:5]),
)
_wide_no_dup = df_wide_duplicate_values.iloc[:50]
df_wide_identical_duplicates = pd.concat([_wide_no_dup, _wide_no_dup.iloc[:5]])

# Series B of `df_multi_long` repeats 2023-01-11 (row 110) with another
# value, or as an identical copy.
df_long_duplicate_values_series_b = pd.concat(
    [df_multi_long, df_multi_long.iloc[[110]].assign(value=-1.0)],
    ignore_index=True,
)
df_long_identical_duplicates_series_b = pd.concat(
    [df_multi_long, df_multi_long.iloc[[110]]],
    ignore_index=True,
)
df_multiindex_identical_duplicates_series_b = (
    df_long_identical_duplicates_series_b.set_index(["series_id", "date"])
)
