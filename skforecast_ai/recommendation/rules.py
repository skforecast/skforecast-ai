"""Deterministic rule functions for the recommendation engine."""

from typing import Literal

from ..schemas import DataProfile


def select_task_type(
    profile: DataProfile,
    prefer_foundation: bool = False,
    prefer_statistical: bool = False,
) -> Literal[
    "single_series",
    "multi_series",
    "statistical",
    "foundation",
]:
    """
    Determine the forecasting task type from profile shape and user hints.

    Parameters
    ----------
    profile : DataProfile
        Profiled dataset metadata.
    prefer_foundation : bool, default False
        If `True`, override with `'foundation'` task type.
    prefer_statistical : bool, default False
        If `True`, override with `'statistical'` task type.

    Returns
    -------
    task_type : str
        One of `'single_series'`, `'multi_series'`, `'statistical'`,
        `'foundation'`.

    Notes
    -----
    Source: `skforecast_ai/skills/choosing-a-forecaster/SKILL.md` Step 1.
    """
    if prefer_foundation:
        return "foundation"
    if prefer_statistical:
        return "statistical"
    if profile.n_series > 1:
        return "multi_series"
    return "single_series"


def select_forecaster(task_type: str) -> str:
    """
    Map a task type to the recommended skforecast forecaster class name.

    Parameters
    ----------
    task_type : str
        Forecasting task category produced by `select_task_type`.

    Returns
    -------
    forecaster : str
        Name of the skforecast forecaster class.

    Notes
    -----
    Source: `skforecast_ai/skills/choosing-a-forecaster/SKILL.md` flowchart.
    """
    mapping = {
        "single_series": "ForecasterRecursive",
        "multi_series": "ForecasterRecursiveMultiSeries",
        "statistical": "ForecasterStats",
        "foundation": "ForecasterFoundation",
        "baseline": "ForecasterEquivalentDate",
        "classification": "ForecasterRecursiveClassifier",
        "multivariate": "ForecasterDirectMultiVariate",
    }
    return mapping[task_type]


def select_estimator(
    task_type: str,
    n_observations: int,
) -> str | None:
    """
    Choose an ML estimator based on task type and data size.

    Parameters
    ----------
    task_type : str
        Forecasting task category.
    n_observations : int
        Number of observations in the dataset.

    Returns
    -------
    estimator : str or None
        Name of the scikit-learn compatible estimator, or `None` for tasks
        that do not use an external estimator.

    Notes
    -----
    Source: `skforecast_ai/skills/forecasting-single-series/SKILL.md`.
    """
    if task_type in ("statistical", "foundation", "baseline"):
        return None
    if n_observations < 500:
        return "Ridge"
    return "LGBMRegressor"


def select_lags(
    n_observations: int,
) -> list[int]:
    """
    Determine a default lag structure based on dataset size.

    This is a placeholder until ACF/PACF-based lag selection is
    implemented.

    Parameters
    ----------
    n_observations : int
        Number of observations in the dataset.

    Returns
    -------
    lags : list
        Sorted list of lag indices to use as predictors.

    Notes
    -----
    Source: `skforecast_ai/skills/choosing-a-forecaster/SKILL.md`.
    """
    max_lag = max(n_observations // 3, 1)
    return list(range(1, min(8, max_lag + 1)))


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


NAN_TOLERANT_ESTIMATORS: set[str] = {
    "LGBMRegressor",
    "CatBoostRegressor",
    "XGBRegressor",
}


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
    if task_type in ("statistical", "foundation", "baseline"):
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


def build_rationale(
    task_type: str,
    forecaster: str,
    estimator: str | None,
    lags: list[int] | None,
    metric: str,
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
    metric : str
        Selected evaluation metric.
    interval_method : str or None
        Selected prediction interval method.
    profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    rationale : str
        Multi-sentence explanation of the recommendation.
    """
    parts = []

    if task_type == "multi_series":
        parts.append(
            f"The dataset contains {profile.n_series} series, so a multi-series "
            f"forecaster ({forecaster}) is recommended."
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

    parts.append(f"Metric: {metric}.")

    if interval_method is not None:
        parts.append(f"Prediction intervals via {interval_method}.")

    if profile.exog_columns:
        parts.append(
            f"Exogenous variables detected: {profile.exog_columns}."
        )

    return " ".join(parts)
