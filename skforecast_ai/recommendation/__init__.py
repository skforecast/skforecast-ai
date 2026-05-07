"""Recommendation engine: deterministic rule-based forecaster selection."""

from .forecaster_selection import _build_profile_explanation
from .rules import (
    build_data_requirements,
    build_explanation,
    build_forecaster_kwargs,
    check_exog_usage,
    select_backtesting,
    select_dropna_from_series,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_interval_method,
    select_autoregressive,
    select_metric,
    select_task_type_from_forecaster,
    select_transformer_exog,
    select_transformer_series,
)

__all__ = [
    "_build_profile_explanation",
    "build_data_requirements",
    "build_explanation",
    "build_forecaster_kwargs",
    "check_exog_usage",
    "select_backtesting",
    "select_dropna_from_series",
    "select_estimator_and_candidates",
    "select_forecaster_and_candidates",
    "select_interval_method",
    "select_autoregressive",
    "select_metric",
    "select_task_type_from_forecaster",
    "select_transformer_exog",
    "select_transformer_series",
]
