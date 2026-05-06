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

REQUIRES_DATETIME_FREQ: set[str] = {
    "ForecasterRecursive",
    "ForecasterDirect",
    "ForecasterRecursiveMultiSeries",
    "ForecasterDirectMultiVariate",
    "ForecasterStats",
    "ForecasterFoundation",
}
