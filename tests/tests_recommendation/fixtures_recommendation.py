"""Fixtures for recommendation tests."""

from skforecast_ai import ForecastingAssistant
from skforecast_ai.schemas import DataProfile, ForecastPlan

from tests.fixtures_datasets import df_h2o, df_h2o_long

# --- Single series, daily, 365 observations, no exog ---
profile_single_daily = DataProfile(
    n_series               = 1,
    series_lengths         = {"y": 365},
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
)

# --- Three monthly series of 96 dates side by side, 288 pooled ---
profile_wide_monthly = DataProfile(
    n_series               = 3,
    series_lengths         = {
                                 name: {
                                     "start": "2016-01-01",
                                     "end": "2023-12-01",
                                     "length": 96,
                                 }
                                 for name in ("a", "b", "c")
                             },
    target                 = ["a", "b", "c"],
    index_type             = "datetime",
    frequency              = "MS",
)

# --- Single series, hourly, 720 observations with exog ---
profile_single_hourly_exog = DataProfile(
    n_series               = 1,
    series_lengths         = {"sales": 720},
    target                 = "sales",
    index_type             = "datetime",
    frequency              = "h",
    exog_columns           = ["temperature", "promo_budget", "holiday"],
    categorical_exog       = ["holiday"],
)

# --- Multi-series, long format, 3 series ---
profile_multi_long = DataProfile(
    n_series               = 3,
    series_lengths         = {"value": 300},
    target                 = "value",
    date_column            = "date",
    series_id_column       = "series_id",
    index_type             = "datetime",
    frequency              = "D",
    exog_columns           = ["exog_1"],
)

# --- Short series, 50 observations ---
profile_short = DataProfile(
    n_series               = 1,
    series_lengths         = {"y": 50},
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
    warnings               = ["Short series (< 50 observations)."],
)

# --- Range index, no datetime ---
profile_no_datetime = DataProfile(
    n_series               = 1,
    series_lengths         = {"value": 200},
    target                 = "value",
    index_type             = "range",
)

# --- Series with missing values ---
profile_with_missing = DataProfile(
    n_series               = 1,
    series_lengths         = {"target": 365},
    target                 = "target",
    missing_target         = {"target": 3},
    index_type             = "datetime",
    frequency              = "D",
    exog_columns           = ["exog"],
    missing_exog           = {"exog": 2},
)

# --- Series with categorical exog ---
profile_categorical_exog = DataProfile(
    n_series               = 1,
    series_lengths         = {"sales": 500},
    target                 = "sales",
    index_type             = "datetime",
    frequency              = "D",
    exog_columns           = ["temperature", "holiday"],
    categorical_exog       = ["holiday"],
)

# --- Single series, daily, 100 observations with explicit date bounds ---
profile_single_daily_100 = DataProfile(
    n_series       = 1,
    series_lengths = {
        "value": {"start": "2023-01-01", "end": "2023-04-10", "length": 100}
    },
    target         = "value",
    index_type     = "datetime",
    frequency      = "D",
    start_date     = "2023-01-01",
)


# --- h2o (monthly, 204 observations) with bootstrapped intervals ---
# The window size of the plans is 36, so an initial training window of 40
# observations leaves 4 rows of a recursive forecaster, and 2 of a direct one
# of 3 steps.
_assistant = ForecastingAssistant()
_profile_h2o = _assistant.profile(df_h2o, target="x")
profile_h2o_complete = _profile_h2o.data_profile
_interval = [0.025, 0.975]
plan_h2o_interval_recursive = _assistant.plan(
    _profile_h2o, steps=1, interval=_interval
)
plan_h2o_interval_direct = _assistant.plan(
    _profile_h2o, steps=3, interval=_interval, forecaster="ForecasterDirect"
)
plan_h2o_no_interval = _assistant.plan(_profile_h2o, steps=1)
plan_h2o_interval_stats = _assistant.plan(
    _profile_h2o, steps=1, interval=_interval, forecaster="ForecasterStats"
)
plan_h2o_interval_baseline = _assistant.plan(
    _profile_h2o, steps=1, interval=_interval, forecaster="ForecasterEquivalentDate"
)


# --- h2o as two series with bootstrapped intervals ---
# The window size of the plans is 36, as above. In wide format both series
# span the 204 observations; in long format the series 'b' starts 20
# observations later (1993-03-01), so a training window of 80 observations
# leaves 44 rows of 'a' and 24 of 'b'.
_profile_h2o_wide = _assistant.profile(
    df_h2o_long.pivot(index="date", columns="series", values="x"),
    target = ["a", "b"],
)
profile_h2o_wide = _profile_h2o_wide.data_profile
plan_h2o_wide_interval_multiseries = _assistant.plan(
    _profile_h2o_wide, steps=1, interval=_interval
)
plan_h2o_wide_interval_multivariate = _assistant.plan(
    _profile_h2o_wide,
    steps      = 3,
    interval   = _interval,
    forecaster = "ForecasterDirectMultiVariate",
)
_profile_h2o_staggered = _assistant.profile(
    df_h2o_long.drop(index=df_h2o_long.index[204:224]),
    target           = "x",
    series_id_column = "series",
    date_column      = "date",
)
profile_h2o_staggered = _profile_h2o_staggered.data_profile
plan_h2o_staggered_interval = _assistant.plan(
    _profile_h2o_staggered, steps=1, interval=_interval
)
# The same series in wide format: 'b' starts with 20 missing values.
_profile_h2o_wide_staggered = _assistant.profile(
    df_h2o_long.drop(index=df_h2o_long.index[204:224]).pivot(
        index="date", columns="series", values="x"
    ),
    target = ["a", "b"],
)
profile_h2o_wide_staggered = _profile_h2o_wide_staggered.data_profile
plan_h2o_wide_staggered_interval = _assistant.plan(
    _profile_h2o_wide_staggered, steps=1, interval=_interval
)


