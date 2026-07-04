"""Shared forecaster-type constants used across modules."""

# Maximum fraction of the available observations that an explicit lag or
# rolling-window feature may span. Mirrors `finalize_lags`'
# `max_fraction_allowed` so manual/LLM overrides honour the same budget as
# the deterministic PACF-based selection.
MAX_FEATURE_FRACTION = 0.33

MULTI_SERIES_FORECASTERS: set[str] = {
    "ForecasterRecursiveMultiSeries",
}

MULTIVARIATE_FORECASTERS: set[str] = {
    "ForecasterDirectMultiVariate",
}

SINGLE_ML_FORECASTERS: set[str] = {
    "ForecasterRecursive",
    "ForecasterDirect",
}

FOUNDATION_FORECASTERS: set[str] = {
    "ForecasterFoundation",
}

STATS_FORECASTERS: set[str] = {
    "ForecasterStats",
}

AUTOREG_FORECASTERS: set[str] = {
    "ForecasterRecursive",
    "ForecasterDirect",
    "ForecasterRecursiveMultiSeries",
    "ForecasterDirectMultiVariate",
}

DIRECT_FORECASTERS: set[str] = {
    "ForecasterDirect",
    "ForecasterDirectMultiVariate",
}

CATEGORICAL_FORECASTERS: set[str] = {
    "ForecasterRecursive",
    "ForecasterDirect",
    "ForecasterRecursiveMultiSeries",
    "ForecasterDirectMultiVariate",
}

DROPNA_FORECASTERS: set[str] = {
    "ForecasterRecursive",
    "ForecasterDirect",
    "ForecasterRecursiveMultiSeries",
    "ForecasterDirectMultiVariate",
}

REQUIRES_DATETIME_FREQ: set[str] = {
    "ForecasterRecursive",
    "ForecasterDirect",
    "ForecasterRecursiveMultiSeries",
    "ForecasterDirectMultiVariate",
    "ForecasterStats",
    "ForecasterFoundation",
}

TREE_BASED_ESTIMATORS: set[str] = {
    "LGBMRegressor",
    "XGBRegressor",
    "CatBoostRegressor",
    "RandomForestRegressor",
    "GradientBoostingRegressor",
    "HistGradientBoostingRegressor",
    "ExtraTreesRegressor",
}

NAN_TOLERANT_ESTIMATORS: set[str] = {
    "LGBMRegressor",
    "CatBoostRegressor",
    "XGBRegressor",
    "HistGradientBoostingRegressor",
}

# Rolling statistics supported by skforecast's `RollingFeatures`. Explicit
# `window_features` overrides (manual, CLI, or LLM-supplied) are validated
# against this set.
ALLOWED_WINDOW_STATS: set[str] = {
    "mean",
    "std",
    "min",
    "max",
    "sum",
    "median",
    "ratio_min_max",
    "coef_variation",
    "ewm",
}
