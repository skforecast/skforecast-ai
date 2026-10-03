################################################################################
#                               Plans schemas                                  #
#                                                                              #
# Plan schemas: forecasting configuration and overrides                        #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import sys
from typing import Annotated, Any, ClassVar, Literal, get_args
import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator

if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict
from .._constants import WindowStat
from .._foundation import validate_foundation_plan
from .._validation import (
    _validate_lags,
    _validate_window_features,
    validate_estimator,
    validate_forecaster,
    validate_forecaster_kwargs,
    validate_interval,
    validate_metrics,
    validate_preprocessing_step,
    validate_steps,
)
from .._display import DisplayMixin, render_plan
from ..exceptions import InvalidInputError


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
        default=False,
        description=(
            "Whether to refit the model every fold (True), never (False, "
            "train once), or every n folds (int). Refitting multiplies the "
            "training cost by the number of folds."
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
        Python code template that implements this step. The snippet of a
        blocking step must be one of the templates `plan()` generates (see
        `ForecastPlan`), whose placeholders (`{series_id_column}`,
        `{date_column}`) are filled when the script is rendered.
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
        if value is not None:
            _validate_window_features([wf.model_dump() for wf in value])
        return value


def _plain(value: Any) -> Any:
    """
    Return a numpy scalar or array as the Python value it holds, also inside
    lists, tuples and dicts; any other value as it is.
    """
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_plain(item) for item in value)
    return value


OverrideName = Literal[
    "forecaster",
    "estimator",
    "estimator_kwargs",
    "lags",
    "window_features",
    "metric",
    "use_exog",
    "differentiation",
    "calendar_features",
    "target_transformer",
    "dropna_from_series",
]
"""Decisions of a plan that the user can make instead of the rules of
`plan()`, as recorded in `ForecastPlan.overridden_fields`."""