# =============================================================================
# Estimator choice: monthly profiles and plans that carry an estimator
# =============================================================================
def _monthly_profile(length, n_series=1, **kwargs):
    """
    Return the profile of a monthly series of `length` observations, or of
    `n_series` series that share them side by side.
    """
    names = ["y"] if n_series == 1 else [f"s{number}" for number in range(n_series)]
    return DataProfile(
        data_format          = "single" if n_series == 1 else "wide",
        n_series             = n_series,
        series_lengths       = {name: length for name in names},
        span_index_length    = length,
        n_total_observations = length * n_series,
        target               = names[0] if n_series == 1 else names,
        index_type           = "datetime",
        frequency            = "MS",
        **kwargs,
    )


profile_monthly_120 = _monthly_profile(120)
profile_monthly_249 = _monthly_profile(249)
profile_monthly_250 = _monthly_profile(250)
profile_monthly_120_missing_target = _monthly_profile(120, missing_target={"y": 3})
profile_monthly_249_missing_target = _monthly_profile(249, missing_target={"y": 3})
profile_monthly_250_missing_target = _monthly_profile(250, missing_target={"y": 3})
profile_monthly_120_gaps = _monthly_profile(120, has_gaps=True)
profile_monthly_120_missing_exog = _monthly_profile(
    120, exog_columns=["promo"], missing_exog={"promo": 2}
)
# Three series of 120 dates: 360 observations pooled, 120 dates shared.
profile_monthly_3x120 = _monthly_profile(120, n_series=3)
profile_monthly_3x120_missing_target = _monthly_profile(
    120, n_series=3, missing_target={"s0": 3}
)


def _plan(task_type, forecaster, estimator, overridden_fields=(), use_exog=False):
    """
    Return a plan of `forecaster` with `estimator` that records
    `overridden_fields` as the decisions of the user. The forecasters that
    are not autoregressive take no lags.
    """
    autoregressive = task_type in ("single_series", "multi_series", "multivariate")
    return ForecastPlan(
        task_type         = task_type,
        forecaster        = forecaster,
        forecaster_kwargs = {"lags": 3} if autoregressive else {},
        estimator         = estimator,
        steps             = 6,
        frequency         = "MS",
        use_exog          = use_exog,
        overridden_fields = list(overridden_fields),
        explanation       = "Plan with the estimator under test.",
    )


# Plans that record the estimator as a decision of the user.
plan_recursive_ridge_user = _plan(
    "single_series", "ForecasterRecursive", "Ridge", ["estimator"]
)
plan_recursive_lgbm_user = _plan(
    "single_series", "ForecasterRecursive", "LGBMRegressor", ["estimator"]
)
plan_recursive_forest_user = _plan(
    "single_series", "ForecasterRecursive", "RandomForestRegressor", ["estimator"]
)
plan_recursive_forest_exog_user = _plan(
    "single_series", "ForecasterRecursive", "RandomForestRegressor", ["estimator"],
    use_exog=True,
)
plan_direct_lgbm_user = _plan(
    "single_series", "ForecasterDirect", "LGBMRegressor", ["estimator"]
)
plan_multiseries_ridge_user = _plan(
    "multi_series", "ForecasterRecursiveMultiSeries", "Ridge", ["estimator"]
)
plan_multivariate_ridge_user = _plan(
    "multivariate", "ForecasterDirectMultiVariate", "Ridge", ["estimator"]
)
plan_multivariate_lgbm_user = _plan(
    "multivariate", "ForecasterDirectMultiVariate", "LGBMRegressor", ["estimator"]
)

# Plans that do not record it: the rules chose it, or a plan edited by hand or
# a candidate of `compare()`.
plan_recursive_ridge = _plan("single_series", "ForecasterRecursive", "Ridge")
plan_recursive_lgbm = _plan("single_series", "ForecasterRecursive", "LGBMRegressor")
plan_multiseries_lgbm = _plan(
    "multi_series", "ForecasterRecursiveMultiSeries", "LGBMRegressor"
)

# Forecasters without an estimator to choose.
plan_stats = _plan("statistical", "ForecasterStats", "Arima", ["estimator"])
plan_foundation = _plan(
    "foundation", "ForecasterFoundation", "autogluon/chronos-2-small", ["estimator"]
)
plan_baseline = _plan("baseline", "ForecasterEquivalentDate", None)
