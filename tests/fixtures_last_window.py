# Fixtures for the checks of the last window of the target

import numpy as np
import pandas as pd

from skforecast_ai import ForecastingAssistant

from tests.fixtures_datasets import df_items_sales_long

_assistant = ForecastingAssistant()

# --- Daily single series with a date column, 60 dates ---
# Last date 2023-03-01. Position 1 is the last value, position 5 the value
# of 2023-02-25.
_dates = pd.date_range("2023-01-01", periods=60, freq="D")
data_single = pd.DataFrame({
    "date": _dates,
    "y": 10.0 + np.sin(np.arange(60)) + np.arange(60) * 0.1,
})
profile_single = _assistant.profile(
    data_single, target="y", date_column="date"
).data_profile

# Lags 1 and 5 and a rolling mean of 3, 3 steps: a recursive forecaster reads
# positions 1 (lag 1) and 3, 4 and 5 (lag 5 at steps 3, 2 and 1); the
# rolling mean skips missing values.
_single_kwargs = {
    "steps": 3,
    "lags": [1, 5],
    "window_features": [{"stats": ["mean"], "window_size": 3}],
}
plan_single_ridge = _assistant.plan(
    _assistant.profile(data_single, target="y", date_column="date"),
    estimator="Ridge", **_single_kwargs,
)
plan_single_lgbm = _assistant.plan(
    _assistant.profile(data_single, target="y", date_column="date"),
    estimator="LGBMRegressor", **_single_kwargs,
)
plan_single_direct = _assistant.plan(
    _assistant.profile(data_single, target="y", date_column="date"),
    estimator="Ridge", forecaster="ForecasterDirect", **_single_kwargs,
)
plans_single_without_lags = {
    "stats": _assistant.plan(
        _assistant.profile(data_single, target="y", date_column="date"),
        steps=3, forecaster="ForecasterStats",
    ),
    "foundation": _assistant.plan(
        _assistant.profile(data_single, target="y", date_column="date"),
        steps=3, forecaster="ForecasterFoundation",
    ),
}
# ForecasterEquivalentDate with an offset of 7: the 3 steps read positions
# 7, 6 and 5.
plan_single_baseline = _assistant.plan(
    _assistant.profile(data_single, target="y", date_column="date"),
    steps=3, forecaster="ForecasterEquivalentDate",
).model_copy(update={"forecaster_kwargs": {"offset": 7, "n_offsets": 1}})


def with_missing(data: pd.DataFrame, positions: list[int], column: str = "y"):
    """
    Return a copy of `data` with the target missing at `positions` (1 is the
    last row).
    """
    data = data.copy()
    for position in positions:
        data.loc[data.index[-position], column] = np.nan
    return data


# --- Wide data with three series (items_sales, last date 2012-04-29) ---
data_wide = df_items_sales_long.pivot(
    index="date", columns="series", values="value"
)
data_wide.columns.name = None
_profile_wide = _assistant.profile(data_wide, target=list(data_wide.columns))
profile_wide = _profile_wide.data_profile
plan_wide_ridge = _assistant.plan(
    _profile_wide, estimator="Ridge", **_single_kwargs
)
plan_wide_lgbm = _assistant.plan(
    _profile_wide, estimator="LGBMRegressor", **_single_kwargs
)
plan_wide_multivariate = _assistant.plan(
    _profile_wide, estimator="Ridge", forecaster="ForecasterDirectMultiVariate",
    **_single_kwargs,
)

# --- Long data with three series (items_sales, last date 2012-04-29) ---
data_long = df_items_sales_long
_profile_long = _assistant.profile(
    data_long, target="value", date_column="date", series_id_column="series"
)
profile_long = _profile_long.data_profile
plan_long_ridge = _assistant.plan(
    _profile_long, estimator="Ridge", **_single_kwargs
)
plan_long_lgbm = _assistant.plan(
    _profile_long, estimator="LGBMRegressor", **_single_kwargs
)
plan_long_foundation = _assistant.plan(
    _profile_long, steps=3, forecaster="ForecasterFoundation"
)
# ForecasterDirectMultiVariate fails on long-format data with several series.
plan_long_multivariate = _assistant.plan(
    _profile_long, estimator="Ridge", forecaster="ForecasterDirectMultiVariate",
    **_single_kwargs,
)


def with_missing_long(data: pd.DataFrame, series: str, positions: list[int]):
    """
    Return a copy of long-format `data` with the target of `series` missing at
    `positions` (1 is its last row).
    """
    data = data.copy()
    rows = data.index[data["series"] == series]
    for position in positions:
        data.loc[rows[-position], "value"] = np.nan
    return data
