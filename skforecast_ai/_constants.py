"""Shared forecaster-type constants used across modules."""

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
