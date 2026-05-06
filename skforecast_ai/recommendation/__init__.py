"""Recommendation engine: deterministic rule-based forecaster selection."""

from .forecaster_selection import _build_profile_explanation
from .rules import (
    build_data_requirements,
    build_explanation,
    check_exog_usage,
    select_backtesting,
    select_dropna_from_series,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_interval_method,
    select_lags,
    select_metric,
    select_task_type_from_forecaster,
)

__all__ = [
    "_build_profile_explanation",
    "build_data_requirements",
    "build_explanation",
    "check_exog_usage",
    "select_backtesting",
    "select_dropna_from_series",
    "select_estimator_and_candidates",
    "select_forecaster_and_candidates",
    "select_interval_method",
    "select_lags",
    "select_metric",
    "select_task_type_from_forecaster",
]
