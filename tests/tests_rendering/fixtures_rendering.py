# Fixtures for rendering module tests

from types import SimpleNamespace

from skforecast_ai.schemas import DataProfile, ForecastPlan


# =============================================================================
# DataProfile fixtures
# =============================================================================

profile_single = DataProfile(
    data_format="single",
    n_series=1,
    series_lengths={"sales": 100},
    target="sales",
    target_dtype="numeric",
    target_stats={"sales": {"min": 10.0, "max": 200.0, "mean": 105.0, "std": 40.0}},
    date_column="date",
    index_type="datetime",
    frequency="D",
    frequency_is_set=False,
    exog_columns=["promo"],
    categorical_exog=[],
    data_path="data.csv",
)

profile_single_no_exog = DataProfile(
    data_format="single",
    n_series=1,
    series_lengths={"sales": 100},
    target="sales",
    target_dtype="numeric",
    target_stats={"sales": {"min": 10.0, "max": 200.0, "mean": 105.0, "std": 40.0}},
    date_column="date",
    index_type="datetime",
    frequency="D",
    frequency_is_set=False,
    exog_columns=[],
    categorical_exog=[],
    data_path="data.csv",
)

profile_single_mixed_exog = DataProfile(
    data_format="single",
    n_series=1,
    series_lengths={"sales": 100},
    target="sales",
    target_dtype="numeric",
    target_stats={"sales": {"min": 10.0, "max": 200.0, "mean": 105.0, "std": 40.0}},
    date_column="date",
    index_type="datetime",
    frequency="D",
    frequency_is_set=False,
    exog_columns=["temp", "holiday"],
    categorical_exog=["holiday"],
    data_path="data.csv",
)

profile_multi_wide = DataProfile(
    data_format="wide",
    n_series=2,
    series_lengths={"series_a": 100, "series_b": 100},
    target=["series_a", "series_b"],
    target_dtype="numeric",
    target_stats={
        "series_a": {"min": 5.0, "max": 150.0, "mean": 75.0, "std": 30.0},
        "series_b": {"min": 8.0, "max": 180.0, "mean": 90.0, "std": 35.0},
    },
    date_column="date",
    index_type="datetime",
    frequency="D",
    frequency_is_set=False,
    exog_columns=[],
    categorical_exog=[],
    data_path="data.csv",
)

profile_multi_long = DataProfile(
    data_format="long",
    n_series=2,
    series_lengths={"store_a": 100, "store_b": 100},
    target="value",
    target_dtype="numeric",
    target_stats={
        "store_a": {"min": 5.0, "max": 150.0, "mean": 75.0, "std": 30.0},
        "store_b": {"min": 8.0, "max": 180.0, "mean": 90.0, "std": 35.0},
    },
    date_column="date",
    series_id_column="series_id",
    index_type="datetime",
    frequency="D",
    frequency_is_set=False,
    exog_columns=[],
    categorical_exog=[],
    data_path="data.csv",
)

profile_multi_wide_exog = DataProfile(
    data_format="wide",
    n_series=2,
    series_lengths={"series_a": 100, "series_b": 100},
    target=["series_a", "series_b"],
    target_dtype="numeric",
    target_stats={
        "series_a": {"min": 5.0, "max": 150.0, "mean": 75.0, "std": 30.0},
        "series_b": {"min": 8.0, "max": 180.0, "mean": 90.0, "std": 35.0},
    },
    date_column="date",
    index_type="datetime",
    frequency="D",
    frequency_is_set=False,
    exog_columns=["promo", "holiday"],
    categorical_exog=["holiday"],
    data_path="data.csv",
)

profile_multi_long_exog = DataProfile(
    data_format="long",
    n_series=2,
    series_lengths={"store_a": 100, "store_b": 100},
    target="value",
    target_dtype="numeric",
    target_stats={
        "store_a": {"min": 5.0, "max": 150.0, "mean": 75.0, "std": 30.0},
        "store_b": {"min": 8.0, "max": 180.0, "mean": 90.0, "std": 35.0},
    },
    date_column="date",
    series_id_column="series_id",
    index_type="datetime",
    frequency="D",
    frequency_is_set=False,
    exog_columns=["promo"],
    categorical_exog=[],
    data_path="data.csv",
)


# =============================================================================
# ForecastPlan fixtures
# =============================================================================
#
# The train/test split boundary now lives on the plan via ``end_train``.
# Fixtures below carry a concrete ``end_train`` so they render/execute in
# EVALUATION mode (split + metrics). Prediction-mode fixtures with
# ``end_train=None`` are defined further down.
# =============================================================================

plan_single_recursive = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": 7},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=True,
    end_train="2023-03-12",
    explanation="Single series recursive forecasting with LightGBM.",
)

