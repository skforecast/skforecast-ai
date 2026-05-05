"""Orchestrator: assemble a ForecastPlan from deterministic rules."""

from __future__ import annotations

import pandas as pd

from ..preparation import derive_preprocessing_steps
from ..profiling.analysis import create_analysis_context
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


def select_forecaster_type(
    profile: DataProfile,
    prefer_foundation: bool = False,
    prefer_statistical: bool = False,
) -> str:
    """
    Select the appropriate forecaster class based on data profile.

    This is the Stage 2 entry point that combines task type detection
    and forecaster mapping into a single call.

    Parameters
    ----------
    profile : DataProfile
        Profiled dataset metadata.
    prefer_foundation : bool, default False
        If `True`, recommend a foundation model forecaster.
    prefer_statistical : bool, default False
        If `True`, recommend a statistical model forecaster.

    Returns
    -------
    forecaster : str
        Name of the skforecast forecaster class (e.g.
        `'ForecasterRecursive'`, `'ForecasterRecursiveMultiSeries'`).
    """
    task_type = select_task_type(profile, prefer_foundation, prefer_statistical)
    return select_forecaster(task_type)


def recommend_plan(
    profile: DataProfile,
    steps: int = 10,
    data: pd.DataFrame | None = None,
    prefer_foundation: bool = False,
    prefer_statistical: bool = False,
) -> ForecastPlan:
    """
    Generate a deterministic forecasting plan from a data profile.

    Internally orchestrates four stages:
      1. Profile (already done — receives ``profile``)
      2. Select forecaster type
      3. Build analysis context (forecaster-specific)
      4. Assemble strategy (lags, backtesting, preprocessing steps)

    Parameters
    ----------
    profile : DataProfile
        Profiled dataset metadata produced by `create_data_profile`.
    steps : int, default 10
        Number of steps ahead to predict.
    data : pandas DataFrame, default None
        Raw input data. When provided, enables forecaster-specific
        analysis (e.g. per-series length for multi-series). When None,
        safe defaults derived from the profile are used.
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
        backtesting strategy, preprocessing steps, and rationale.

    Notes
    -----
    The recommendation is fully deterministic. The LLM is not invoked by
    this function.
    """
    # Stage 2: Select forecaster
    task_type = select_task_type(profile, prefer_foundation, prefer_statistical)
    forecaster = select_forecaster(task_type)

    # Stage 3: Forecaster-specific analysis
    context = create_analysis_context(data, profile, forecaster)

    # Stage 4: Build strategy using context
    estimator = select_estimator(task_type, context.effective_n_observations)

    if task_type in ("statistical", "foundation", "baseline"):
        lags = None
    else:
        lags = select_lags(
            context.effective_n_observations,
        )
    metric = select_metric(task_type)
    backtesting_strategy = select_backtesting(
        context.effective_n_observations, steps
    )
    interval_method = select_interval_method(
        forecaster, context.effective_n_observations
    )
    dropna_from_series = select_dropna_from_series(
        estimator, profile.missing_target, profile.missing_exog, task_type
    )
    use_exog = check_exog_usage(profile.exog_columns)
    data_requirements = build_data_requirements(profile)
    preprocessing_steps = derive_preprocessing_steps(profile, forecaster)

    warnings: list[str] = []
    if steps > context.effective_n_observations:
        warnings.append(
            f"steps ({steps}) exceeds the number of observations "
            f"({context.effective_n_observations}). Results may be unreliable."
        )

    rationale = build_rationale(
        task_type, forecaster, estimator, lags, metric, interval_method, profile
    )

    return ForecastPlan(
        task_type            = task_type,
        forecaster           = forecaster,
        estimator            = estimator,
        steps                = steps,
        frequency            = profile.frequency,
        lags                 = lags,
        metric               = metric,
        backtesting_strategy = backtesting_strategy,
        interval_method      = interval_method,
        dropna_from_series   = dropna_from_series,
        use_exog             = use_exog,
        preprocessing_steps  = preprocessing_steps,
        data_requirements    = data_requirements,
        warnings             = warnings,
        rationale            = rationale,
    )
