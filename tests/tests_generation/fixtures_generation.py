"""Fixtures for code generation tests."""

from skforecast_ai.schemas import DataProfile, ForecastPlan, PreprocessingStep

# --- Single series, ForecasterRecursive, no exog ---
profile_recursive_no_exog = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
    end_train              = "2024-10-01",
)

plan_recursive_no_exog = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterRecursive",
    estimator            = "LGBMRegressor",
    steps              = 30,
    frequency            = "D",
    forecaster_kwargs    = {"lags": [1, 2, 3, 4, 5, 6, 7], "dropna_from_series": False},
    interval_method      = "bootstrapping",
    use_exog             = False,
    explanation            = "Single daily series, ML forecaster.",
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
    end_train              = "2024-10-01",
)

plan_recursive_with_exog = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterRecursive",
    estimator            = "LGBMRegressor",
    steps              = 24,
    frequency            = "h",
    forecaster_kwargs    = {"lags": [1, 2, 3, 4, 5, 6, 7, 24], "dropna_from_series": False},
    interval_method      = "bootstrapping",
    use_exog             = True,
    explanation            = "Hourly series with exogenous variables.",
)

# --- Single series, ForecasterRecursive, with window_features and categorical ---
profile_recursive_full = DataProfile(
    n_series               = 1,
    n_observations         = 720,
    target                 = "sales",
    index_type             = "datetime",
    frequency              = "h",
    exog_columns           = ["temperature", "day_of_week"],
    categorical_exog       = ["day_of_week"],
    end_train              = "2024-10-01",
)

plan_recursive_full = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterRecursive",
    estimator            = "Ridge",
    steps              = 24,
    frequency            = "h",
    forecaster_kwargs    = {
        "lags": [1, 7, 24],
        "window_features": [
            {"stats": ["mean", "std"], "window_sizes": 24},
            {"stats": ["mean"], "window_sizes": 168},
        ],
        "transformer_y": "StandardScaler",
        "transformer_exog": "StandardScaler",
        "categorical_features": "auto",
        "dropna_from_series": True,
    },
    interval             = [5, 95],
    interval_method      = "bootstrapping",
    use_exog             = True,
    explanation            = "Full config: window features, transformers, categorical.",
)

# --- Single series, ForecasterDirect ---
profile_direct = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
    end_train              = "2024-10-01",
)

plan_direct = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterDirect",
    estimator            = "Ridge",
    steps              = 14,
    frequency            = "D",
    forecaster_kwargs    = {"lags": [1, 2, 3, 4, 5, 6, 7], "steps": 14, "dropna_from_series": False},
    interval_method      = "bootstrapping",
    use_exog             = False,
    explanation            = "Direct forecaster for steps-dependent patterns.",
)

# --- Single series, no interval method ---
plan_recursive_no_interval = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterRecursive",
    estimator            = "Ridge",
    steps              = 10,
    frequency            = "D",
    forecaster_kwargs    = {"lags": [1, 2, 3, 4, 5, 6, 7], "dropna_from_series": False},
    interval_method      = None,
    use_exog             = False,
    explanation            = "Short series, no intervals.",
)

# --- Multi-series (long format) ---
profile_multi_series = DataProfile(
    data_format            = "long",
    n_series               = 3,
    n_observations         = 300,
    target                 = "sales",
    date_column            = "date",
    series_id_column       = "series_id",
    index_type             = "datetime",
    frequency              = "D",
    exog_columns           = [],
    end_train              = "2024-10-01",
)

plan_multi_series = ForecastPlan(
    task_type            = "multi_series",
    forecaster           = "ForecasterRecursiveMultiSeries",
    estimator            = "LGBMRegressor",
    steps              = 14,
    frequency            = "D",
    forecaster_kwargs    = {"lags": [1, 2, 3, 4, 5, 6, 7], "encoding": "ordinal", "dropna_from_series": False},
    interval_method      = "conformal",
    use_exog             = False,
    explanation            = "Multi-series with global model.",
)

# --- Multi-series (wide format) ---
profile_multi_series_wide = DataProfile(
    data_format            = "wide",
    n_series               = 3,
    n_observations         = 300,
    target                 = ["series_a", "series_b", "series_c"],
    index_type             = "datetime",
    frequency              = "D",
    exog_columns           = [],
    end_train              = "2024-10-01",
)