# Canonical order of the names, the order `overridden_fields` keeps.
OVERRIDE_NAMES: tuple[str, ...] = get_args(OverrideName)


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
        Estimator class name, e.g. `'Ridge'`, or the Hugging Face model ID
        of a foundation model, e.g. `'google/timesfm-3.0-pytorch'`.
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
    metric : str, list of str, None
        Metric(s) to compute, the first one being the primary metric, as
        in `plan()`. None selects them from the data again. When omitted,
        a metric chosen by the user is kept and a selected one is
        selected again.
    use_exog : bool, None
        Whether the plan uses the exogenous variables, as in `plan()`. None
        lets the rule decide again. When omitted, a choice of the user is
        kept and the rule decides otherwise.
    differentiation : int, None
        Order of differencing of the target, as in `plan()`. None removes
        it. When omitted, an order chosen by the user is kept while the
        forecaster takes one.
    calendar_features : list of str, None
        Calendar features to generate, as in `plan()`; an empty list for
        none. None selects them again from the frequency.
    target_transformer : str, None
        `'StandardScaler'` or `'none'`, as in `plan()`. None lets the rule
        decide again.
    dropna_from_series : bool, None
        Whether to drop the training rows with missing values, as in
        `plan()`. None lets the rule decide again.
    """

    forecaster: str
    estimator: str
    estimator_kwargs: dict[str, Any] | None
    steps: int
    interval: list[float] | None
    lags: int | list[int] | None
    window_features: list[dict[str, list[str] | int]] | None
    metric: str | list[str] | None
    use_exog: bool | None
    differentiation: int | None
    calendar_features: list[str] | None
    target_transformer: str | None
    dropna_from_series: bool | None


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
        Estimator class name, e.g. `'LGBMRegressor'`, or the Hugging Face
        model ID of a foundation model, e.g. `'autogluon/chronos-2-small'`.
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
    use_exog : bool, None
        Whether the candidate uses the exogenous variables, as in `plan()`.
        None uses them whenever the forecaster can.
    differentiation : int, None
        Order of differencing of the target, as in `plan()`. The candidate
        runs on a copy of the strategy with this order.
    calendar_features : list of str, None
        Calendar features to generate, as in `plan()`.
    target_transformer : str, None
        `'StandardScaler'` or `'none'`, as in `plan()`.
    dropna_from_series : bool, None
        Whether to drop the training rows with missing values, as in
        `plan()`.
    """

    forecaster: str
    estimator: str
    estimator_kwargs: dict[str, Any] | None
    lags: int | list[int] | None
    window_features: list[dict[str, list[str] | int]] | None
    use_exog: bool | None
    differentiation: int | None
    calendar_features: list[str] | None
    target_transformer: str | None
    dropna_from_series: bool | None


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
        `'foundation'`, or `'baseline'` when the plan was built for
        `ForecasterEquivalentDate`.
    forecaster : str
        Name of the skforecast forecaster class. It must be a supported
        forecaster whose task type is `task_type`.
    forecaster_kwargs : dict, default {}
        Keyword arguments for the forecaster constructor (e.g. `lags`,
        `steps`, `encoding`, `dropna_from_series`). Can be unpacked
        directly into the constructor alongside `estimator`. Only the
        arguments `plan()` builds for the forecaster, plus
        `differentiation`, are accepted, with the values the generated
        scripts support (`categorical_features` only `'auto'` or None,
        `dropna_from_series` a bool, `differentiation` an int of at least
        1).
    estimator : str, default None
        Name of the scikit-learn compatible estimator. For `'foundation'`
        plans it is the Hugging Face model ID of the foundation model
        (e.g. `'autogluon/chronos-2-small'`), and it must be a model
        supported by skforecast.
    estimator_kwargs : dict, default {}
        Keyword arguments for the estimator constructor (e.g.
        `n_estimators`, `learning_rate`). Merged on top of built-in
        defaults (`random_state`, silencing flags). For `'foundation'`
        plans they are passed to `FoundationModel` on top of the default
        `context_length` of the model, and cannot contain `model_id`.
    steps : int
        Number of steps ahead to predict: an integer of at least 1. An
        integral float (`12.0`) is stored as an int; a bool, a string or a
        non-integer raises.
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
        `'conformal'`, `'native'`. Required when `interval` is set.
    metric : str, default 'mean_absolute_error'
        Recommended primary evaluation metric (string name matching
        sklearn/skforecast naming conventions).
    metrics_to_compute : list, default ['mean_absolute_error', 'mean_squared_error', 'mean_absolute_scaled_error']
        Full list of metrics to evaluate in generated code.
    use_exog : bool, default False
        Whether to include exogenous variables.
    preprocessing_steps : list
        Ordered list of preprocessing steps required before forecasting.
        A blocking step is written into the script, so its action and
        snippet must be one of those `plan()` generates (the steps of
        0.3.1 included).
    warnings : list
        Text of the warnings that `plan()` emitted while building the plan
        (an unrecommended forecaster, estimator keyword arguments that the
        library may ignore, a baseline on a target with missing values),
        in the order they were emitted. Kept as given when the plan is
        loaded or validated.
    llm_refined_fields : list
        Names of the fields (`'lags'`, `'window_features'`) whose values
        were suggested by the LLM during `refine_plan()`. Empty for
        deterministic plans and for fields the user overrode explicitly.
        Used to flag LLM-sourced values when the plan is displayed.
    overridden_fields : list
        Names of the decisions the user made instead of the rules of
        `plan()`: the arguments passed with a value other than None among
        `forecaster`, `estimator`, `estimator_kwargs`, `lags`,
        `window_features`, `metric`, `use_exog`, `differentiation`,
        `calendar_features`, `target_transformer` and `dropna_from_series`
        (an argument passed as None asks for the rule and is not recorded).
        It holds names only; the values are those of the plan. `refine_plan()`
        keeps a name while the refined plan keeps its value. Empty for a
        plan of an earlier version.
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
        "baseline",
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
    overridden_fields: list[OverrideName] = Field(default_factory=list)
    explanation: str

    @field_validator("estimator_kwargs", mode="before")
    @classmethod
    def _plain_estimator_kwargs(cls, value: Any) -> Any:
        """
        Turn numpy values (`np.float64(0.5)`, an array) into the Python
        values they hold. They are written into the script with `repr()`,
        which gave `np.float64(0.5)` in a script that does not import
        numpy, and they cannot be saved as JSON.
        """
        if isinstance(value, dict):
            return {key: _plain(item) for key, item in value.items()}
        return value

    @field_validator("overridden_fields", mode="after")
    @classmethod
    def _order_overridden_fields(cls, value: list[str]) -> list[str]:
        """
        Keep each name once, in the canonical order of `OVERRIDE_NAMES`, so
        two plans with the same decisions compare equal.
        """
        return [name for name in OVERRIDE_NAMES if name in value]

    @field_validator("steps", mode="before")
    @classmethod
    def _check_steps(cls, value: Any) -> int:
        """
        Apply `validate_steps` before pydantic's coercion: an integral float
        (`12.0`) becomes an int, and a bool, a string or a non-integer is
        rejected instead of being coerced.
        """
        return validate_steps(value)

    @model_validator(mode="after")
    def _check_plan_inputs(self) -> ForecastPlan:
        """
        Validate the inputs that reach the generated script, so a plan built
        by hand or loaded from JSON cannot name a forecaster or an estimator
        the script cannot import (or write an arbitrary name into it), hold
        forecaster arguments or blocking preprocessing steps outside the
        closed sets the script templates accept, or carry an interval, a
        metric or a foundation model that would fail inside the script.
        """
        validate_forecaster(self.forecaster, self.task_type)
        validate_forecaster_kwargs(self.forecaster_kwargs, self.forecaster)
        for step in self.preprocessing_steps:
            validate_preprocessing_step(
                action       = step.action,
                code_snippet = step.code_snippet,
                blocking     = step.blocking,
            )
        validate_estimator(
            estimator        = self.estimator,
            estimator_kwargs = self.estimator_kwargs,
            task_type        = self.task_type,
        )
        validate_metrics([self.metric])
        validate_metrics(self.metrics_to_compute, field="metrics_to_compute")
        if self.task_type == "foundation":
            validate_foundation_plan(
                estimator        = self.estimator,
                estimator_kwargs = self.estimator_kwargs,
                interval         = self.interval,
            )
        else:
            validate_interval(
                interval   = self.interval,
                task_type  = self.task_type,
                forecaster = self.forecaster,
            )
        if self.interval is not None and self.interval_method is None:
            # Without a method the backtest took skforecast's default and
            # forecast() computed no interval, without a warning.
            raise InvalidInputError(
                "`interval` needs an `interval_method`: 'bootstrapping' for "
                "the machine learning forecasters, 'conformal' for "
                "ForecasterEquivalentDate and 'native' for ForecasterStats "
                "and ForecasterFoundation, as plan() sets it.",
                field = "interval_method",
            )
        return self

    def _rich_body(self, console, options):
        yield render_plan(self)
