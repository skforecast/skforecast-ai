# Fixtures for execution tests

import numpy as np
import pandas as pd

from skforecast_ai.schemas import DataProfile, ForecastPlan


# Seed for reproducibility
_rng = np.random.default_rng(42)

# --- Single series fixture (200 daily observations) ---
_n_obs = 200
_dates = pd.date_range("2020-01-01", periods=_n_obs, freq="D")
_target_values = (
    100
    + np.cumsum(_rng.normal(0, 1, _n_obs))
    + 5 * np.sin(2 * np.pi * np.arange(_n_obs) / 7)
)
_exog_values = _rng.normal(50, 10, _n_obs)

df_single = pd.DataFrame(
    {
        "date": _dates,
        "sales": _target_values,
        "promo": _exog_values,
    }
)

# Compute end_train at 80% for date-based split
_end_train_single = str(_dates[int(_n_obs * 0.8) - 1].date())

profile_single = DataProfile(
    n_series=1,
    n_observations=_n_obs,
    target="sales",
    date_column="date",
    index_type="datetime",
    frequency="D",
    exog_columns=["promo"],
    categorical_exog=[],
    missing_target={},
    missing_exog={},
    end_train=_end_train_single,
    warnings=[],
)

plan_single = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": [1, 2, 3, 4, 5, 6, 7], "dropna_from_series": False},
    estimator="Ridge",
    steps=10,
    frequency="D",
    interval_method=None,
    use_exog=True,
    data_requirements=[],
    warnings=[],
    explanation="Single series with exog, Ridge for moderate dataset size.",
)

plan_single_with_intervals = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": [1, 2, 3, 4, 5, 6, 7], "dropna_from_series": False},
    estimator="Ridge",
    steps=10,
    frequency="D",
    interval_method="bootstrapping",
    use_exog=False,
    data_requirements=[],
    warnings=[],
    explanation="Single series with bootstrapping intervals.",
)

# --- Multi-series fixture (200 observations, 2 series) ---
_n_obs_multi = 200
_dates_multi = pd.date_range("2020-01-01", periods=_n_obs_multi // 2, freq="D")
_series_a = 100 + np.cumsum(_rng.normal(0, 1, _n_obs_multi // 2))
_series_b = 200 + np.cumsum(_rng.normal(0, 1, _n_obs_multi // 2))

df_multi = pd.DataFrame(
    {
        "date": np.tile(_dates_multi, 2),
        "series_id": (["A"] * (_n_obs_multi // 2)) + (["B"] * (_n_obs_multi // 2)),
        "value": np.concatenate([_series_a, _series_b]),
    }
)

_end_train_multi = str(_dates_multi[int(len(_dates_multi) * 0.8) - 1].date())

profile_multi = DataProfile(
    data_format="long",
    n_series=2,
    n_observations=_n_obs_multi,
    target="value",
    date_column="date",
    series_id_column="series_id",
    index_type="datetime",
    frequency="D",
    exog_columns=[],
    categorical_exog=[],
    missing_target={},
    missing_exog={},
    end_train=_end_train_multi,
    warnings=[],
)

plan_multi = ForecastPlan(
    task_type="multi_series",
    forecaster="ForecasterRecursiveMultiSeries",
    forecaster_kwargs={"lags": [1, 2, 3, 4, 5, 6, 7], "encoding": "ordinal", "dropna_from_series": False},
    estimator="Ridge",
    steps=5,
    frequency="D",
    interval_method=None,
    use_exog=False,
    data_requirements=[],
    warnings=[],
    explanation="Multi-series with Ridge, ordinal encoding.",
)

# --- Short series fixture (30 observations) ---
_n_obs_short = 30
_dates_short = pd.date_range("2020-01-01", periods=_n_obs_short, freq="D")
_target_short = 50 + np.cumsum(_rng.normal(0, 1, _n_obs_short))

df_short = pd.DataFrame(
    {
        "date": _dates_short,
        "sales": _target_short,
    }
)

_end_train_short = str(_dates_short[int(_n_obs_short * 0.8) - 1].date())

profile_short = DataProfile(
    n_series=1,
    n_observations=_n_obs_short,
    target="sales",
    date_column="date",
    index_type="datetime",
    frequency="D",
    exog_columns=[],
    categorical_exog=[],
    missing_target={},
    missing_exog={},
    end_train=_end_train_short,
    warnings=[],
)

plan_short = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": [1, 2, 3], "dropna_from_series": False},
    estimator="Ridge",
    steps=5,
    frequency="D",
    interval_method=None,
    use_exog=False,
    data_requirements=[],
    warnings=[],
    explanation="Short series with Ridge.",
)

# --- Single series with custom estimator_kwargs ---
plan_single_custom_kwargs = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": [1, 2, 3, 4, 5, 6, 7], "dropna_from_series": False},
    estimator="Ridge",
    estimator_kwargs={"alpha": 0.5},
    steps=10,
    frequency="D",
    interval_method=None,
    use_exog=False,
    data_requirements=[],
    warnings=[],
    explanation="Single series with custom estimator kwargs.",
)
