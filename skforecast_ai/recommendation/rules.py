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
) -> list[int]:
    """
    Determine a default lag structure based on dataset size.

    This is a placeholder until ACF/PACF-based lag selection is
    implemented. autoregressive

    Parameters
    ----------
    n_observations : int
        Number of observations in the dataset.

    Returns
    -------
    lags : list
        Sorted list of lag indices to use as predictors.
    window_features : list or None
        List of window features to use as predictors, or `None` if not applicable.

    Notes
    -----
    Source: `skforecast_ai/skills/choosing-a-forecaster/SKILL.md`.

    .. todo::
        Incorporate ``frequency`` to select seasonally-aware lags
        (e.g. 24 for hourly, 7 for daily, 12 for monthly) once the
        frequency-to-seasonal-period mapping is available in the
        profiling skill.
    """
    max_lag = max(n_observations // 3, 1)
    window_features = None
    return list(range(1, min(8, max_lag + 1))), window_features


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
