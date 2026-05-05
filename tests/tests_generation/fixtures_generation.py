"""Fixtures for code generation tests."""

from skforecast_ai.schemas import DataProfile, ForecastPlan

# --- Single series, ForecasterRecursive, no exog ---
profile_recursive_no_exog = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
)

plan_recursive_no_exog = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterRecursive",
    estimator            = "LGBMRegressor",
    steps              = 30,
    frequency            = "D",
    lags                 = [1, 2, 3, 4, 5, 6, 7],
    metric               = "mean_absolute_error",
    backtesting_strategy = "TimeSeriesFold",
    interval_method      = "bootstrapping",
    use_exog             = False,
    rationale            = "Single daily series, ML forecaster.",
)

# --- Single series, ForecasterRecursive, with exog ---
profile_recursive_with_exog = DataProfile(
    n_series               = 1,
    n_observations         = 720,
    target                 = "sales",
    index_type             = "datetime",
    frequency              = "h",
    exog_columns           = ["temperature", "promo_budget"],
    categorical_exog       = [],
)

plan_recursive_with_exog = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterRecursive",
    estimator            = "LGBMRegressor",
    steps              = 24,
    frequency            = "h",
    lags                 = [1, 2, 3, 4, 5, 6, 7, 24],
    metric               = "mean_absolute_error",
    backtesting_strategy = "TimeSeriesFold",
    interval_method      = "bootstrapping",
    use_exog             = True,
    rationale            = "Hourly series with exogenous variables.",
)

# --- Single series, ForecasterDirect ---
profile_direct = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
)

plan_direct = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterDirect",
    estimator            = "Ridge",
    steps              = 14,
    frequency            = "D",
    lags                 = [1, 2, 3, 4, 5, 6, 7],
    metric               = "mean_absolute_error",
    backtesting_strategy = "TimeSeriesFold",
    interval_method      = "bootstrapping",
    use_exog             = False,
    rationale            = "Direct forecaster for steps-dependent patterns.",
)

# --- Single series, no interval method ---
plan_recursive_no_interval = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterRecursive",
    estimator            = "Ridge",
    steps              = 10,
    frequency            = "D",
    lags                 = [1, 2, 3, 4, 5, 6, 7],
    metric               = "mean_absolute_error",
    backtesting_strategy = "TimeSeriesFold",
    interval_method      = None,
    use_exog             = False,
    rationale            = "Short series, no intervals.",
)

# --- Multi-series ---
profile_multi_series = DataProfile(
    n_series               = 3,
    n_observations         = 300,
    target                 = "sales",
    date_column            = "date",
    series_id_column       = "series_id",
    index_type             = "datetime",
    frequency              = "D",
    exog_columns           = [],
)

plan_multi_series = ForecastPlan(
    task_type            = "multi_series",
    forecaster           = "ForecasterRecursiveMultiSeries",
    estimator            = "LGBMRegressor",
    steps              = 14,
    frequency            = "D",
    lags                 = [1, 2, 3, 4, 5, 6, 7],
    metric               = "mean_absolute_error",
    backtesting_strategy = "TimeSeriesFold",
    interval_method      = "conformal",
    use_exog             = False,
    rationale            = "Multi-series with global model.",
)

# --- Statistical ---
profile_statistical = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
)

plan_statistical = ForecastPlan(
    task_type            = "statistical",
    forecaster           = "ForecasterStats",
    estimator            = None,
    steps              = 30,
    frequency            = "D",
    lags                 = None,
    metric               = "mean_absolute_error",
    backtesting_strategy = "TimeSeriesFold",
    interval_method      = None,
    use_exog             = False,
    rationale            = "Statistical model per user preference.",
)

# --- Foundation ---
profile_foundation = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
)

plan_foundation = ForecastPlan(
    task_type            = "foundation",
    forecaster           = "ForecasterFoundation",
    estimator            = None,
    steps              = 30,
    frequency            = "D",
    lags                 = None,
    metric               = "mean_absolute_error",
    backtesting_strategy = "TimeSeriesFold",
    interval_method      = None,
    use_exog             = False,
    rationale            = "Foundation model per user preference.",
)
