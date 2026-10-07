################################################################################
#                              MCP server models                               #
#                                                                              #
# What the tools of the MCP server take and return                             #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import sys
from typing import Annotated, Any, Literal, get_args
from pydantic import BaseModel, ConfigDict, Field, with_config
from skforecast.foundation import list_adapters

if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict
from .._constants import (
    ALLOWED_METRICS,
    DEFAULT_FOUNDATION_MODEL_ID,
    SUPPORTED_ESTIMATORS,
    SUPPORTED_TRANSFORMERS,
    WindowStat,
)
from .._validation import _CALENDAR_FEATURES

ObjectKind = Literal["profile", "plan", "cv", "backtest", "comparison", "forecast"]
"""Kinds of the objects the server registers, the first part of their id."""

ForecasterName = Literal[
    "ForecasterRecursive",
    "ForecasterDirect",
    "ForecasterRecursiveMultiSeries",
    "ForecasterDirectMultiVariate",
    "ForecasterStats",
    "ForecasterFoundation",
    "ForecasterEquivalentDate",
]
"""Forecasters a plan can name (the keys of `FORECASTER_TASK_TYPES`)."""

# Descriptions of the arguments shared by `plan`, `refine_plan` and the
# candidates of `compare`, written for the agent: the schema of a tool is
# all it reads about an argument. The valid values come from the constants
# of the core and from skforecast, so they never go out of date.
FORECASTER_DESCRIPTION = (
    "skforecast forecaster class: ForecasterRecursive or ForecasterDirect "
    "(one series, machine learning), ForecasterRecursiveMultiSeries (several "
    "series), ForecasterDirectMultiVariate (one series predicted from "
    "several), ForecasterStats (Auto-ARIMA), ForecasterFoundation "
    "(pre-trained foundation model, no training) or ForecasterEquivalentDate "
    "(seasonal naive baseline)."
)
ESTIMATOR_DESCRIPTION = (
    f"Estimator: one of {sorted(SUPPORTED_ESTIMATORS)} for the machine "
    f"learning forecasters, 'Arima' for ForecasterStats, or the Hugging Face "
    f"model id of a foundation model for ForecasterFoundation (default "
    f"'{DEFAULT_FOUNDATION_MODEL_ID}'; model id prefixes: "
    f"{[p for info in list_adapters() for p in info.model_id_prefixes]}). "
    f"ForecasterEquivalentDate takes none."
)
ESTIMATOR_KWARGS_DESCRIPTION = (
    "Keyword arguments of the estimator, e.g. {'n_estimators': 200}. A "
    "foundation model only takes context_length, cross_learning, "
    "point_estimate, max_horizon, add_calendar_features and n_fourier_terms."
)
STEPS_DESCRIPTION = (
    "Forecast horizon: number of steps ahead to predict, from 1 to the length "
    "of the longest series (12 for a year of monthly data)."
)
INTERVAL_DESCRIPTION = (
    "Prediction interval as two quantiles [lower, upper] with 0 < lower < "
    "upper < 1, e.g. [0.1, 0.9] for 80 %. The baseline and ForecasterStats "
    "only take symmetric ones (lower + upper = 1)."
)
LAGS_DESCRIPTION = (
    "Lags: an integer n for 1..n, or a list of distinct positive integers."
)
WINDOW_FEATURES_DESCRIPTION = (
    f"Rolling features, one entry per window size: {{'stats': [...], "
    f"'window_size': n}}, with stats among {list(get_args(WindowStat))}, e.g. "
    f"[{{'stats': ['mean', 'std'], 'window_size': 7}}]."
)

USE_EXOG_DESCRIPTION = (
    "Whether to use the exogenous columns of the data: false leaves them "
    "out (forecast then takes no exog_path); true fails when the data has "
    "none or the forecaster cannot use them."
)
DIFFERENTIATION_DESCRIPTION = (
    "Order of differencing of the target before training (an integer of at "
    "least 1, usually 1 for a trend); predictions are integrated back. "
    "Machine learning forecasters only."
)
CALENDAR_FEATURES_DESCRIPTION = (
    "Calendar features generated from the dates (an empty list for none); "
    "the encoding follows the estimator. A feature whose column is already "
    "an exogenous column used by the plan is rejected. Machine learning "
    "forecasters with a datetime index only."
)
TARGET_TRANSFORMER_DESCRIPTION = (
    "Scaler of the target: 'StandardScaler', or 'none' for no scaling. "
    "Machine learning forecasters only."
)
DROPNA_DESCRIPTION = (
    "Whether to drop the training rows with missing values; false fails "
    "when the data has missing values and the estimator does not accept "
    "them. Machine learning forecasters only."
)
METRIC_DESCRIPTION = (
    "Metric, or list of metrics whose first one is the primary metric "
    "(the one that ranks); only the ones given are computed."
)