plan_single_recursive_no_exog = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": 7},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Single series recursive forecasting without exogenous.",
)

plan_single_direct = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterDirect",
    forecaster_kwargs={"lags": 7},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=5,
    frequency="D",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Single series direct forecasting.",
)

plan_single_with_intervals = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": 7},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    interval=[0.1, 0.9],
    interval_method="bootstrapping",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Single series with prediction intervals.",
)

plan_single_with_window_features = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={
        "lags": 7,
        "window_features": [{"stats": ["mean", "std"], "window_sizes": 7}],
    },
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Single series with rolling window features.",
)

plan_single_with_transformer_y = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": 7, "transformer_y": "StandardScaler"},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Single series with transformer_y.",
)

plan_single_with_transformer_exog = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": 7, "transformer_exog": "StandardScaler"},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=True,
    end_train="2023-03-12",
    explanation="Single series with transformer_exog.",
)

plan_multi_series = ForecastPlan(
    task_type="multi_series",
    forecaster="ForecasterRecursiveMultiSeries",
    forecaster_kwargs={"lags": 7, "encoding": "ordinal"},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Multi-series forecasting with global model.",
)

plan_multi_series_exog = ForecastPlan(
    task_type="multi_series",
    forecaster="ForecasterRecursiveMultiSeries",
    forecaster_kwargs={"lags": 7, "encoding": "ordinal"},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=True,
    end_train="2023-03-12",
    explanation="Multi-series forecasting with exogenous variables.",
)

plan_multi_series_with_transformer_series = ForecastPlan(
    task_type="multi_series",
    forecaster="ForecasterRecursiveMultiSeries",
    forecaster_kwargs={
        "lags": 7,
        "encoding": "ordinal",
        "transformer_series": "StandardScaler",
    },
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Multi-series with transformer_series.",
)

plan_multi_series_with_window_features = ForecastPlan(
    task_type="multi_series",
    forecaster="ForecasterRecursiveMultiSeries",
    forecaster_kwargs={
        "lags": 7,
        "encoding": "ordinal",
        "window_features": [{"stats": ["mean"], "window_sizes": 7}],
    },
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Multi-series with window features.",
)

plan_multivariate = ForecastPlan(
    task_type="multivariate",
    forecaster="ForecasterDirectMultiVariate",
    forecaster_kwargs={"lags": 7},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=5,
    frequency="D",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Multivariate forecasting.",
)

plan_statistical = ForecastPlan(
    task_type="statistical",
    forecaster="ForecasterStats",
    forecaster_kwargs={},
    estimator=None,
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Auto-ARIMA statistical forecasting.",
)

plan_statistical_with_intervals = ForecastPlan(
    task_type="statistical",
    forecaster="ForecasterStats",
    forecaster_kwargs={},
    estimator=None,
    estimator_kwargs={},
    steps=10,
    frequency="D",
    interval=[0.1, 0.9],
    interval_method="native",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Auto-ARIMA with prediction intervals.",
)

plan_foundation = ForecastPlan(
    task_type="foundation",
    forecaster="ForecasterFoundation",
    forecaster_kwargs={},
    estimator=None,
    estimator_kwargs={"model_id": "autogluon/chronos-2-small", "context_length": 512},
    steps=10,
    frequency="D",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Foundation model forecasting with Chronos-2.",
)

plan_foundation_with_intervals = ForecastPlan(
    task_type="foundation",
    forecaster="ForecasterFoundation",
    forecaster_kwargs={},
    estimator=None,
    estimator_kwargs={"model_id": "autogluon/chronos-2-small", "context_length": 512},
    steps=10,
    frequency="D",
    interval=[0.1, 0.9],
    interval_method="native",
    use_exog=False,
    end_train="2023-03-12",
    explanation="Foundation model with quantile predictions.",
)


# =============================================================================
# Prediction-mode ForecastPlan fixtures (end_train=None)
# =============================================================================
#
# With ``end_train=None`` the renderers emit prediction-mode code: no
# train/test split, fit on the full data, and no metrics section.
# =============================================================================

plan_single_no_end_train = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": 7},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=False,
    end_train=None,
    explanation="Single series recursive forecasting (prediction mode).",
)

plan_single_predict_exog = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    forecaster_kwargs={"lags": 7},
    estimator="LGBMRegressor",
    estimator_kwargs={},
    steps=10,
    frequency="D",
    use_exog=True,
    end_train=None,
    explanation="Single series with exog (prediction mode).",
)


# =============================================================================
# CV mock for backtesting tests
# =============================================================================

cv_basic = SimpleNamespace(
    steps=10,
    initial_train_size=80,
    refit=False,
    fixed_train_size=False,
    gap=0,
    fold_stride=None,
    skip_folds=None,
    allow_incomplete_fold=True,
    differentiation=None,
)
