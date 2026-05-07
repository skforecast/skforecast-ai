"""Deterministic rule functions for the recommendation engine."""

from typing import Any, Literal

from .._constants import (
    AUTOREG_FORECASTERS,
    DIRECT_FORECASTERS,
    CATEGORICAL_FORECASTERS,
    DROPNA_FORECASTERS,
    TREE_BASED_ESTIMATORS, 
    NAN_TOLERANT_ESTIMATORS
)
from ..schemas import DataProfile


def select_task_type(
    profile: DataProfile,
) -> Literal[
    "single_series",
    "multi_series",
]:
    """
    Determine the default forecasting task type from profile shape.

    Parameters
    ----------
    profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    task_type : str
        One of `'single_series'`, `'multi_series'`.

    Notes
    -----
    Source: `skforecast_ai/skills/choosing-a-forecaster/SKILL.md` Step 1.
    """
    if profile.n_series > 1:
        return "multi_series"
    return "single_series"


# TODO: ENhance with checks for date column presence, frequency inference, etc. to
def select_forecaster_and_candidates(
    profile: DataProfile
) -> tuple[str, list[str]]:
    """
    Select the preferred forecaster and ordered compatible candidates.

    Parameters
    ----------
    profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    preferred : str
        Name of the recommended forecaster class.
    candidates : list
        Ordered list of compatible skforecast forecaster class names.
        The first item matches `preferred`.

    Notes
    -----
    Source: `skforecast_ai/skills/choosing-a-forecaster/SKILL.md`.

    """
    
    if profile.n_series > 1:
        
        preferred = "ForecasterRecursiveMultiSeries"
        candidates = [
            "ForecasterRecursiveMultiSeries",
            "ForecasterDirectMultiVariate"
        ]            

    else:
        
        preferred = "ForecasterRecursive"
        candidates = [
            "ForecasterRecursive",
            "ForecasterDirect",
            "ForecasterFoundation",
            "ForecasterStats",
        ]

    return preferred, candidates


def select_task_type_from_forecaster(
    forecaster: str,
) -> Literal[
    "single_series",
    "multi_series",
    "multivariate",
    "statistical",
    "foundation",
]:
    """
    Resolve the task type implied by a selected forecaster.

    Parameters
    ----------
    forecaster : str
        Name of the selected skforecast forecaster class.

    Returns
    -------
    task_type : str
        Forecasting task category associated with `forecaster`.
    """
    mapping = {
        "ForecasterRecursive": "single_series",
        "ForecasterDirect": "single_series",
        "ForecasterRecursiveMultiSeries": "multi_series",
        "ForecasterDirectMultiVariate": "multivariate",
        "ForecasterStats": "statistical",
        "ForecasterFoundation": "foundation"
    }

    if forecaster not in mapping:
        raise ValueError(f"Unknown forecaster '{forecaster}'.")

    return mapping[forecaster]


def select_estimator_and_candidates(
    task_type: str,
    n_observations: int,
) -> tuple[str, list[str]]:
    """
    Select the preferred estimator and ordered compatible candidates.

    Parameters
    ----------
    task_type : str
        Forecasting task category.
    n_observations : int
        Number of observations in the dataset.

    Returns
    -------
    preferred : str
        Name of the recommended estimator class.
    candidates : list
        Ordered list of compatible estimator class names.
        The first item matches `preferred`.

    Notes
    -----
    Source: `skforecast_ai/skills/forecasting-single-series/SKILL.md`.

    """

    if task_type == "statistical":
        return "Arima", ["Arima"]
    
    if task_type == "foundation":
        return "Chronos-2", ["Chronos-2"]

    if n_observations < 250:
        return "Ridge", ["Ridge", "RandomForestRegressor", "LGBMRegressor"]
    
    preferred = "LGBMRegressor"
    candidates = [
        "LGBMRegressor",
        "XGBRegressor",
        "CatBoostRegressor",
        "Ridge",
    ]

    return preferred, candidates


def select_metric(task_type: str) -> str:
    """
    Choose the default evaluation metric for a task type.

    Parameters
    ----------
    task_type : str
        Forecasting task category.

    Returns
    -------
    metric : str
        Name of the evaluation metric.

    Notes
    -----
    Source: `skforecast_ai/skills/hyperparameter-optimization/SKILL.md`.
    """
    if task_type == "classification":
        return "accuracy"
    return "mean_absolute_error"


