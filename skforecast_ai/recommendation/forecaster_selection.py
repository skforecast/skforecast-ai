"""Orchestrator: assemble a ForecastPlan from deterministic rules."""

from ..schemas import DataProfile, ForecastPlan
from .rules import (
    build_data_requirements,
    build_rationale,
    check_exog_usage,
    select_backtesting,
    select_dropna_from_series,
    select_estimator,
    select_forecaster,
    select_interval_method,
    select_lags,
    select_metric,
    select_task_type,
)


def recommend_plan(
    profile: DataProfile,
    horizon: int = 10,
    prefer_foundation: bool = False,
    prefer_statistical: bool = False,
) -> ForecastPlan:
    """
    Generate a deterministic forecasting plan from a data profile.

    Parameters
    ----------
    profile : DataProfile
        Profiled dataset metadata produced by `create_data_profile`.
    horizon : int, default 10
        Number of steps ahead to predict.
    prefer_foundation : bool, default False
        If `True`, recommend a foundation model forecaster regardless of
        data characteristics.
    prefer_statistical : bool, default False
        If `True`, recommend a statistical model forecaster regardless of
        data characteristics.

    Returns
    -------
    plan : ForecastPlan
        Structured plan with the recommended forecaster, lags, metric,
        backtesting strategy, and rationale.

    Notes
    -----
    The recommendation is fully deterministic. The LLM is not invoked by
    this function.
    """
    task_type = select_task_type(profile, prefer_foundation, prefer_statistical)
    forecaster = select_forecaster(task_type)
    estimator = select_estimator(task_type, profile.n_observations)

    if task_type in ("statistical", "foundation", "baseline"):
        lags = None
    else:
        lags = select_lags(
            profile.frequency,
            profile.inferred_seasonalities,
            profile.n_observations,
        )
    metric = select_metric(task_type)
    backtesting_strategy = select_backtesting(profile.n_observations, horizon)
    interval_method = select_interval_method(forecaster, profile.n_observations)
    dropna_from_series = select_dropna_from_series(
        estimator, profile.missing_values, task_type
    )
    use_exog = check_exog_usage(profile.exog_columns)
    data_requirements = build_data_requirements(profile)

    warnings: list[str] = []
    if horizon > profile.n_observations:
        warnings.append(
            f"Horizon ({horizon}) exceeds the number of observations "
            f"({profile.n_observations}). Results may be unreliable."
        )

    rationale = build_rationale(
        task_type, forecaster, estimator, lags, metric, interval_method, profile
    )

    return ForecastPlan(
        task_type            = task_type,
        forecaster           = forecaster,
        estimator            = estimator,
        horizon              = horizon,
        frequency            = profile.frequency,
        lags                 = lags,
        metric               = metric,
        backtesting_strategy = backtesting_strategy,
        interval_method      = interval_method,
        dropna_from_series   = dropna_from_series,
        use_exog             = use_exog,
        data_requirements    = data_requirements,
        warnings             = warnings,
        rationale            = rationale,
    )
