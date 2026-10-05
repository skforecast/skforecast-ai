
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

# Items of a list that `describe()` shows, with "(first N of M)" when the
# list is longer. The reason of the categorical preprocessing step is cut
# at the same length where it is built, so it is cut for `ask()` too.
MAX_DESCRIBE_ITEMS = 15

# ---------------------------------------------------------------------------
# Prompt budgeting
# ---------------------------------------------------------------------------

# Context window assumed for local Ollama models. Hosted providers expose
# provider-specific windows, so no budget is imposed for them.
OLLAMA_MAX_CONTEXT_TOKENS = 32768

# Tokens held back for the model's own answer when budgeting the prompt.
RESERVED_RESPONSE_TOKENS = 2048

# Ceiling on the skill content of a single request, applied whatever the
# provider. Hosted context windows are not known up front, so without it a
# question matching many topics is sent unbounded and fails at the provider.
# Sized so that the skills, the API reference, the role prompt and the reserved
# answer still fit a 32k window.
MAX_SKILL_TOKENS = 20_000

# Ceiling for the static role prompt. It is paid on every call and is not
# trimmable, so it must not grow into the budget reserved for skills.
MAX_STATIC_PROMPT_TOKENS = 1250

FOUNDATION_FORECASTERS: set[str] = {
    "ForecasterFoundation",
}

# Foundation model loaded when a `ForecasterFoundation` plan names none. Its
# capabilities (covariates, categorical covariates, any quantile level) and a
# license with no registered restriction make it the safest default.
DEFAULT_FOUNDATION_MODEL_ID = "autogluon/chronos-2-small"

BASELINE_FORECASTERS: set[str] = {
    "ForecasterEquivalentDate",
}

# Forecasting task category implied by each supported forecaster
FORECASTER_TASK_TYPES: dict[str, str] = {
    "ForecasterRecursive": "single_series",
    "ForecasterDirect": "single_series",
    "ForecasterRecursiveMultiSeries": "multi_series",
    "ForecasterDirectMultiVariate": "multivariate",
    "ForecasterStats": "statistical",
    "ForecasterFoundation": "foundation",
    "ForecasterEquivalentDate": "baseline",
}

# Mapping from pandas frequency strings to seasonal period (m), read first
# by Auto-ARIMA, the rule that leaves ForecasterStats out of the candidates
# and the baseline (`arima_seasonal_period`, `select_baseline_seasonal_period`).
# For data every 5 to 30 minutes it keeps the day, while the lags and window
# features (`estimate_seasonality`) put the hour first. Measured with
# `tools/perf/subhourly_periods.py` on three real and two synthetic sets,
# neither period won on every dataset and horizon, so both stay.
FREQUENCY_TO_SEASONAL_PERIOD: dict[str, int] = {
    "min": 60,
    "5min": 288,
    "10min": 144,
    "15min": 96,
    "30min": 48,
    "h": 24,
    "2h": 12,
    "4h": 6,
    "6h": 4,
    "D": 7,
    "2D": 7,
    "B": 5,
    "W": 52,
    "W-SUN": 52,
    "W-MON": 52,
    "MS": 12,
    "ME": 12,
    "QS": 4,
    "QE": 4,
    "YS": 1,
    "YE": 1,
}

# Seasonal period from which the Auto-ARIMA search becomes impractical.
# Its cost grows with both the seasonal period and the series length, so
# ForecasterStats is not recommended automatically at or above this value.
MAX_STATS_SEASONAL_PERIOD = 24

# Longest seasonal period Auto-ARIMA gets for a frequency that is not in
# `FREQUENCY_TO_SEASONAL_PERIOD` (`arima_seasonal_period`). It is the longest
# period the table gives to a frequency whose ForecasterStats is a recommended
# candidate (`'2h'`, `'MS'`): the table has none between 13 and 23, and
# measured there (`'3min'`, 20) one fit costs what hourly data cost.
MAX_UNTABULATED_ARIMA_PERIOD = 12

# Backtesting cost, counted in estimator fits (a ForecasterDirect training
# fits one estimator per step). Counting fits instead of timing a trial fold
# keeps the decision exact, known before running and reproducible.
# `LONG_TRAINING_FITS` is the threshold of skforecast's LongTrainingWarning,
# which the generated scripts silence with `suppress_warnings=True`, so the
# assistant warns itself before running. `COMPARE_FIT_BUDGET` is the most a
# candidate chosen automatically by `compare()` may cost.
LONG_TRAINING_FITS = 50
COMPARE_FIT_BUDGET = 500

# Backtesting cost of a foundation model, counted in inference windows: it
# is never trained, so it loads its weights once and forecasts each series
# in each fold. Above `LONG_INFERENCE_WINDOWS` the assistant warns with
# LongTrainingWarning: about a minute of inference with Chronos-2 small on
# a 4-core CPU (about 27 ms per window, `tools/perf/foundation_cost.py`),
# and about 7 s on a laptop GPU. Kept low on purpose: it protects the
# machine without a GPU, and `amazon/chronos-2` takes 3.5 times longer.
LONG_INFERENCE_WINDOWS = 2000

