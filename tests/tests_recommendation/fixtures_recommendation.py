"""Fixtures for recommendation tests."""

from skforecast_ai import ForecastingAssistant
from skforecast_ai.schemas import DataProfile

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
