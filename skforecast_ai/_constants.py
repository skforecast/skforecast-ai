
################################################################################
#                                Constants                                     #
#                                                                              #
# Shared forecaster-type constants used across modules                         #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from typing import Literal, get_args

# Maximum fraction of the available observations that an explicit lag or
# rolling-window feature may span. Mirrors `finalize_lags`'
# `max_fraction_allowed` so manual/LLM overrides honour the same budget as
# the deterministic PACF-based selection.
MAX_FEATURE_FRACTION = 0.33

# ---------------------------------------------------------------------------
# LLM context rendering limits
# ---------------------------------------------------------------------------

# A DataFrame with at most this many rows is sent to the LLM in full.
# Beyond it, only the head and tail are sent plus a per-column summary.
MAX_CONTEXT_DATAFRAME_ROWS = 30

# Rows kept at each end when a DataFrame exceeds the cap above.
CONTEXT_HEAD_TAIL_ROWS = 5

# Leaderboard rows kept when a comparison has many candidates. The table
# is already sorted by the ranking metric, so the top rows are the ones a
# ranking question needs; the tail carries no extra information.
MAX_LEADERBOARD_ROWS = 15

# ---------------------------------------------------------------------------
# Prompt budgeting
# ---------------------------------------------------------------------------

# Context window assumed for local Ollama models. Hosted providers expose
# provider-specific windows, so no budget is imposed for them.
OLLAMA_MAX_CONTEXT_TOKENS = 32768

# Tokens held back for the model's own answer when budgeting the prompt.
RESERVED_RESPONSE_TOKENS = 2048

# Ceiling for the static role prompt. It is paid on every call and is not
# trimmable, so it must not grow into the budget reserved for skills.
MAX_STATIC_PROMPT_TOKENS = 1200

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
WindowStat = Literal[
    "mean",
    "std",
    "min",
    "max",
    "sum",
    "median",
    "ratio_min_max",
    "coef_variation",
    "ewm",
]

ALLOWED_WINDOW_STATS: set[str] = set(get_args(WindowStat))