Interval = Annotated[list[float], Field(min_length=2, max_length=2)]
WindowFeatures = list[dict[str, list[str] | int]]
MetricName = Literal[ALLOWED_METRICS]
"""Regression metrics of skforecast (`ALLOWED_METRICS`)."""
Metric = MetricName | Annotated[list[MetricName], Field(min_length=1)]
CalendarFeatureName = Literal[_CALENDAR_FEATURES]
"""Calendar features of skforecast's `CalendarFeatures`."""
TargetTransformer = Literal[(*SUPPORTED_TRANSFORMERS, "none")]
"""Values of `target_transformer`."""


@with_config(ConfigDict(
    extra            = "forbid",
    strict           = True,
    title            = "RefinePlanArgs",
    json_schema_extra = {
        "description": (
            "Decisions of the plan to change. An omitted key keeps the value "
            "of the plan; every key but forecaster, estimator and steps set to "
            "null asks for the deterministic default."
        ),
    },
))
class RefinePlanArgs(TypedDict, total=False):
    """
    Overrides of the `refine_plan` tool.

    The keys of `RefinePlanOverrides` (a test checks they stay the same),
    each described for the agent, with unknown keys rejected and no type
    coercion. A key that is omitted keeps the value of the plan; a key
    passed as null asks for the deterministic default, as in
    `ForecastingAssistant.refine_plan()`.
    """

    forecaster: Annotated[ForecasterName, Field(description=FORECASTER_DESCRIPTION)]
    estimator: Annotated[str, Field(description=ESTIMATOR_DESCRIPTION)]
    estimator_kwargs: Annotated[
        dict[str, Any] | None,
        Field(description=(
            f"{ESTIMATOR_KWARGS_DESCRIPTION} Null for the defaults of the "
            f"estimator."
        )),
    ]
    steps: Annotated[int, Field(ge=1, description=STEPS_DESCRIPTION)]
    interval: Annotated[
        Interval | None,
        Field(description=f"{INTERVAL_DESCRIPTION} Null removes the interval."),
    ]
    lags: Annotated[
        int | list[int] | None,
        Field(description=(
            f"{LAGS_DESCRIPTION} Null selects them again from the partial "
            f"autocorrelation."
        )),
    ]
    window_features: Annotated[
        WindowFeatures | None,
        Field(description=(
            f"{WINDOW_FEATURES_DESCRIPTION} Null selects them again with the "
            f"deterministic rules."
        )),
    ]
    metric: Annotated[
        Metric | None,
        Field(description=(
            f"{METRIC_DESCRIPTION} Null selects them again from the data. "
            f"Omitted, a metric chosen before is kept."
        )),
    ]
    use_exog: Annotated[
        bool | None,
        Field(description=(
            f"{USE_EXOG_DESCRIPTION} Null lets the rule decide again. "
            f"Omitted, a choice made before is kept."
        )),
    ]
    differentiation: Annotated[
        Annotated[int, Field(ge=1)] | None,
        Field(description=(
            f"{DIFFERENTIATION_DESCRIPTION} Null removes it. Omitted, an "
            f"order chosen before is kept."
        )),
    ]
    calendar_features: Annotated[
        list[CalendarFeatureName] | None,
        Field(description=(
            f"{CALENDAR_FEATURES_DESCRIPTION} Null selects them again from "
            f"the frequency. Omitted, a choice made before is kept."
        )),
    ]
    target_transformer: Annotated[
        TargetTransformer | None,
        Field(description=(
            f"{TARGET_TRANSFORMER_DESCRIPTION} Null lets the rule decide "
            f"again. Omitted, a choice made before is kept."
        )),
    ]
    dropna_from_series: Annotated[
        bool | None,
        Field(description=(
            f"{DROPNA_DESCRIPTION} Null lets the rule decide again. Omitted, "
            f"a choice made before is kept."
        )),
    ]


