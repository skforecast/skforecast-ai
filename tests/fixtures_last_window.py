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
# ForecasterDirectMultiVariate fails on long-format data with several series,
# so plan() rejects it there; a plan built for the wide data still reaches
# the check with the long profile (a plan passed with other data).
plan_long_multivariate = plan_wide_multivariate


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


def with_infinite(data: pd.DataFrame, positions: list[int], column: str = "y"):
    """
    Return a copy of `data` with the target infinite at `positions` (1 is the
    last row).
    """
    data = data.copy()
    for position in positions:
        data.loc[data.index[-position], column] = np.inf
    return data


def with_leading_missing(data: pd.DataFrame, column: str, n_values: int):
    """
    Return a copy of wide `data` where `column` only has its last `n_values`
    values (the rest, at the start, is missing).
    """
    data = data.copy()
    data.iloc[: len(data) - n_values, data.columns.get_loc(column)] = np.nan
    return data


def long_starting_late(data: pd.DataFrame, series: str, n_values: int):
    """
    Return a copy of long-format `data` where `series` only has its last
    `n_values` rows (the earlier ones are dropped).
    """
    drop = data.index[data["series"] == series][:-n_values]
    return data.drop(index=drop)


# --- Wide data with seven series, each one with only its last 3 values ---
# More series than a message lists (5), for the "and N more" suffix.
data_wide_many = pd.DataFrame(
    {f"s{number}": np.arange(60, dtype=float) for number in range(1, 8)},
    index=_dates,
)
for _column in data_wide_many.columns:
    data_wide_many = with_leading_missing(data_wide_many, _column, 3)
_profile_wide_many = _assistant.profile(
    data_wide_many, target=list(data_wide_many.columns)
)
profile_wide_many = _profile_wide_many.data_profile


# --- Plans in evaluation mode (`end_train` set) ---
# data_single ends on 2023-03-01: with 3 test dates the training partition
# ends on 2023-02-26, so the last training row is position 4 of the data.
# The wide and long items_sales data end on 2012-04-29: 7 test dates end the
# training partition on 2012-04-22.
def in_evaluation(plan, end_train: str):
    """Return a copy of `plan` in evaluation mode, with `end_train` set."""
    return plan.model_copy(update={"end_train": end_train}, deep=True)


plan_single_ridge_eval = in_evaluation(plan_single_ridge, "2023-02-26")
plan_single_lgbm_eval = in_evaluation(plan_single_lgbm, "2023-02-26")

_multiseries_kwargs = {
    "steps": 7,
    "forecaster": "ForecasterRecursiveMultiSeries",
    "lags": [1, 5],
}
plan_wide_multiseries_eval = in_evaluation(
    _assistant.plan(_profile_wide, estimator="Ridge", **_multiseries_kwargs),
    "2012-04-22",
)
plan_long_multiseries_eval = in_evaluation(
    _assistant.plan(_profile_long, estimator="Ridge", **_multiseries_kwargs),
    "2012-04-22",
)

# Seven complete daily series (60 dates, last date 2023-03-01), more than a
# message lists (5), for the "and N more" suffix; 7 test dates end the
# training partition on 2023-02-22.
data_wide_seven = pd.DataFrame(
    {f"s{number}": np.arange(60, dtype=float) for number in range(1, 8)},
    index=_dates,
)
_profile_wide_seven = _assistant.profile(
    data_wide_seven, target=list(data_wide_seven.columns)
)
profile_wide_seven = _profile_wide_seven.data_profile
plan_wide_seven_eval = in_evaluation(
    _assistant.plan(_profile_wide_seven, estimator="Ridge", **_multiseries_kwargs),
    "2023-02-22",
)

# ForecasterFoundation on the three items_sales series, 7 test dates.
plan_wide_foundation_eval = in_evaluation(
    _assistant.plan(_profile_wide, steps=7, forecaster="ForecasterFoundation"),
    "2012-04-22",
)
plan_long_foundation_eval = in_evaluation(
    _assistant.plan(_profile_long, steps=7, forecaster="ForecasterFoundation"),
    "2012-04-22",
)


def long_ending_early(data: pd.DataFrame, series: str, n_rows: int):
    """
    Return a copy of long-format `data` without the last `n_rows` rows of
    `series`, which ends before the others.
    """
    drop = data.index[data["series"] == series][-n_rows:]
    return data.drop(index=drop)
