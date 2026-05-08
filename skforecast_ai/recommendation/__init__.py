"""Recommendation engine: deterministic rule-based forecaster selection."""

from .rules import (
    _build_profile_explanation,
    build_plan_explanation,
    build_forecaster_kwargs,
    check_exog_usage,
    derive_preprocessing_steps,
    select_dropna_from_series,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_lags_and_window_features,
    select_task_type_from_forecaster,
    select_transformer_exog,
    select_transformer_series,
)

__all__ = [
    "_build_profile_explanation",
    "build_plan_explanation",
    "build_forecaster_kwargs",
    "check_exog_usage",
    "derive_preprocessing_steps",
    "select_dropna_from_series",
    "select_estimator_and_candidates",
    "select_forecaster_and_candidates",
    "select_lags_and_window_features",
    "select_task_type_from_forecaster",
    "select_transformer_exog",
    "select_transformer_series",
]
