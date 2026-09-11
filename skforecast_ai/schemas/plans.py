################################################################################
#                               Plans schemas                                  #
#                                                                              #
# Plan schemas: forecasting configuration and overrides                        #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import sys
from typing import Annotated, Any, ClassVar, Literal
from pydantic import BaseModel, Field, field_validator

if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict
from .._constants import WindowStat
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
        (0, 1)), or ISO date string marking the end of the initial
        training set (only when the dataset has a datetime index).
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
            "Number of observations (int), fraction of the data (float in "
            "(0, 1)), or, only when the dataset context lists a date range, "
            "an ISO date string ('YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS') "
            "strictly inside that range marking the end of the initial "
            "training set."
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
        ge=0,
        description="Number of observations between training end and test start.",
    )
    fold_stride: int | None = Field(
        default=None,
        ge=1,
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
        Whether skforecast will fail without this step. Blocking steps
        are emitted into the generated script; non-blocking steps are
        informational and never emitted.
    """

    action: str
    reason: str
    code_snippet: str
    blocking: bool = True


class WindowFeature(BaseModel):
    """
    A single rolling-window feature specification for a forecaster.

    Attributes
    ----------
    stats : list of str
        Rolling statistics to compute (e.g. `['mean', 'std']`). Each value
        must be one of the statistics supported by skforecast's
        `RollingFeatures`: `'mean'`, `'std'`, `'min'`, `'max'`, `'sum'`,
        `'median'`, `'ratio_min_max'`, `'coef_variation'`, `'ewm'`.
    window_size : int
        Rolling window length in observations, applied to every statistic
        in `stats`. Must be a positive scalar int (strictly typed, so a
        float or bool is rejected); to combine several window sizes, use
        one `WindowFeature` per size.
    """
    stats: list[WindowStat] = Field(
        description=(
            "Rolling statistics to compute. Each value must be one of: "
            "'mean', 'std', 'min', 'max', 'sum', 'median', 'ratio_min_max', "
            "'coef_variation', 'ewm'."
        ),
    )
    window_size: int = Field(
        gt=0,
        strict=True,
        description=(
            "Rolling window length in observations, e.g. 7. Must be a "
            "positive integer. Scalar only: it is applied to every statistic "
            "in `stats`. Use one entry per window size to combine several "
            "sizes."
        ),
    )


class PlanOverrides(BaseModel):
    """
    LLM-produced overrides for a forecasting plan.

    The field constraints mirror `_validate_lags` and
    `_validate_window_features`, the checks `plan()` applies to explicit
    overrides, so an invalid suggestion fails at the schema boundary and
    pydantic-ai sends the error back to the model before the refinement
    loop sees it.

    Attributes
    ----------
    lags : list of int, int, default None
        Overridden lag indices (non-empty list of unique positive ints) or
        lag count (positive int meaning lags `1..n`).
    window_features : list of WindowFeature, default None
        Overridden window features configurations. The same statistic
        cannot be paired with the same window size in two entries.
    reasoning : str
        Explanation of why the LLM chose these features based on the
        user's domain knowledge prompt.
    """
    lags: (
        Annotated[list[Annotated[int, Field(ge=1)]], Field(min_length=1)]
        | Annotated[int, Field(ge=1)]
        | None
    ) = Field(
        default=None,
        description=(
            "The lag indices to use for the forecaster: a non-empty list of "
            "unique positive integers, e.g. [1, 2, 3, 7, 14], or a single "
            "positive integer n for the consecutive lags 1..n."
        ),
    )
    window_features: list[WindowFeature] | None = Field(
        default=None,
        description=(
            "The window features configurations to use. E.g. [{'stats': "
            "['mean', 'std'], 'window_size': 7}]. Do not repeat the same "
            "statistic with the same window size in two entries."
        ),
    )
    reasoning: str = Field(
        description="Explanation of why these specific features (lags and window features) were chosen based on the user's prompt and time series context.",
    )

    @field_validator("lags", mode="before")
    @classmethod
    def _check_lags(cls, value: Any) -> Any:
        """
        Apply `_validate_lags` before pydantic's coercion, so a boolean or a
        float is rejected instead of being turned into an int.
        """
        # Deferred import: `_utils` imports the schemas package.
        from .._utils import _validate_lags

        _validate_lags(value)
        return value

    @field_validator("window_features", mode="after")
    @classmethod
    def _check_window_features(
        cls, value: list[WindowFeature] | None
    ) -> list[WindowFeature] | None:
        """
        Reject entries that pair the same statistic with the same window
        size, which `RollingFeatures` refuses once the entries are flattened.
        """
        # Deferred import: `_utils` imports the schemas package.
        from .._utils import _validate_window_features

        if value is not None:
            _validate_window_features([wf.model_dump() for wf in value])
        return value


class RefinePlanOverrides(TypedDict, total=False):
    """
    Keyword overrides accepted by `ForecastingAssistant.refine_plan()`.

    Every key is optional, and what matters is whether a key is present:
    an omitted key keeps the value of the plan being refined, while a key
    passed as None asks for the deterministic default. The dictionary is
    a typing aid (editors autocomplete the keys and type checkers reject
    unknown ones); `refine_plan()` validates the keys at run time as well.

    Attributes
    ----------
    forecaster : str
        Forecaster class name, e.g. `'ForecasterDirect'`.
    estimator : str
        Estimator class name, e.g. `'Ridge'`.
    estimator_kwargs : dict, None
        Keyword arguments for the estimator constructor. None resets them
        to the built-in defaults.
    steps : int
        Forecast horizon.
    interval : list of float, None
        Prediction interval quantiles as `[lower, upper]`. None removes
        the prediction intervals.
    lags : int, list of int, None
        Lag configuration: a positive int (consecutive lags `1..n`) or a
        non-empty list of unique positive ints. None re-runs the
        PACF-based selection.
    window_features : list of dict, None
        Rolling window features, one dict with `'stats'` and a positive
        scalar `'window_size'` per window size; the same statistic cannot
        repeat the same window size across entries. None re-runs the
        deterministic selection.
    """

    forecaster: str
    estimator: str
    estimator_kwargs: dict[str, Any] | None
    steps: int
    interval: list[float] | None
    lags: int | list[int] | None
    window_features: list[dict[str, list[str] | int]] | None


class CandidateConfig(TypedDict, total=False):
    """
    Configuration of one candidate in `ForecastingAssistant.compare()`.

    The keys mirror the overrides `plan()` accepts for a candidate. Every
    key is optional; an omitted key keeps the profile recommendation. The
    dictionary is a typing aid; `compare()` validates the keys at run time
    as well.

    Attributes
    ----------
    forecaster : str
        Forecaster class name, e.g. `'ForecasterRecursive'`.
    estimator : str
        Estimator class name, e.g. `'LGBMRegressor'`.
    estimator_kwargs : dict, None
        Keyword arguments for the estimator constructor.
    lags : int, list of int, None
        Lag configuration: a positive int (consecutive lags `1..n`) or a
        non-empty list of unique positive ints. None uses the PACF-based
        selection.
    window_features : list of dict, None
        Rolling window features, one dict with `'stats'` and a positive
        scalar `'window_size'` per window size; the same statistic cannot
        repeat the same window size across entries.
    """

    forecaster: str
    estimator: str
    estimator_kwargs: dict[str, Any] | None
    lags: int | list[int] | None
    window_features: list[dict[str, list[str] | int]] | None


# Keys validated at run time, taken from the typed dictionaries so the two
# never drift apart.
REFINE_PLAN_OVERRIDE_KEYS: frozenset[str] = frozenset(RefinePlanOverrides.__annotations__)
CANDIDATE_CONFIG_KEYS: frozenset[str] = frozenset(CandidateConfig.__annotations__)


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
        Name of the scikit-learn compatible estimator. For `'foundation'`
        plans this is always `'Chronos-2'`, the only foundation backend
        wired into skforecast-ai.
    estimator_kwargs : dict, default {}
        Keyword arguments for the estimator constructor (e.g.
        `n_estimators`, `learning_rate`). Merged on top of built-in
        defaults (`random_state`, silencing flags). For `'foundation'`
        plans, use `model_id` to load a backend other than
        `autogluon/chronos-2-small`.
    steps : int
        Number of steps ahead to predict. Must be greater than 0.
    frequency : str, default None
        Pandas frequency string for the series.
    end_train : str, default None
        Last datetime (inclusive) of the training set as a string
        (e.g. `'2005-03-01'`). When set, the generated code runs in
        evaluation mode: it splits the data at this boundary, trains on
        the training portion, predicts the test portion and computes
        metrics. When None, the generated code runs in prediction mode:
        it trains on all available data and forecasts the future (no
        metrics, since there is no ground truth to compare against).
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
    llm_refined_fields : list
        Names of the fields (`'lags'`, `'window_features'`) whose values
        were suggested by the LLM during `refine_plan()`. Empty for
        deterministic plans and for fields the user overrode explicitly.
        Used to flag LLM-sourced values when the plan is displayed.
    explanation : str
        Explanation of the plan-level decisions.
    """

    _explanation_title: ClassVar[str] = "Plan Explanation"

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
    end_train: str | None = None
    interval: list[float] | None = None
    interval_method: Literal["bootstrapping", "conformal", "native"] | None = None
    metric: str = "mean_absolute_error"
    metrics_to_compute: list[str] = Field(
        default_factory=lambda: ["mean_absolute_error", "mean_squared_error", "mean_absolute_scaled_error"]
    )
    use_exog: bool = False
    preprocessing_steps: list[PreprocessingStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    llm_refined_fields: list[str] = Field(default_factory=list)
    explanation: str

    def _rich_body(self, console, options):
        yield render_plan(self)