@with_config(ConfigDict(
    extra            = "forbid",
    strict           = True,
    title            = "CandidateArgs",
    json_schema_extra = {
        "description": (
            "Configuration of one candidate. An omitted key keeps the "
            "recommendation of the profile."
        ),
    },
))
class CandidateArgs(TypedDict, total=False):
    """
    Configuration of a candidate of the `compare` tool.

    The keys of `CandidateConfig` (a test checks they stay the same), each
    described for the agent, with unknown keys rejected and no type
    coercion. An omitted key keeps the recommendation of the profile.
    """

    forecaster: Annotated[ForecasterName, Field(description=FORECASTER_DESCRIPTION)]
    estimator: Annotated[str, Field(description=ESTIMATOR_DESCRIPTION)]
    estimator_kwargs: Annotated[
        dict[str, Any] | None,
        Field(description=ESTIMATOR_KWARGS_DESCRIPTION),
    ]
    lags: Annotated[
        int | list[int] | None,
        Field(description=(
            f"{LAGS_DESCRIPTION} Null selects them from the partial "
            f"autocorrelation."
        )),
    ]
    window_features: Annotated[
        WindowFeatures | None,
        Field(description=(
            f"{WINDOW_FEATURES_DESCRIPTION} Null selects them with the "
            f"deterministic rules."
        )),
    ]
    use_exog: Annotated[
        bool | None,
        Field(description=(
            f"{USE_EXOG_DESCRIPTION} Null uses them whenever the forecaster "
            f"can."
        )),
    ]
    differentiation: Annotated[
        Annotated[int, Field(ge=1)] | None,
        Field(description=(
            f"{DIFFERENTIATION_DESCRIPTION} The candidate runs on a copy of "
            f"the strategy with this order."
        )),
    ]
    calendar_features: Annotated[
        list[CalendarFeatureName] | None,
        Field(description=(
            f"{CALENDAR_FEATURES_DESCRIPTION} Null selects them from the "
            f"frequency."
        )),
    ]
    target_transformer: Annotated[
        TargetTransformer | None,
        Field(description=f"{TARGET_TRANSFORMER_DESCRIPTION} Null for the rule."),
    ]
    dropna_from_series: Annotated[
        bool | None,
        Field(description=f"{DROPNA_DESCRIPTION} Null for the rule."),
    ]


class CandidateArg(BaseModel):
    """
    A candidate of the `compare` tool.

    Attributes
    ----------
    name : str
        Name of the candidate, unique, that labels its row of the
        leaderboard.
    config : dict
        Its configuration: the keys of `CandidateConfig`, as in
        `ForecastingAssistant.compare()`.
    """

    model_config = ConfigDict(
        extra             = "forbid",
        strict            = True,
        json_schema_extra = {
            "description": "A configuration to compare, with a unique name.",
        },
    )

    name: str = Field(description=(
        "Unique name of the candidate, which labels its row of the "
        "leaderboard. 'Baseline (seasonal naive)' and 'Baseline (naive)' are "
        "reserved for the baseline."
    ))
    config: CandidateArgs = Field(
        default_factory = dict,
        description     = "Its configuration; empty for the recommendation.",
    )


