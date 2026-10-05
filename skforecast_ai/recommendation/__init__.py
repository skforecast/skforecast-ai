"""Recommendation engine: deterministic rule-based forecaster selection."""

from .autoregressive import (
    compute_series_pacf,
    finalize_lags,
    select_lags,
    select_window_features,
)
from .baseline import baseline_missing_values_note, select_baseline_config
from .backtesting import (
    build_cv,
    build_cv_explanation,
    check_first_window,
    count_cv_fits,
    count_cv_folds,
    count_estimator_fits,
    count_inference_windows,
    cv_as_executed,
    derive_cv_defaults,
    resolve_cv_config,
    resolve_cv_provenance,
    warn_first_window,
)
from .calendar import (
    constant_calendar_features,
    drop_colliding_calendar_features,
    select_calendar_encoding,
    select_calendar_features,
)
from .explanation import (
    _build_profile_explanation,
    build_foundation_explanation,
    build_metric_override_explanation,
    build_plan_explanation,
)
from .forecaster_selection import (
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_task_type_from_forecaster,
)
from .metric_selection import select_metric
from .preprocessing import (
    build_forecaster_kwargs,
    check_exog_usage,
    derive_preprocessing_steps,
    select_dropna_from_series,
    select_transformer_exog,
    select_transformer_series,
)

__all__ = [
    "_build_profile_explanation",
    "baseline_missing_values_note",
    "build_cv",
    "build_cv_explanation",
    "build_foundation_explanation",
    "build_metric_override_explanation",
    "build_plan_explanation",
    "build_forecaster_kwargs",
    "check_exog_usage",
    "check_first_window",
    "compute_series_pacf",
    "count_cv_fits",
    "count_cv_folds",
    "count_estimator_fits",
    "count_inference_windows",
    "cv_as_executed",
    "derive_cv_defaults",
    "derive_preprocessing_steps",
    "constant_calendar_features",
    "drop_colliding_calendar_features",
    "finalize_lags",
    "resolve_cv_config",
    "resolve_cv_provenance",
    "select_baseline_config",
    "select_calendar_encoding",
    "select_calendar_features",
    "select_dropna_from_series",
    "select_estimator_and_candidates",
    "select_forecaster_and_candidates",
    "select_lags",
    "select_metric",
    "select_task_type_from_forecaster",
    "select_transformer_exog",
    "select_transformer_series",
    "select_window_features",
    "warn_first_window",
]