plan_multi_series_wide = ForecastPlan(
    task_type            = "multi_series",
    forecaster           = "ForecasterRecursiveMultiSeries",
    estimator            = "LGBMRegressor",
    steps              = 14,
    frequency            = "D",
    forecaster_kwargs    = {"lags": [1, 2, 3, 4, 5, 6, 7], "encoding": "ordinal", "dropna_from_series": False},
    interval_method      = None,
    use_exog             = False,
    explanation            = "Wide-format multi-series.",
)

# --- Multi-series with exog ---
profile_multi_series_exog = DataProfile(
    data_format            = "long",
    n_series               = 3,
    n_observations         = 300,
    target                 = "sales",
    date_column            = "date",
    series_id_column       = "store_id",
    index_type             = "datetime",
    frequency              = "D",
    exog_columns           = ["temperature", "holiday"],
    categorical_exog       = ["holiday"],
    end_train              = "2024-10-01",
)

plan_multi_series_exog = ForecastPlan(
    task_type            = "multi_series",
    forecaster           = "ForecasterRecursiveMultiSeries",
    estimator            = "LGBMRegressor",
    steps              = 7,
    frequency            = "D",
    forecaster_kwargs    = {
        "lags": [1, 2, 3, 7],
        "encoding": "ordinal",
        "transformer_series": "StandardScaler",
        "transformer_exog": "StandardScaler",
        "categorical_features": "auto",
        "dropna_from_series": False,
    },
    interval_method      = None,
    use_exog             = True,
    explanation            = "Multi-series with exog.",
)

# --- Multivariate ---
profile_multivariate = DataProfile(
    data_format            = "wide",
    n_series               = 3,
    n_observations         = 365,
    target                 = ["series_a", "series_b", "series_c"],
    index_type             = "datetime",
    frequency              = "D",
    exog_columns           = [],
    end_train              = "2024-10-01",
)

plan_multivariate = ForecastPlan(
    task_type            = "multivariate",
    forecaster           = "ForecasterDirectMultiVariate",
    estimator            = "Ridge",
    steps              = 10,
    frequency            = "D",
    forecaster_kwargs    = {"lags": [1, 2, 3], "steps": 10, "dropna_from_series": False},
    interval_method      = None,
    use_exog             = False,
    explanation            = "Multivariate forecaster.",
)

# --- Statistical ---
profile_statistical = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
    end_train              = "2024-10-01",
)

plan_statistical = ForecastPlan(
    task_type            = "statistical",
    forecaster           = "ForecasterStats",
    estimator            = None,
    steps              = 30,
    frequency            = "D",
    forecaster_kwargs    = {},
    interval_method      = None,
    use_exog             = False,
    explanation            = "Statistical model per user preference.",
)

plan_statistical_with_interval = ForecastPlan(
    task_type            = "statistical",
    forecaster           = "ForecasterStats",
    estimator            = None,
    steps              = 30,
    frequency            = "D",
    forecaster_kwargs    = {},
    interval             = [10, 90],
    interval_method      = "native",
    use_exog             = False,
    explanation            = "Statistical model with intervals.",
)

# --- Foundation ---
profile_foundation = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
    end_train              = "2024-10-01",
)

plan_foundation = ForecastPlan(
    task_type            = "foundation",
    forecaster           = "ForecasterFoundation",
    estimator            = None,
    steps              = 30,
    frequency            = "D",
    forecaster_kwargs    = {},
    interval_method      = None,
    use_exog             = False,
    explanation            = "Foundation model per user preference.",
)

plan_foundation_with_interval = ForecastPlan(
    task_type            = "foundation",
    forecaster           = "ForecasterFoundation",
    estimator            = None,
    steps              = 30,
    frequency            = "D",
    forecaster_kwargs    = {},
    interval             = [10, 90],
    interval_method      = "native",
    use_exog             = False,
    explanation            = "Foundation model with quantiles.",
)

# --- Preprocessing steps fixture ---
profile_needs_preprocessing = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "D",
    frequency_is_set       = False,
    index_is_monotonic     = False,
    has_duplicate_timestamps = True,
    end_train              = "2024-10-01",
)

plan_with_preprocessing = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterRecursive",
    estimator            = "LGBMRegressor",
    steps              = 10,
    frequency            = "D",
    forecaster_kwargs    = {"lags": [1, 2, 3, 4, 5, 6, 7], "dropna_from_series": False},
    interval_method      = None,
    use_exog             = False,
    preprocessing_steps  = [
        PreprocessingStep(
            action="drop_duplicates",
            reason="Duplicate timestamps cause errors in skforecast.",
            code_snippet="data = data[~data.index.duplicated(keep='first')]",
            blocking=True,
        ),
    ],
    explanation            = "Plan with preprocessing steps.",
)

