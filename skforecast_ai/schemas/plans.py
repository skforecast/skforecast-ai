"""Plan schemas: forecasting configuration and overrides."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PreprocessingStep(BaseModel):
    """
    A preprocessing action required before forecasting.

    Attributes
    ----------
    action : str
        Identifier for the preprocessing operation (e.g.
        `'sort_index'`, `'asfreq'`, `'reshape_long_to_dict'`).
    reason : str
        Human-readable explanation of why this step is needed.
    code_snippet : str
        Python code template that implements this step. May contain
        format placeholders (e.g. `{frequency}`, `{date_column}`).
    blocking : bool, default True
        Whether skforecast will fail without this step. Non-blocking
        steps are recommended but optional.
    """

    action: str
    reason: str
    code_snippet: str
    blocking: bool = True


class ForecastPlan(BaseModel):
    """
    Detailed forecasting plan produced from a `ForecastingProfile`.

    Carries every concrete decision needed to fit, evaluate and predict:
    lag structure, prediction intervals, NaN handling, exogenous usage
    and preprocessing steps.

    Attributes
    ----------
    task_type : str
        Forecasting task category (mirrored from the source
        `ForecastingProfile`). One of `'single_series'`,
        `'multi_series'`, `'multivariate'`, `'statistical'`,
        `'foundation'`.
    forecaster : str
        Name of the skforecast forecaster class.
    forecaster_kwargs : dict, default {}
        Keyword arguments for the forecaster constructor (e.g. `lags`,
        `steps`, `encoding`, `dropna_from_series`). Can be unpacked
        directly into the constructor alongside `estimator`.
    estimator : str, default None
        Name of the scikit-learn compatible estimator.
    estimator_kwargs : dict, default {}
        Keyword arguments for the estimator constructor (e.g.
        `n_estimators`, `learning_rate`). Merged on top of built-in
        defaults (`random_state`, silencing flags).
    steps : int
        Number of steps ahead to predict. Must be greater than 0.
    frequency : str, default None
        Pandas frequency string for the series.
    interval : list, default None
        Prediction interval percentiles as `[lower, upper]`
        (e.g. `[10, 90]`). If None, no intervals are computed.
    interval_method : str, default None
        Method for prediction intervals. One of `'bootstrapping'`,
        `'conformal'`, `'native'`.
    metric : str, default 'mean_absolute_error'
        Recommended primary evaluation metric (string name matching
        sklearn/skforecast naming conventions).
    metrics_to_compute : list, default ['mean_absolute_error', 'mean_squared_error', 'mean_absolute_scaled_error']
        Full list of metrics to evaluate in generated code.
    use_exog : bool, default False
        Whether to include exogenous variables.
    preprocessing_steps : list
        Ordered list of preprocessing steps required before forecasting.
    warnings : list
        Human-readable warnings about the plan.
    explanation : str
        Explanation of the plan-level decisions.
    """

    task_type: Literal[
        "single_series",
        "multi_series",
        "multivariate",
        "statistical",
        "foundation",
    ]
    forecaster: str
    forecaster_kwargs: dict[str, Any] = Field(default_factory=dict)
    estimator: str | None = None
    estimator_kwargs: dict[str, Any] = Field(default_factory=dict)
    steps: int = Field(gt=0)
    frequency: str | None = None
    interval: list[int] | None = None
    interval_method: Literal["bootstrapping", "conformal", "native"] | None = None
    metric: str = "mean_absolute_error"
    metrics_to_compute: list[str] = Field(
        default_factory=lambda: ["mean_absolute_error", "mean_squared_error", "mean_absolute_scaled_error"]
    )
    use_exog: bool = False
    preprocessing_steps: list[PreprocessingStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explanation: str


class PlanOverrides(BaseModel):
    """
    Structured overrides extracted from natural language by the LLM.

    Used by `refine_plan()` (future) to re-derive a forecast plan
    with user-requested changes applied on top of the original profile.

    Attributes
    ----------
    forecaster : str, default None
        Override for the forecaster class name.
    estimator : str, default None
        Override for the estimator class name.
    steps : int, default None
        Override for the forecast horizon.
    lags : list, default None
        Override for the lag structure.
    interval : list, default None
        Override for prediction interval percentiles (e.g. [10, 90]).
    """

    forecaster: str | None = None
    estimator: str | None = None
    steps: int | None = None
    lags: list[int] | None = None
    interval: list[int] | None = None
