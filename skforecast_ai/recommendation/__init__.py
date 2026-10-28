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
    check_default_folds_fit,
    check_first_window,
    count_cv_fits,
    count_cv_folds,
    count_estimator_fits,
    count_inference_windows,
    count_trainings,
    cv_as_executed,
    derive_cv_defaults,
    resolve_cv_config,
    resolve_cv_provenance,
    warn_first_window,
    warn_interval_residuals,
)
from .calendar import (
    constant_calendar_features,
    drop_colliding_calendar_features,
    select_calendar_encoding,
    select_calendar_features,
)
from .estimator_choice import (
    estimator_change,
    recommended_estimator,
)
from .explanation import (
    _build_profile_explanation,
    build_foundation_explanation,
    build_metric_override_explanation,
    build_estimator_explanation,
    build_plan_explanation,
)
from .forecaster_selection import (
    estimator_n_observations,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_task_type_from_forecaster,
)
from .metric_selection import (
    check_metric_domain,
    describe_series_near_zero,
    select_metric,
    series_near_zero,
)
from .missing_values import select_nan_tolerant_estimator
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
    "build_estimator_explanation",
    "build_foundation_explanation",
    "build_metric_override_explanation",
    "build_plan_explanation",
    "build_forecaster_kwargs",
    "check_default_folds_fit",
    "check_exog_usage",
    "check_first_window",
    "check_metric_domain",
    "compute_series_pacf",
    "count_cv_fits",
    "count_cv_folds",
    "count_estimator_fits",
    "count_inference_windows",
    "count_trainings",
    "cv_as_executed",
    "derive_cv_defaults",
    "derive_preprocessing_steps",
    "describe_series_near_zero",
    "estimator_change",
    "estimator_n_observations",
    "constant_calendar_features",
    "drop_colliding_calendar_features",
    "finalize_lags",
    "recommended_estimator",
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
    "select_nan_tolerant_estimator",
    "select_task_type_from_forecaster",
    "select_transformer_exog",
    "select_transformer_series",
    "select_window_features",
    "series_near_zero",
    "warn_first_window",
    "warn_interval_residuals",
]
