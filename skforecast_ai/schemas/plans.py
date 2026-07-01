"""Plan schemas: forecasting configuration and overrides."""

from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

from .._display import DisplayMixin, render_plan

class CVParams(BaseModel):
    """
    LLM-produced cross-validation parameters for `TimeSeriesFold`.

    Returned as structured output from the CV configuration agent.
    All fields have defaults so the LLM only needs to specify the
    parameters it wants to override from the deterministic baseline.

    Attributes
    ----------
    initial_train_size : int, float, str
        Number of observations (int), fraction of data (float in
        (0, 1)), or date string for the initial training set.
    refit : bool, int
        Whether to refit every fold (True), never (False), or every
        n folds (int).
    fixed_train_size : bool
        If True, training size stays fixed; if False, expands.
    gap : int
        Observations between end of training and start of test.
    fold_stride : int, None
        Observations between consecutive test set starts. None means
        equal to steps.
    skip_folds : int, list of int, None
        Folds to skip. Int means keep every n-th fold; list specifies
        indexes.
    allow_incomplete_fold : bool
        Whether to allow a final fold with fewer observations than
        steps.
    reasoning : str
        Explanation of why these parameters were chosen. Shown to the
        user for transparency.
    """

    initial_train_size: int | float | str = Field(
        description=(
            "Number of observations (int), fraction of total data "
            "(float in (0,1)), or date string for the initial training set."
        ),
    )
    refit: bool | int = Field(
        default=True,
        description=(
            "Whether to refit the model every fold (True), never (False), "
            "or every n folds (int)."
        ),
    )
    fixed_train_size: bool = Field(
        default=False,
        description=(
            "If True, training window stays fixed (rolling). "
            "If False, training window expands each fold."
        ),
    )
    gap: int = Field(
        default=0,
        description="Number of observations between training end and test start.",
    )
    fold_stride: int | None = Field(
        default=None,
        description=(
            "Number of observations between consecutive test set starts. "
            "None defaults to steps (non-overlapping test sets)."
        ),
    )
    skip_folds: int | list[int] | None = Field(
        default=None,
        description=(
            "Folds to skip. Int keeps every n-th fold; list specifies "
            "fold indexes to skip."
        ),
    )
    allow_incomplete_fold: bool = Field(
        default=True,
        description="Whether to allow a final fold with fewer observations than steps.",
    )
    reasoning: str = Field(
        description=(
            "Explanation of why these parameters were chosen, referencing "
            "the user's deployment scenario."
        ),
    )


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


class ForecastPlan(DisplayMixin, BaseModel):
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
        Prediction interval quantiles as `[lower, upper]`
        (e.g. `[0.1, 0.9]`). If None, no intervals are computed.
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
    interval: list[float] | None = None
    interval_method: Literal["bootstrapping", "conformal", "native"] | None = None
    metric: str = "mean_absolute_error"
    metrics_to_compute: list[str] = Field(
        default_factory=lambda: ["mean_absolute_error", "mean_squared_error", "mean_absolute_scaled_error"]
    )
    use_exog: bool = False
    preprocessing_steps: list[PreprocessingStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explanation: str

    def __rich_console__(self, console, options):
        yield render_plan(self)
