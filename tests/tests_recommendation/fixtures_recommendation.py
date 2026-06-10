"""Fixtures for recommendation tests."""

from skforecast_ai.schemas import DataProfile

# --- Single series, daily, 365 observations, no exog ---
profile_single_daily = DataProfile(
    n_series               = 1,
    series_lengths         = {"y": 365},
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
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