# --- Statistical with exog (Sarimax) ---
profile_statistical_exog = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "MS",
    exog_columns           = ["temperature", "holiday"],
    end_train              = "2024-10-01",
)

plan_statistical_sarimax_exog = ForecastPlan(
    task_type            = "statistical",
    forecaster           = "ForecasterStats",
    estimator            = None,
    steps              = 12,
    frequency            = "MS",
    forecaster_kwargs    = {"stats_model": "Sarimax"},
    interval             = [10, 90],
    interval_method      = "native",
    use_exog             = True,
    explanation            = "Sarimax model with exogenous variables.",
)

# --- Statistical ETS ---
plan_statistical_ets = ForecastPlan(
    task_type            = "statistical",
    forecaster           = "ForecasterStats",
    estimator            = None,
    steps              = 12,
    frequency            = "MS",
    forecaster_kwargs    = {"stats_model": "Ets"},
    interval_method      = None,
    use_exog             = False,
    explanation            = "ETS model.",
)

# --- Multivariate with exog ---
profile_multivariate_exog = DataProfile(
    data_format            = "wide",
    n_series               = 3,
    n_observations         = 365,
    target                 = ["series_a", "series_b", "series_c"],
    index_type             = "datetime",
    frequency              = "D",
    exog_columns           = ["temperature", "promo"],
    end_train              = "2024-10-01",
)

plan_multivariate_exog = ForecastPlan(
    task_type            = "multivariate",
    forecaster           = "ForecasterDirectMultiVariate",
    estimator            = "LGBMRegressor",
    steps              = 10,
    frequency            = "D",
    forecaster_kwargs    = {"lags": [1, 2, 3], "steps": 10, "dropna_from_series": False},
    interval_method      = "bootstrapping",
    use_exog             = True,
    explanation            = "Multivariate with exog.",
)

# --- Foundation with custom model_id and exog ---
profile_foundation_exog = DataProfile(
    n_series               = 1,
    n_observations         = 500,
    target                 = "y",
    index_type             = "datetime",
    frequency              = "h",
    exog_columns           = ["temperature"],
    end_train              = "2024-10-01",
)

plan_foundation_custom = ForecastPlan(
    task_type            = "foundation",
    forecaster           = "ForecasterFoundation",
    estimator            = None,
    steps              = 24,
    frequency            = "h",
    forecaster_kwargs    = {"model_id": "autogluon/chronos-2-base", "context_length": 4096},
    interval             = [20, 80],
    interval_method      = "native",
    use_exog             = True,
    explanation            = "Foundation model with custom model_id and exog.",
)

# --- Foundation multi-series ---
profile_foundation_multi = DataProfile(
    data_format            = "wide",
    n_series               = 3,
    n_observations         = 365,
    target                 = ["series_a", "series_b", "series_c"],
    index_type             = "datetime",
    frequency              = "D",
    end_train              = "2024-10-01",
)

plan_foundation_multi = ForecastPlan(
    task_type            = "foundation",
    forecaster           = "ForecasterFoundation",
    estimator            = None,
    steps              = 14,
    frequency            = "D",
    forecaster_kwargs    = {"model_id": "autogluon/chronos-2-small"},
    interval_method      = None,
    use_exog             = False,
    explanation            = "Foundation model, multi-series zero-shot.",
)

# --- Single series with differentiation ---
plan_recursive_differentiation = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterRecursive",
    estimator            = "LGBMRegressor",
    steps              = 7,
    frequency            = "D",
    forecaster_kwargs    = {"lags": [1, 2, 3, 7], "differentiation": 1, "dropna_from_series": False},
    interval_method      = None,
    use_exog             = False,
    explanation            = "Single series with differentiation.",
)

# --- Single series with date_column (date is not the index) ---
profile_with_date_column = DataProfile(
    n_series               = 1,
    n_observations         = 365,
    target                 = "y",
    date_column            = "datetime",
    index_type             = "range",
    frequency              = "D",
    end_train              = "2024-10-01",
)

plan_with_date_column = ForecastPlan(
    task_type            = "single_series",
    forecaster           = "ForecasterRecursive",
    estimator            = "LGBMRegressor",
    steps              = 10,
    frequency            = "D",
    forecaster_kwargs    = {"lags": [1, 2, 3, 4, 5, 6, 7], "dropna_from_series": False},
    interval_method      = None,
    use_exog             = False,
    explanation            = "Single series where date is a regular column.",
)
