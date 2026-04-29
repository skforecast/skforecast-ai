"""Fixtures for recommendation tests."""

from skforecast_ai.schemas import DataProfile

# --- Single series, daily, 365 observations, no exog ---
profile_single_daily = DataProfile(
    n_observations         = 365,
    n_series               = 1,
    index_type             = "datetime",
    frequency              = "D",
    target                 = "y",
    inferred_seasonalities = [7, 365],
)

# --- Single series, hourly, 720 observations with exog ---
profile_single_hourly_exog = DataProfile(
    n_observations         = 720,
    n_series               = 1,
    index_type             = "datetime",
    frequency              = "h",
    target                 = "sales",
    exog_columns           = ["temperature", "promo_budget", "holiday"],
    categorical_exog       = ["holiday"],
    inferred_seasonalities = [24, 168],
)

# --- Multi-series, long format, 3 series ---
profile_multi_long = DataProfile(
    n_observations         = 300,
    n_series               = 3,
    index_type             = "datetime",
    frequency              = "D",
    target                 = "value",
    date_column            = "date",
    series_id_column       = "series_id",
    exog_columns           = ["exog_1"],
    inferred_seasonalities = [7, 365],
)

# --- Short series, 50 observations ---
profile_short = DataProfile(
    n_observations         = 50,
    n_series               = 1,
    index_type             = "datetime",
    frequency              = "D",
    target                 = "y",
    inferred_seasonalities = [7],
    warnings               = ["Short series (< 50 observations)."],
)

# --- Range index, no datetime ---
profile_no_datetime = DataProfile(
    n_observations         = 200,
    n_series               = 1,
    index_type             = "range",
    target                 = "value",
)

# --- Series with missing values ---
profile_with_missing = DataProfile(
    n_observations         = 365,
    n_series               = 1,
    index_type             = "datetime",
    frequency              = "D",
    target                 = "target",
    exog_columns           = ["exog"],
    missing_values         = {"target": 3, "exog": 2},
    inferred_seasonalities = [7, 365],
)

# --- Series with categorical exog ---
profile_categorical_exog = DataProfile(
    n_observations         = 500,
    n_series               = 1,
    index_type             = "datetime",
    frequency              = "D",
    target                 = "sales",
    exog_columns           = ["temperature", "holiday"],
    categorical_exog       = ["holiday"],
    inferred_seasonalities = [7, 365],
)