def select_backtesting(n_observations: int, steps: int) -> str:
    """
    Choose the backtesting fold strategy.

    Parameters
    ----------
    n_observations : int
        Number of observations in the dataset.
    steps : int
        Forecast steps in number of steps.

    Returns
    -------
    backtesting_strategy : str
        Name of the backtesting fold class.

    Notes
    -----
    Source: `skforecast_ai/skills/hyperparameter-optimization/SKILL.md`.
    """
    return "TimeSeriesFold"


def select_autoregressive(
    n_observations: int,
    frequency: str | None = None,
    target_series: "pd.Series" = None,
) -> tuple[list[int], list[dict] | None]:
    """
    Select lags and window features using PACF analysis of the target series.

    Lags are selected using the partial autocorrelation function (PACF):
    lags whose absolute PACF exceeds the asymptotic 95 % white-noise
    threshold (``1.96 / sqrt(n)``) are included. This is the data-aware
    approach recommended by the lag-selection skill.

    Window features follow the feature-engineering skill: a short-window
    ``roll_mean`` (and conditionally ``roll_std`` for heteroscedastic
    series) plus a long-window ``roll_mean`` for trend capture. When a
    rolling mean is added at window size W, redundant contiguous lags
    within that range are pruned.

    Parameters
    ----------
    n_observations : int
        Number of observations available for training.
    frequency : str, default None
        Pandas frequency string (e.g. `'h'`, `'D'`, `'ME'`). Used to
        determine seasonal periods. If None, a frequency-agnostic
        default is used.
    target_series : pandas Series
        Target time series (NaN-free) for PACF-based lag selection.

    Returns
    -------
    lags : list
        Sorted list of lag indices to use as predictors.
    window_features : list or None
        List of window feature configurations (dicts with keys
        `'stats'` and `'window_sizes'`) suitable for constructing
        `RollingFeatures` instances. None when the series is too short
        to benefit from rolling statistics.

    Notes
    -----
    Source: `skforecast_ai/skills/autocorrelation-and-lag-selection/SKILL.md`,
    `skforecast_ai/skills/feature-engineering/SKILL.md`.

    The PACF-based approach follows the skill end-to-end recipe:
    1. Rank lags by |PACF| using `calculate_lag_autocorrelation`.
    2. Filter by the asymptotic 95 % white-noise band: `1.96 / sqrt(n)`.
    3. Enrich with seasonal lags that may not exceed the threshold in
       short series but are structurally important.

    Window features follow the skill practical recipe:
    - `roll_mean` at the primary seasonal period (or generic 7) captures
      the recent level.
    - `roll_std` only when the series coefficient of variation > 0.1
      (heteroscedastic signal worth capturing).
    - A longer `roll_mean` (secondary period or 2x primary) captures
      trend-like slow dynamics.
    - Contiguous lags covered by a rolling mean window are pruned to
      avoid redundancy (skill anti-pattern: "shrink the lag set when
      you add the rolling stat").

    Constraints:
    - `max(lags) < n_observations // 3` (leave enough training rows).
    - `max_window_size < n_observations * 0.25` (preserve training data).
    - When the series is very short (< 30), only minimal lags are used
      and window features are skipped.
    """
    from ..profiling.frequency import estimate_seasonality

    if target_series is None:
        raise ValueError(
            "`target_series` is required for lag selection. The series "
            "must be available from `AnalysisContext.target_series`."
        )

    max_lag_allowed = max(n_observations // 3, 1)
    max_window_allowed = max(int(n_observations * 0.25), 1)

    seasonalities = estimate_seasonality(frequency)
    primary_season = seasonalities[0] if seasonalities else None
    secondary_season = seasonalities[1] if len(seasonalities) > 1 else None

    # --- Very short series: minimal lags, no window features ---
    if n_observations < 30:
        n_lags = min(5, max_lag_allowed)
        return list(range(1, n_lags + 1)), None

    # --- Build lag set from PACF ---
    lags = _select_lags_from_pacf(
        target_series, max_lag_allowed, primary_season, secondary_season
    )

    # --- Build window features ---
    window_features = _build_window_features(
        n_observations     = n_observations,
        max_window_allowed = max_window_allowed,
        primary_season     = primary_season,
        secondary_season   = secondary_season,
        target_series      = target_series,
    )

    # --- Prune redundant lags when rolling mean is present ---
    if window_features is not None:
        lags = _prune_redundant_lags(lags, window_features, primary_season)

    return lags, window_features


def _select_lags_from_pacf(
    target_series: "pd.Series",
    max_lag_allowed: int,
    primary_season: int | None,
    secondary_season: int | None,
) -> list[int]:
    """
    Select lags using PACF significance (skill-recommended approach).

    Parameters
    ----------
    target_series : pandas Series
        Target time series (NaN-free).
    max_lag_allowed : int
        Maximum allowed lag index.
    primary_season : int, None
        Primary seasonal period.
    secondary_season : int, None
        Secondary seasonal period.

    Returns
    -------
    lags : list
        Sorted list of selected lag indices.

    Notes
    -----
    Source: `skforecast_ai/skills/autocorrelation-and-lag-selection/SKILL.md`.
    """
    import numpy as np
    from skforecast.stats import calculate_lag_autocorrelation

    n = len(target_series)
    # PACF requires nlags < n // 2
    n_lags = min(max_lag_allowed, n // 2 - 1)
    n_lags = max(n_lags, 1)

    lag_table = calculate_lag_autocorrelation(
        data=target_series, n_lags=n_lags
    )

    # Asymptotic 95% white-noise threshold
    threshold = 1.96 / np.sqrt(n)

    significant = lag_table.loc[
        lag_table["partial_autocorrelation_abs"] > threshold, "lag"
    ].astype(int).tolist()

    # Filter by max_lag_allowed
    lags = sorted(lag for lag in significant if lag <= max_lag_allowed)

    # Safety net: ensure at least 3 recent lags
    if len(lags) < 3:
        min_recent = min(5, max_lag_allowed)
        for lag in range(1, min_recent + 1):
            if lag not in lags:
                lags.append(lag)
        lags = sorted(lags)

    # Seasonal enrichment: ensure at least one seasonal lag is present
    if primary_season is not None and primary_season <= max_lag_allowed:
        if primary_season not in lags:
            lags.append(primary_season)
            lags = sorted(lags)

    if secondary_season is not None and secondary_season <= max_lag_allowed:
        if secondary_season not in lags:
            lags.append(secondary_season)
            lags = sorted(lags)

    return lags


def _build_window_features(
    n_observations: int,
    max_window_allowed: int,
    primary_season: int | None,
    secondary_season: int | None,
    target_series: "pd.Series" = None,
) -> list[dict] | None:
    """
    Build window feature configurations following the feature-engineering
    skill recommendations.

    Parameters
    ----------
    n_observations : int
        Number of observations available.
    max_window_allowed : int
        Maximum window size that preserves training data.
    primary_season : int, None
        Primary seasonal period.
    secondary_season : int, None
        Secondary seasonal period.
    target_series : pandas Series
        Target series for coefficient of variation check.

    Returns
    -------
    window_features : list or None
        Window feature configurations or None if not applicable.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`.

    The skill recommends:
    - Always include `roll_mean` (the default smoothing signal).
    - Include `roll_std` only when the series is heteroscedastic
      (coefficient of variation > 0.1).
    - Multi-scale: combine short (reactive) and long (trend) windows.
    """
    if n_observations < 60:
        return None

    # Determine whether std is warranted (heteroscedasticity check)
    include_std = True
    if target_series is not None and len(target_series) > 0:
        import numpy as np
        mean_abs = abs(float(np.mean(target_series)))
        if mean_abs > 0:
            cv = float(np.std(target_series)) / mean_abs
            include_std = cv > 0.1

    if primary_season is not None:
        wf_configs = []

        # Short window: roll_mean (+ conditionally roll_std)
        short_window = min(primary_season, max_window_allowed)
        if short_window >= 3:
            stats = ["mean", "std"] if include_std else ["mean"]
            wf_configs.append({
                "stats": stats,
                "window_sizes": short_window,
            })

        # Long window: roll_mean at secondary period or 2x primary
        long_window_size = (
            secondary_season if secondary_season is not None
            else primary_season * 2
        )
        long_window_size = min(long_window_size, max_window_allowed)
        if long_window_size > short_window and long_window_size >= 5:
            wf_configs.append({
                "stats": ["mean"],
                "window_sizes": long_window_size,
            })

        return wf_configs if wf_configs else None

    # No frequency info but enough data: generic rolling window
    generic_window = min(7, max_window_allowed)
    if generic_window >= 3:
        stats = ["mean", "std"] if include_std else ["mean"]
        return [{"stats": stats, "window_sizes": generic_window}]

    return None


def _prune_redundant_lags(
    lags: list[int],
    window_features: list[dict],
    primary_season: int | None,
) -> list[int]:
    """
    Remove contiguous lags that overlap with a rolling mean window.

    When a `roll_mean` of window W is included, keeping all lags
    1..W is redundant for gradient boosting models (the tree can
    reconstruct the average from splits). Retain only representative
    lags (1, W//2, W) plus any seasonal lags within the range.

    Parameters
    ----------
    lags : list
        Current sorted lag list.
    window_features : list
        Window feature configurations.
    primary_season : int, None
        Primary seasonal period (always preserved).

    Returns
    -------
    pruned_lags : list
        Reduced lag list.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`
    (anti-pattern: "keeping lags=range(1, 25) together with
    roll_mean_24 rarely helps").
    """
    # Find the shortest rolling mean window size
    mean_windows = []
    for wf in window_features:
        if "mean" in wf.get("stats", []):
            ws = wf.get("window_sizes")
            if isinstance(ws, int):
                mean_windows.append(ws)

    if not mean_windows:
        return lags

    shortest_mean_window = min(mean_windows)

    # Only prune if we have a solid contiguous block covered by the window
    contiguous_in_window = [lag for lag in lags if lag <= shortest_mean_window]
    if len(contiguous_in_window) < shortest_mean_window * 0.8:
        # Not enough contiguous coverage to justify pruning
        return lags

    # Preserve: lag 1, midpoint, window boundary, seasonal lags, lags > window
    keep = {1, shortest_mean_window // 2, shortest_mean_window}
    if primary_season is not None:
        keep.add(primary_season)

    pruned = []
    for lag in lags:
        if lag > shortest_mean_window:
            pruned.append(lag)
        elif lag in keep:
            pruned.append(lag)

    # Safety: always keep at least 3 lags
    if len(pruned) < 3:
        return lags

    return sorted(pruned)


def select_interval_method(
    forecaster: str,
    n_observations: int,
) -> Literal["bootstrapping", "conformal"] | None:
    """
    Choose the prediction interval method based on the forecaster type.

    Parameters
    ----------
    forecaster : str
        Name of the skforecast forecaster class.
    n_observations : int
        Number of observations in the dataset.

    Returns
    -------
    interval_method : str or None
        `'bootstrapping'`, `'conformal'`, or `None` for forecasters with
        native intervals.

    Notes
    -----
    Source: `skforecast_ai/skills/prediction-intervals/SKILL.md`.
    """
    if n_observations < 100:
        return None
    if forecaster in ("ForecasterRecursive", "ForecasterDirect"):
        return "bootstrapping"
    if forecaster == "ForecasterRecursiveMultiSeries":
        return "conformal"
    return None


def select_transformer_series(
    estimator: str | None,
    task_type: str,
) -> str | None:
    """
    Choose the target series transformer based on estimator type.

    Linear models benefit from scaling the target series to have zero
    mean and unit variance. Tree-based models are invariant to
    monotonic transformations and do not require scaling.

    The returned value maps to `transformer_y` for single-series
    forecasters and `transformer_series` for multi-series forecasters.

    Parameters
    ----------
    estimator : str or None
        Name of the scikit-learn compatible estimator.
    task_type : str
        Forecasting task category.

    Returns
    -------
    transformer_series : str or None
        `'StandardScaler'` when scaling is recommended, `None` otherwise.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`,
    `skforecast_ai/skills/forecasting-single-series/SKILL.md`.
    """
    if task_type in ("statistical", "foundation"):
        return None
    if estimator is None:
        return None
    if estimator in TREE_BASED_ESTIMATORS:
        return None
    return "StandardScaler"


def select_transformer_exog(
    estimator: str | None,
    task_type: str,
    exog_columns: list[str],
    categorical_exog: list[str],
) -> str | None:
    """
    Choose the exogenous variable transformer based on estimator type.

    Linear models benefit from scaling numeric exogenous variables.
    Tree-based models do not require scaling. Categorical columns are
    handled separately by `categorical_features='auto'`.

    Parameters
    ----------
    estimator : str or None
        Name of the scikit-learn compatible estimator.
    task_type : str
        Forecasting task category.
    exog_columns : list
        Names of all exogenous columns.
    categorical_exog : list
        Names of categorical exogenous columns.

    Returns
    -------
    transformer_exog : str or None
        `'StandardScaler'` when scaling is recommended for numeric exog
        columns, `None` otherwise.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`.

    When `'StandardScaler'` is returned, it means the numeric exogenous
    columns should be scaled. The code generator is responsible for
    building the appropriate `ColumnTransformer` that leaves categorical
    columns untouched.
    """
    if task_type in ("statistical", "foundation"):
        return None
    if estimator is None:
        return None
    if not exog_columns:
        return None
    # Only numeric exog columns need scaling
    numeric_exog = [c for c in exog_columns if c not in categorical_exog]
    if not numeric_exog:
        return None
    if estimator in TREE_BASED_ESTIMATORS:
        return None
    return "StandardScaler"


def select_dropna_from_series(
    estimator: str | None,
    missing_target: dict[str, int],
    missing_exog: dict[str, int],
    task_type: str,
) -> bool | None:
    """
    Determine whether to drop NaN rows from training matrices.

    Parameters
    ----------
    estimator : str or None
        Name of the scikit-learn compatible estimator.
    missing_target : dict
        Mapping of target/series name to NaN count.
    missing_exog : dict
        Mapping of exogenous column name to count of missing values.
    task_type : str
        Forecasting task category.

    Returns
    -------
    dropna_from_series : bool or None
        `None` for forecasters without the parameter. `True` when NaN
        rows must be dropped. `False` when the estimator handles NaN
        natively or no missing values exist.

    Notes
    -----
    Source: `skforecast_ai/skills/troubleshooting-common-errors/SKILL.md`,
    `skforecast_ai/resources/llms-full.txt` (NaN handling section).
    """
    if task_type in ("statistical", "foundation"):
        return None
    has_missing = bool(missing_target) or bool(missing_exog)
    if not has_missing:
        return False
    if estimator in NAN_TOLERANT_ESTIMATORS:
        return False
    return True


def check_exog_usage(exog_columns: list[str]) -> bool:
    """
    Determine whether exogenous variables should be included.

    Parameters
    ----------
    exog_columns : list
        Names of detected exogenous columns.

    Returns
    -------
    use_exog : bool
        `True` if at least one exogenous column is available.
    """
    return len(exog_columns) > 0


def build_data_requirements(profile: DataProfile) -> list[str]:
    """
    Build a list of data preparation steps the user should perform.

    Parameters
    ----------
    profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    data_requirements : list
        Human-readable data preparation instructions.

    Notes
    -----
    Source: `skforecast_ai/skills/forecasting-single-series/SKILL.md`,
    `skforecast_ai/skills/troubleshooting-common-errors/SKILL.md`.
    """
    requirements: list[str] = []

    if profile.missing_target or profile.missing_exog:
        requirements.append("Impute missing values before training.")

    if profile.categorical_exog:
        requirements.append(
            "Categorical exogenous variables detected: "
            f"{profile.categorical_exog}. These are handled automatically "
            "by skforecast (categorical_features='auto')."
        )

    if profile.index_type != "datetime":
        requirements.append(
            "Provide a DatetimeIndex or date column for time-based features."
        )

    return requirements


def build_forecaster_kwargs(
    forecaster: str,
    task_type: str,
    steps: int,
    lags: list[int] | None,
    window_features: list | None = None,
    transformer_series: str | None = None,
    transformer_exog: str | None = None,
    dropna_from_series: bool | None = None,
) -> dict[str, Any]:
    """
    Build the keyword arguments dict for instantiating a forecaster.

    The returned dict can be unpacked directly into the forecaster
    constructor (minus `estimator`, which requires import/instantiation
    logic handled separately).

    Parameters
    ----------
    forecaster : str
        Name of the skforecast forecaster class.
    task_type : str
        Forecasting task category.
    steps : int
        Forecast horizon.
    lags : list or None
        Lag indices. None for statistical/foundation forecasters.
    window_features : list or None
        Window feature objects (e.g. `RollingFeatures` instances). None
        when not applicable.
    transformer_series : str or None
        Name of the scaler class for the target series (e.g.
        `'StandardScaler'`). None when no scaling is needed. Stored as
        `transformer_y` for single-series or `transformer_series` for
        multi-series forecasters in the returned dict.
    transformer_exog : str or None
        Name of the scaler class for numeric exogenous variables (e.g.
        `'StandardScaler'`). None when no scaling is needed.
    dropna_from_series : bool or None
        NaN handling flag. None for statistical/foundation forecasters.

    Returns
    -------
    kwargs : dict
        Keyword arguments for the forecaster constructor.

    Notes
    -----
    Source: `skforecast_ai/skills/choosing-a-forecaster/SKILL.md`.
    """
    if task_type in ("statistical", "foundation"):
        return {}

    kwargs: dict[str, Any] = {}

    if forecaster in AUTOREG_FORECASTERS:
        kwargs["lags"] = lags
        kwargs["window_features"] = window_features

    if forecaster in DIRECT_FORECASTERS:
        kwargs["steps"] = steps

    if forecaster == "ForecasterRecursiveMultiSeries":
        kwargs["encoding"] = "ordinal"

    if transformer_series is not None:
        if forecaster in (
            "ForecasterRecursiveMultiSeries",
            "ForecasterDirectMultiVariate",
        ):
            kwargs["transformer_series"] = transformer_series
        else:
            kwargs["transformer_y"] = transformer_series

    if transformer_exog is not None:
        kwargs["transformer_exog"] = transformer_exog

    if forecaster in CATEGORICAL_FORECASTERS:
        kwargs["categorical_features"] = "auto"

    if forecaster in DROPNA_FORECASTERS and dropna_from_series is not None:
        kwargs["dropna_from_series"] = dropna_from_series

    return kwargs


def build_explanation(
    task_type: str,
    forecaster: str,
    estimator: str | None,
    lags: list[int] | None,
    interval_method: str | None,
    profile: DataProfile,
) -> str:
    """
    Assemble a human-readable explanation of the recommendation.

    Parameters
    ----------
    task_type : str
        Selected task type.
    forecaster : str
        Selected forecaster class name.
    estimator : str or None
        Selected estimator name.
    lags : list or None
        Selected lag indices.
    interval_method : str or None
        Selected prediction interval method.
    profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    explanation : str
        Multi-sentence explanation of the recommendation.
    """
    parts = []

    if task_type == "multi_series":
        parts.append(
            f"The dataset contains {profile.n_series} series, so a multi-series "
            f"forecaster ({forecaster}) is recommended."
        )
    elif task_type == "multivariate":
        parts.append(
            f"A multivariate forecaster ({forecaster}) is recommended for "
            "predicting the target using multiple correlated series as features."
        )
    elif task_type == "foundation":
        parts.append(
            f"A foundation model ({forecaster}) was selected per user preference."
        )
    elif task_type == "statistical":
        parts.append(
            f"A statistical model ({forecaster}) was selected per user preference."
        )
    else:
        parts.append(
            f"A single-series ML forecaster ({forecaster}) is recommended."
        )

    if estimator is not None:
        parts.append(f"The estimator is {estimator}.")

    if lags is not None:
        parts.append(f"Lags: {lags}.")

    if interval_method is not None:
        parts.append(f"Prediction intervals via {interval_method}.")

    if profile.exog_columns:
        parts.append(
            f"Exogenous variables detected: {profile.exog_columns}."
        )

    return " ".join(parts)