class ToolNotice(BaseModel):
    """
    A warning emitted while a tool call ran.

    Attributes
    ----------
    source : str
        Where the warning comes from: `'data'` (reading or profiling the
        data), `'plan'` (a warning the plan carries in `plan.warnings`, or
        the model a plan uses) or `'runtime'` (any other warning of the
        call).
    category : str
        Class name of the warning (e.g. `'LongTrainingWarning'`), or the
        name of a notice of the server: `'ModelDownloadNotice'` (a
        foundation model will download its weights; it carries the license),
        `'ModelLicenseNotice'` (the license of a foundation model, when no
        download is announced), `'MetricReferenceNotice'` (what MASE and
        RMSSE are scaled by) and `'CompareCostNotice'` (a `compare` that
        costs more than the plan).
    message : str
        Text of the warning, without the suggestion of skforecast on how to
        silence it, cut to 1,000 characters.
    count : int
        Number of times the call emitted it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["data", "plan", "runtime"]
    category: str
    message: str
    count: int = Field(ge=1)


class ToolResult(BaseModel):
    """
    Envelope returned by the tools that create an object, and by
    `describe_object`.

    Attributes
    ----------
    id : str
        Id of the object, to pass to the tools that take it.
    kind : str
        Kind of the object: `'profile'`, `'plan'`, `'cv'`, `'backtest'`,
        `'comparison'` or `'forecast'`.
    links : dict
        Ids of related objects: those it was built from (`profile_id`,
        `plan_id`, `cv_id`, and `parent_plan_id` for a refined plan), the
        plan of the winner of a comparison (`best_plan_id`), and the
        comparison a winning plan comes from (`comparison_id`).
    summary : str
        Plain-text description of the object (`describe()` of the core),
        cut to 20,000 characters.
    summary_truncated : bool
        Whether `summary` was cut; the full text is then in
        `files['summary']`.
    notices : list of ToolNotice
        Warnings the call emitted, the first 20 distinct ones. Deprecation
        warnings go to the log of the server instead, and the failures of
        the candidates of a comparison are in its result.
    notices_omitted : int
        Number of distinct warnings left out of `notices`.
    files : dict
        Absolute paths of the files written for the object, by role:
        `predictions` and `metrics` (CSV with the index) of a backtest or a
        forecast, `leaderboard`, `best_predictions` and `best_metrics` of a
        comparison, and `summary` when the summary was cut.
    values_included : bool
        Always False: the response holds no rows of the data or of the
        predictions. The summary carries statistics of the predictions, the
        metrics and the leaderboard of a comparison; the rows are in
        `files`.
    cost : dict, None
        Cost of a cross-validation strategy, a backtest or a comparison:
        `n_folds`, `n_fits` (trainings of the forecaster in the shared
        strategy), `estimator_fits` (fits of an estimator, which a direct
        forecaster multiplies by `steps`) and `inference_windows` (the
        cost of a foundation model, never trained: one forecast per series
        and fold; 0 for the other forecasters); for a comparison, the last
        two are sums over its candidates. A cross-validation strategy also
        has `compare_estimator_fits` and `compare_inference_windows`, those
        of a comparison without candidates with it. None for the other
        kinds.
    changeable : list of str
        Arguments of `refine_plan` (for a plan) or of `create_cv` (for a
        cross-validation strategy) that build a variant of the object.
        Empty for the other kinds.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: ObjectKind
    links: dict[str, str] = Field(default_factory=dict)
    summary: str
    summary_truncated: bool = False
    notices: list[ToolNotice] = Field(default_factory=list)
    notices_omitted: int = 0
    files: dict[str, str] = Field(default_factory=dict)
    values_included: Literal[False] = False
    cost: dict[str, int] | None = None
    changeable: list[str] = Field(default_factory=list)


class CodeResult(BaseModel):
    """
    Script of an object, returned by the `get_code` tool.

    Attributes
    ----------
    id : str
        Id of the object.
    kind : str
        Kind of the object.
    candidate : str, None
        Candidate of a comparison whose script it is.
    code : str
        Python code, cut to 20,000 characters.
    code_truncated : bool
        Whether `code` was cut; the full code is then in `files['code']`.
    requirements : list of str
        Packages to install to run the script outside the server: those of
        the modules it imports and the backend of its foundation model,
        each with the version installed where the server runs
        (`'skforecast==0.26.0'`).
    files : dict
        Absolute path of the file with the full code, when it was cut.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: ObjectKind
    candidate: str | None = None
    code: str
    code_truncated: bool = False
    requirements: list[str] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)


class FailureResult(BaseModel):
    """
    Full description of a failure, returned by the `get_failure` tool.

    Attributes
    ----------
    id : str
        Id of the failure, or of the comparison whose candidate failed.
    candidate : str, None
        Candidate of the comparison that failed.
    text : str
        Error, line and statement that failed, traceback and code that ran,
        cut to 20,000 characters. Like the messages of the errors, it can
        quote values of the data. The code that ran reads the data in memory,
        so it does not name the path of the data file.
    text_truncated : bool
        Whether `text` was cut; the full text is then in `files['failure']`.
    files : dict
        Absolute path of the file with the full text, when it was cut.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    candidate: str | None = None
    text: str
    text_truncated: bool = False
    files: dict[str, str] = Field(default_factory=dict)


class ObjectInfo(BaseModel):
    """
    An object registered in the server, as listed by `list_objects`.

    Attributes
    ----------
    id : str
        Id of the object.
    kind : str
        Kind of the object.
    links : dict
        Ids of the objects it was built from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: ObjectKind
    links: dict[str, str] = Field(default_factory=dict)


class ObjectList(BaseModel):
    """
    Objects registered in the server, returned by `list_objects`.

    Attributes
    ----------
    objects : list of ObjectInfo
        Registered objects, most recently used first.
    max_objects : int
        Most objects the server keeps; the least recently used ones are
        removed beyond it.
    max_memory_mb : int
        Memory, in MB, the objects may take; the least recently used ones
        are removed beyond it.
    removed : int
        Number of objects removed so far to stay within those limits. A
        tool that receives the id of a removed object says so.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    objects: list[ObjectInfo]
    max_objects: int
    max_memory_mb: int
    removed: int = 0