# Task types of the machine learning forecasters (lags, window features and
# a scikit-learn compatible estimator).
ML_TASK_TYPES: tuple[str, ...] = ("single_series", "multi_series", "multivariate")

# Forecasters whose predictors are lags, window features and the
# differentiation: they are trained on rows built from them, so the first
# `window_size` values of each series only feed the lags of later rows.
AUTOREG_FORECASTERS: set[str] = {
    "ForecasterRecursive",
    "ForecasterDirect",
    "ForecasterRecursiveMultiSeries",
    "ForecasterDirectMultiVariate",
}

# Forecasters with one model per step, all reading the same last window:
# their lags never read a prediction.
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

# Estimators the generated scripts can import, mapped to their module. It is
# the whitelist `plan()` validates against: the estimator name is written
# into the script, so an arbitrary name must never reach it.
SUPPORTED_ESTIMATORS: dict[str, str] = {
    "LGBMRegressor": "lightgbm",
    "Ridge": "sklearn.linear_model",
    "XGBRegressor": "xgboost",
    "CatBoostRegressor": "catboost",
    "RandomForestRegressor": "sklearn.ensemble",
    "HistGradientBoostingRegressor": "sklearn.ensemble",
}

# Transformers a plan can name. The scripts write the constructor of the
# target transformer (`transformer_y`, `transformer_series`) from a closed
# map built from this tuple; `transformer_exog` is checked against it too,
# but the scripts always scale the numeric exogenous variables with
# `StandardScaler`, which they import directly. Adding a name here needs
# those imports and the exogenous transformer to follow.
SUPPORTED_TRANSFORMERS: tuple[str, ...] = ("StandardScaler",)

# Estimators whose constructor takes `**kwargs` and forwards unknown names to
# the library as extra parameters (LightGBM also accepts parameter aliases),
# so an unknown keyword argument is warned about rather than rejected.
PASSTHROUGH_KWARGS_ESTIMATORS: set[str] = {"LGBMRegressor", "XGBRegressor"}

# Regression metrics accepted by skforecast's backtesting, all of them lower
# is better, which is the order `compare()` ranks by. skforecast also accepts
# classification scores, which are higher is better and never apply here.
ALLOWED_METRICS: tuple[str, ...] = (
    "mean_squared_error",
    "mean_absolute_error",
    "mean_absolute_percentage_error",
    "mean_squared_log_error",
    "mean_absolute_scaled_error",
    "root_mean_squared_scaled_error",
    "median_absolute_error",
    "symmetric_mean_absolute_percentage_error",
)

# Blocking preprocessing steps a generated script can contain. Blocking
# steps are written into the script, so the snippet of a plan must match one
# of these `(action, code_snippet)` pairs exactly: a plan loaded from JSON
# cannot add code of its own. Placeholders sit outside quotes and the
# renderer fills them with `repr()`, so a column name with a quote cannot
# close a string. The snippets generated by 0.3.1 are all in the set.
DROP_DUPLICATE_INDEX_SNIPPET = "data = data[~data.index.duplicated(keep='first')]"
DROP_DUPLICATE_ROWS_SNIPPET = (
    "data = data.drop_duplicates(subset=[{series_id_column}, {date_column}], "
    "keep='first')"
)
PROVIDE_DATETIME_INDEX_SNIPPET = (
    "# Set a DatetimeIndex:\n"
    "# data.index = pd.date_range(start=..., periods=len(data), freq=...)"
)
ENCODE_TARGET_SNIPPET = "# Convert target to numeric"
BLOCKING_PREPROCESSING_TEMPLATES: frozenset[tuple[str, str]] = frozenset({
    ("drop_duplicates", DROP_DUPLICATE_INDEX_SNIPPET),
    ("drop_duplicates", DROP_DUPLICATE_ROWS_SNIPPET),
    ("provide_datetime_index", PROVIDE_DATETIME_INDEX_SNIPPET),
    ("encode_target", ENCODE_TARGET_SNIPPET),
})

TREE_BASED_ESTIMATORS: set[str] = {
    "LGBMRegressor",
    "XGBRegressor",
    "CatBoostRegressor",
    "RandomForestRegressor",
    "GradientBoostingRegressor",
    "HistGradientBoostingRegressor",
    "ExtraTreesRegressor",
}

# Estimators that fit and predict with missing values. RandomForestRegressor
# does since scikit-learn 1.4, the minimum skforecast requires. Among the
# supported estimators only the linear model (Ridge) does not.
NAN_TOLERANT_ESTIMATORS: set[str] = {
    "LGBMRegressor",
    "CatBoostRegressor",
    "XGBRegressor",
    "HistGradientBoostingRegressor",
    "RandomForestRegressor",
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

# Path that `profile()` records for data passed in memory, so the generated
# script has a file to load. A profile recording it describes a DataFrame,
# not a file that was read.
PLACEHOLDER_DATA_PATH = "data.csv"
