################################################################################
#                                 MCP server                                   #
#                                                                              #
# The deterministic workflow of ForecastingAssistant as tools for agents       #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import copy
import functools
import json
import logging
import os
import sys
import tempfile
import threading
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal, get_args, get_origin
import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from mcp.server.mcpserver.tools import Tool
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
from mcp.types import ToolAnnotations
from pydantic import ConfigDict, Field, ValidationError
from .. import __version__
from .._constants import FORECASTER_TASK_TYPES
from .._utils import load_exog, warn_long_training
from ..assistant import ForecastingAssistant
from ..exceptions import InvalidInputError, SkforecastAIError
from ..recommendation import count_estimator_fits
from ..schemas.plans import REFINE_PLAN_OVERRIDE_KEYS
from . import _inputs
from ._errors import (
    ServerError,
    argument_error_payload,
    attach_details,
    candidate_failure_text,
    failure_text,
    tool_error,
)
from ._foundation import ModelPolicy, check_allow_models
from ._inputs import AllowedDir
from ._runtime import CallControl, build_notices, notice_text, run_call
from ._store import Entry, Store, estimate_nbytes
from .models import (
    ESTIMATOR_DESCRIPTION,
    ESTIMATOR_KWARGS_DESCRIPTION,
    FORECASTER_DESCRIPTION,
    INTERVAL_DESCRIPTION,
    LAGS_DESCRIPTION,
    STEPS_DESCRIPTION,
    WINDOW_FEATURES_DESCRIPTION,
    CandidateArg,
    CodeResult,
    FailureResult,
    ForecasterName,
    Interval,
    ObjectInfo,
    ObjectKind,
    ObjectList,
    RefinePlanArgs,
    ToolNotice,
    ToolResult,
    WindowFeatures,
)

logger = logging.getLogger("skforecast_ai.mcp")

# Longest summary, code and failure a response carries; the full text goes
# to a file.
MAX_SUMMARY_CHARS = 20_000
MAX_CODE_CHARS = 20_000
MAX_FAILURE_CHARS = 20_000

# Keyword arguments of a foundation model the server accepts: the ones that
# only change how the model reads the history. The adapters of skforecast
# take others that leave the machine or the model repository (TabPFN
# `mode='client'` sends the data to a remote service, TSICL
# `checkpoint_version` names a file to download) or that take Python
# objects, which a tool cannot pass.
FOUNDATION_KWARGS = frozenset({
    "context_length",
    "cross_learning",
    "point_estimate",
    "max_horizon",
    "add_calendar_features",
    "n_fourier_terms",
})

DEFAULT_MAX_OBJECTS = 256
DEFAULT_MAX_MEMORY_MB = 1024
DEFAULT_MAX_FILE_MB = 256

# Bounds that `TimeSeriesFold` checks, so a value out of them is reported as
# an invalid argument rather than as an error of skforecast.
Count = Annotated[int, Field(ge=1)]
NonNegative = Annotated[int, Field(ge=0)]

CV_ARGUMENTS = (
    "initial_train_size",
    "fold_stride",
    "refit",
    "fixed_train_size",
    "gap",
    "skip_folds",
    "allow_incomplete_fold",
)

INSTRUCTIONS = """\
Deterministic time series forecasting with skforecast. Every decision \
(forecaster, estimator, lags, metric, cross-validation) comes from rules, \
never from a language model, and is reproducible.

Workflow: `profile` a CSV file (absolute path inside the directory the server \
may read) -> `plan` with a horizon (`steps`) -> optionally `refine_plan` -> \
`create_cv` (check its `cost`) -> `backtest` -> optionally `compare` -> \
`forecast`. Each tool returns an `id`; later tools take ids, never objects. \
Every response has a plain-text `summary` and the warnings of the call in \
`notices`; it never holds rows of data, which go to CSV files (`files`). \
`get_code` returns the script that ran, `get_failure` the traceback of a \
failure, `describe_object` the response that created an object, \
`list_objects` the ids registered now.

Errors are JSON objects with `code`, `message`, `field`, `hint` and \
`details`. Dates are ISO 8601 text ('2012-01-01'); counts are numbers.

Rules (the skforecast-ai-forecasting skill has the rest):
1. Trust: a `compare` whose winner beats the baseline > a `backtest` > a \
`forecast` with `test_size` (one window) > a `forecast` of the future (no \
error measure). Without a baseline (several series, or a target with gaps), \
judge each series by `mean_absolute_scaled_error` in the CSV of metrics \
(below 1 beats a naive forecast) and name the worst one: the summary only \
has the average. Never invent a number.
2. Cost: read `cost` of `create_cv` before running; above 50 estimator fits \
tell the user and prefer fewer folds or `refit=false`.
3. Read `notices` before reporting and tell the user about data problems \
(missing dates, rows without target) and plan warnings.
4. `compare` without `interval` uses the interval of the plan of the \
strategy; the baseline only takes symmetric ones ([0.1, 0.9]).
5. Never modify the user's data. If the CSV has a problem, tell the user; \
only with their permission write a corrected copy inside the allowed \
directory under a new name and profile it.
6. Foundation models other than the default (Chronos-2) have their own \
license and size: tell the user before choosing one.\
"""


def _accepts_text(annotation: Any) -> bool:
    """
    Whether a type annotation accepts a string (`str`, a union with `str`,
    a `Literal` of strings).
    """

    if annotation is str:
        return True
    if get_origin(annotation) is Literal:
        return any(isinstance(value, str) for value in get_args(annotation))
    if get_origin(annotation) is Annotated:
        return _accepts_text(get_args(annotation)[0])

    return any(_accepts_text(arg) for arg in get_args(annotation))


class _StrictFuncMetadata(FuncMetadata):
    """
    Argument metadata of the SDK that decodes JSON text only into a list or
    an object, and only for an argument that cannot be text.

    The SDK decodes any JSON text given to an argument that is not exactly
    `str` (some clients send lists and objects as JSON text), so `'null'`
    became None and `'["a", "b"]'` a list where text was valid, and the
    default or another layout was used without notice.
    """

    def pre_parse_json(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Decode the JSON text of the arguments that take a list or an object.
        """

        parsed = dict(data)
        fields = self.arg_model.model_fields
        for key, value in data.items():
            if (
                key not in fields
                or not isinstance(value, str)
                or _accepts_text(fields[key].annotation)
            ):
                continue
            try:
                decoded = json.loads(value)
            except (ValueError, RecursionError):
                continue
            if isinstance(decoded, (list, dict)):
                parsed[key] = decoded

        return parsed


class _StrictTool(Tool):
    """
    Tool whose arguments are checked strictly, and whose argument errors
    reach the agent as the JSON of the other errors.

    The SDK ignores unknown arguments and coerces types (`'12'` to `12`). A
    misspelled argument would then be dropped without notice, so the
    argument model rejects unknown arguments and converts no type.
    """

    @classmethod
    def build(
        cls,
        fn: Callable[..., Awaitable[Any]],
        name: str,
        description: str,
        read_only: bool = False,
    ) -> _StrictTool:
        """
        Build the tool of a function.

        Parameters
        ----------
        fn : Callable
            Async function of the tool.
        name : str
            Name of the tool.
        description : str
            Description shown to the agent.
        read_only : bool, default False
            Whether the tool only reads the objects of the server.

        Returns
        -------
        tool : _StrictTool
            The tool.
        """

        annotations = ToolAnnotations(
            read_only_hint   = read_only,
            destructive_hint = False,
            open_world_hint  = False,
        )
        tool = cls.from_function(
            fn,
            name              = name,
            description       = description,
            annotations       = annotations,
            structured_output = True,
        )
        loose = tool.fn_metadata

        class StrictArguments(loose.arg_model):
            model_config = ConfigDict(
                extra  = "forbid",
                strict = True,
                title  = loose.arg_model.__name__,
            )

        tool.fn_metadata = _StrictFuncMetadata(
            arg_model     = StrictArguments,
            output_schema = loose.output_schema,
            output_model  = loose.output_model,
            wrap_output   = loose.wrap_output,
        )
        tool.parameters = StrictArguments.model_json_schema(by_alias=True)

        return tool

    async def run(
        self,
        arguments: dict[str, Any],
        context: Any,
        convert_result: bool = False,
    ) -> Any:
        """
        Run the tool as the SDK does, reporting arguments that do not match
        its schema with the JSON of the other errors.
        """

        try:
            return await super().run(arguments, context, convert_result=convert_result)
        except ToolError as exc:
            # The SDK raises a ToolError caused by the ValidationError of the
            # arguments; the errors of the tool itself are caused by another
            # ToolError.
            cause = exc.__cause__
            if isinstance(exc, UnexpectedToolError) or not isinstance(
                cause, ValidationError
            ):
                raise
            payload = json.dumps(argument_error_payload(cause), ensure_ascii=True)
            raise ToolError(f"Error executing tool {self.name}: {payload}") from cause


def _report(ctx: Context | None) -> Callable[..., Awaitable[None]] | None:
    """
    The function that sends progress notifications for the request of a
    context (a no-op when the client asked for none); None without a
    context.
    """

    return None if ctx is None else ctx.report_progress


def _reported(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """
    Report every exception of a tool as a `ToolError` with the JSON of the
    error, since the SDK hides the text of any other exception.
    """

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            raise tool_error(exc) from exc

    return wrapper


@dataclass
class _ServerState:
    """
    What the tools of one server share.

    Attributes
    ----------
    allowed : AllowedDir
        Directory the data must be in.
    output_dir : Path
        Directory of the files the server writes.
    store : Store
        Registered objects.
    assistant : ForecastingAssistant
        Assistant without LLM that runs every call.
    failures : OrderedDict
        Failures of runs by id: their text cut to `MAX_FAILURE_CHARS` and the
        file with the full text, if any. `get_failure` returns them.
    failures_lock : threading.Lock
        Guards `failures`.
    models : ModelPolicy
        Foundation models the server runs, and those whose download was
        announced.
    max_file_bytes : int
        Largest CSV file the server reads, in bytes; 0 for no limit.
    """

    allowed: AllowedDir
    output_dir: Path
    store: Store
    assistant: ForecastingAssistant
    models: ModelPolicy = field(default_factory=ModelPolicy)
    max_file_bytes: int = DEFAULT_MAX_FILE_MB * 1024 * 1024
    failures: OrderedDict[str, tuple[str, str | None]] = field(
        default_factory=OrderedDict
    )
    failures_lock: threading.Lock = field(default_factory=threading.Lock)

    def add_failure(self, text: str) -> str:
        """
        Keep a failure and return its id: its text cut to
        `MAX_FAILURE_CHARS`, with the full text in a file when it is longer.
        Only the most recent ones are kept, as many as the objects of the
        store.

        Parameters
        ----------
        text : str
            Full description of the failure.

        Returns
        -------
        failure_id : str
            `'failure-<sequence>-<token>'`.
        """

        failure_id = self.store.new_id("failure")
        kept = self.long_text(f"{failure_id}-failure.txt", text, MAX_FAILURE_CHARS)
        with self.failures_lock:
            self.failures[failure_id] = kept
            while len(self.failures) > self.store.max_objects:
                self.failures.popitem(last=False)

        return failure_id

    def long_text(self, name: str, text: str, max_chars: int) -> tuple[str, str | None]:
        """
        Cut a text to `max_chars` characters, writing the full text to a
        file of the output directory when it is longer.

        Parameters
        ----------
        name : str
            File name, built from an id.
        text : str
            Full text.
        max_chars : int
            Most characters kept.

        Returns
        -------
        text : str
            The text, cut.
        path : str, None
            Path of the file with the full text, or None when it was not cut.
        """

        if len(text) <= max_chars:
            return text, None

        return text[:max_chars], self.write_text(name, text)

    def write_frame(self, object_id: str, role: str, frame: Any) -> dict[str, str]:
        """
        Write a DataFrame to a CSV file of the output directory, with its
        index.

        Parameters
        ----------
        object_id : str
            Id of the object it belongs to.
        role : str
            What it holds (`'predictions'`, `'metrics'`, `'leaderboard'`),
            the key of the path in `files`.
        frame : pandas DataFrame, None
            Data to write. None writes nothing.

        Returns
        -------
        files : dict
            `{role: path}`, or empty when `frame` is None.
        """

        if frame is None:
            return {}
        path = self.output_dir / f"{object_id}-{role.replace('_', '-')}.csv"
        frame.to_csv(path)

        return {role: str(path)}

    def write_text(self, name: str, text: str) -> str:
        """
        Write a file in the output directory and return its absolute path.

        Parameters
        ----------
        name : str
            File name, built from an id (letters, digits and hyphens).
        text : str
            Content.

        Returns
        -------
        path : str
            Absolute path of the file.
        """

        path = self.output_dir / name
        path.write_text(text, encoding="utf-8")

        return str(path)

    def code_file(self, object_id: str, code: str) -> str | None:
        """
        Write the code of an object to a file when it is longer than
        `MAX_CODE_CHARS`, once, when the object is created.

        Parameters
        ----------
        object_id : str
            Id of the object.
        code : str
            Its code.

        Returns
        -------
        path : str, None
            Absolute path of the file, or None when the code fits in a
            response.
        """

        if len(code) <= MAX_CODE_CHARS:
            return None

        return self.write_text(f"{object_id}-code.py", code)

    def summary(self, object_id: str, text: str) -> tuple[str, bool, dict[str, str]]:
        """
        Cut a summary to `MAX_SUMMARY_CHARS`, writing the full text to a file
        when it is longer.

        Parameters
        ----------
        object_id : str
            Id of the object described.
        text : str
            Full summary.

        Returns
        -------
        summary : str
            Summary for the response.
        truncated : bool
            Whether it was cut.
        files : dict
            `{'summary': path}` when it was cut, else empty.
        """

        if len(text) <= MAX_SUMMARY_CHARS:
            return text, False, {}
        path = self.write_text(f"{object_id}-summary.txt", text)

        return text[:MAX_SUMMARY_CHARS], True, {"summary": path}


@dataclass(frozen=True)
class _Described:
    """
    A result with the code that `_finish_run` writes: a comparison has no
    code of its own, its script is the one of the winner.
    """

    result: Any
    code: str

    def describe(self) -> str:
        """
        Describe the wrapped result.
        """

        return self.result.describe()


def _copy(obj: Any) -> Any:
    """
    Deep copy of a registered object, so no call of the core can change it.
    """

    return obj.model_copy(deep=True)


def _check_foundation_kwargs(
    forecaster: str | None,
    estimator_kwargs: dict | None,
    argument: str,
) -> None:
    """
    Reject keyword arguments of a foundation model outside `FOUNDATION_KWARGS`.

    Checked where a plan or a candidate is built and again before any script
    runs, so no tool runs a foundation model with other arguments.

    Parameters
    ----------
    forecaster : str, None
        Forecaster of the plan or the candidate.
    estimator_kwargs : dict, None
        Its keyword arguments of the estimator.
    argument : str
        Argument of the tool that holds them.

    Returns
    -------
    None
    """

    if FORECASTER_TASK_TYPES.get(forecaster) != "foundation" or not estimator_kwargs:
        return
    rejected = sorted(set(estimator_kwargs) - FOUNDATION_KWARGS)
    if rejected:
        raise ServerError(
            f"The server does not pass {rejected} to a foundation model: it "
            f"accepts {sorted(FOUNDATION_KWARGS)}. Other arguments of the "
            f"adapters of skforecast can send the data to a remote service, "
            f"download files or take Python objects.",
            code  = "invalid_argument",
            field = argument,
            hint  = "Use the Python API of skforecast-ai to pass them.",
        )


def _check_steps(steps: Any, profile: Any, argument: str) -> None:
    """
    Reject a horizon longer than the longest series of the profile.

    The core accepts such a plan: a backtest of it fails late, since no
    fold fits the data, and a huge `steps` would exhaust the memory of a
    forecast. The server rejects it when the plan is built (a decision of
    the author for the server, section 17 of the design).

    Parameters
    ----------
    steps : int
        Horizon given by the agent.
    profile : ForecastingProfile
        Profile the plan is built from.
    argument : str
        Argument of the tool that holds it.

    Returns
    -------
    None
    """

    if not isinstance(steps, int) or isinstance(steps, bool):
        return
    longest = max(
        info.length for info in profile.data_profile.series_lengths.values()
    )
    if steps > longest:
        raise ServerError(
            f"`steps` is {steps}, more than the {longest} observations of the "
            f"longest series of the data. The horizon must not exceed the "
            f"history.",
            code    = "invalid_argument",
            field   = argument,
            hint    = f"Pass `steps` of at most {longest}, usually far fewer.",
            details = {"steps": steps, "longest_series": longest},
        )


def _text_notices(
    texts: Iterable[str],
    records: Iterable[Any],
    source: Literal["data", "plan"],
) -> list[ToolNotice]:
    """
    Notices for the warnings an object records as text
    (`data_profile.warnings`, `plan.warnings`) that the call did not emit
    as Python warnings, which reach the agent anyway.

    Parameters
    ----------
    texts : iterable of str
        Warnings the object records.
    records : iterable of warnings.WarningMessage
        Warnings the call emitted, which already become notices.
    source : str
        `'data'` or `'plan'`.

    Returns
    -------
    notices : list of ToolNotice
        One per text not emitted, with the category `'DataProfileWarning'`
        or `'PlanWarning'`.
    """

    emitted = {notice_text(record) for record in records}
    category = "DataProfileWarning" if source == "data" else "PlanWarning"

    return [
        ToolNotice(source=source, category=category, message=text, count=1)
        for text in dict.fromkeys(texts)
        if text not in emitted
    ]


def _cost(cv_config: dict, forecaster: str, steps: int) -> dict[str, int]:
    """
    Cost of a backtest with a cross-validation strategy and a forecaster.
    """

    n_folds = int(cv_config["n_folds"])
    n_fits = int(cv_config["n_fits"])

    return {
        "n_folds": n_folds,
        "n_fits": n_fits,
        "estimator_fits": int(
            count_estimator_fits(
                n_fits     = n_fits,
                forecaster = forecaster,
                steps      = steps,
                n_folds    = n_folds,
            )
        ),
    }


def _register(
    state: _ServerState,
    *,
    object_id: str,
    kind: ObjectKind,
    obj: Any,
    links: dict[str, str],
    summary: tuple[str, bool, dict[str, str]],
    notices: tuple[list, int],
    source: Entry | None,
    code: str | None = None,
    code_file: str | None = None,
    candidate_code_files: dict[str, str] | None = None,
    candidate_failures: dict[str, tuple[str, str | None]] | None = None,
    files: dict[str, str] | None = None,
    nbytes: int | None = None,
    cost: dict[str, int] | None = None,
    changeable: list[str] | None = None,
    data_path: str | None = None,
    data_sha256: str | None = None,
    data_warnings: tuple[str, ...] = (),
) -> ToolResult:
    """
    Register an object and return the envelope of the tool that created it.

    `source` is the entry the object was built from, whose profile and data
    the new entry records; None for a profile, which records its own.
    `files` are the files written for the object, besides the full summary.
    `nbytes` is the memory of the object when the worker thread measured it
    (large results), so the event loop does not.
    """

    text, truncated, summary_files = summary
    files = {**(files or {}), **summary_files}
    envelope = ToolResult(
        id                = object_id,
        kind              = kind,
        links             = links,
        summary           = text,
        summary_truncated = truncated,
        notices           = notices[0],
        notices_omitted   = notices[1],
        files             = files,
        cost              = cost,
        changeable        = changeable or [],
    )
    if source is not None:
        # Every entry records the profile it comes from and its data.
        profile, profile_id = source.profile, source.profile_id
        data_path = source.data_path
        data_sha256 = source.data_sha256
        data_warnings = source.data_warnings
    else:
        profile, profile_id = obj, object_id
    if nbytes is None:
        nbytes = estimate_nbytes(obj)
    state.store.add(
        Entry(
            id                   = object_id,
            kind                 = kind,
            obj                  = obj,
            envelope             = envelope,
            profile              = profile,
            profile_id           = profile_id,
            data_path            = data_path,
            data_sha256          = data_sha256,
            data_warnings        = data_warnings,
            code                 = code,
            code_file            = code_file,
            candidate_code_files = candidate_code_files or {},
            candidate_failures   = candidate_failures or {},
            nbytes               = nbytes + len(text) + len(code or ""),
        )
    )

    return envelope


def _build_tools(state: _ServerState) -> list[Tool]:
    """
    Build the tools of a server.
    """

    store = state.store
    assistant = state.assistant

    @_reported
    async def profile(
        data_path: Annotated[str, Field(description=(
            "Absolute path of a CSV file inside the directory the server may "
            "read. URLs are not accepted."
        ))],
        target: Annotated[str | list[str], Field(description=(
            "Column to forecast, or a list of columns (one series each) for "
            "wide multi-series data."
        ))],
        date_column: Annotated[str | None, Field(description=(
            "Column with the dates. When null, the first column holding dates "
            "is used."
        ))] = None,
        series_id_column: Annotated[str | None, Field(description=(
            "Column with the series ids of long multi-series data."
        ))] = None,
        ctx: Context = None,
    ) -> ToolResult:
        _inputs.check_text_argument(target, "target")
        _inputs.check_text_argument(date_column, "date_column")
        _inputs.check_text_argument(series_id_column, "series_id_column")

        def work(control: CallControl):
            path = _inputs.resolve_csv_path(data_path, state.allowed, "data_path")
            _inputs.check_file_size(path, state.max_file_bytes, "data_path")
            digest = _inputs.file_sha256(path)
            result = assistant.profile(
                data             = path,
                target           = target,
                date_column      = date_column,
                series_id_column = series_id_column,
            )
            _inputs.check_profile_names(result)
            _inputs.check_unchanged(path, digest, "data_path")
            object_id = store.new_id("profile")
            summary = state.summary(object_id, result.describe())
            control.wrote(summary[2])
            return object_id, result, path, digest, summary

        outcome = await run_call(work, report=_report(ctx), label="profile")
        object_id, result, path, digest, summary = outcome.value

        return _register(
            state,
            object_id     = object_id,
            kind          = "profile",
            obj           = result,
            links         = {},
            summary       = summary,
            notices       = build_notices(
                                outcome.warnings,
                                default_source = "data",
                                server_notices = _text_notices(
                                    result.data_profile.warnings,
                                    outcome.warnings,
                                    "data",
                                ),
                            ),
            source        = None,
            data_path     = path,
            data_sha256   = digest,
            data_warnings = tuple(notice_text(r) for r in outcome.warnings),
        )

    def _plan_envelope(
        object_id: str,
        new_plan: Any,
        source: Entry,
        outcome_warnings: list,
        links: dict[str, str],
        summary: tuple[str, bool, dict[str, str]],
        code: tuple[str, str | None],
        notices: tuple[list, int] | None = None,
        server_notices: list | None = None,
    ) -> ToolResult:
        if notices is None:
            # The plan carries its own warnings and the problems of the data
            # it was built from, also when they were not emitted this call.
            texts = [
                *_text_notices(new_plan.warnings, outcome_warnings, "plan"),
                *_text_notices(
                    source.profile.data_profile.warnings, outcome_warnings, "data"
                ),
            ]
            notices = build_notices(
                outcome_warnings,
                plan_warnings  = new_plan.warnings,
                data_warnings  = source.data_warnings,
                server_notices = [*(server_notices or ()), *texts],
            )
        return _register(
            state,
            object_id  = object_id,
            kind       = "plan",
            obj        = new_plan,
            links      = links,
            summary    = summary,
            notices    = notices,
            source     = source,
            code       = code[0],
            code_file  = code[1],
            changeable = sorted(REFINE_PLAN_OVERRIDE_KEYS),
        )

    def _check_plan_model(plan_obj: Any, argument: str) -> list[str]:
        # The foundation model of a plan must be allowed; returns it when
        # its weights are not in the local cache yet, to announce once the
        # plan is registered.
        model_id = state.models.model_of(plan_obj.forecaster, plan_obj.estimator)
        state.models.check(model_id, argument)
        return state.models.uncached([model_id])

    def _describe_plan(control: CallControl, profile_obj: Any, new_plan: Any):
        script = assistant.forecast_code(
            profile = _copy(profile_obj),
            plan    = _copy(new_plan),
        )
        object_id = store.new_id("plan")
        summary = state.summary(object_id, script.describe())
        code_file = state.code_file(object_id, script.code)
        control.wrote(summary[2], code_file)
        return object_id, summary, (script.code, code_file)

    @_reported
    async def plan(
        profile_id: Annotated[str, Field(description="Id returned by `profile`.")],
        steps: Annotated[int, Field(ge=1, description=STEPS_DESCRIPTION)],
        interval: Annotated[Interval | None, Field(description=(
            f"{INTERVAL_DESCRIPTION} Null for no interval."
        ))] = None,
        forecaster: Annotated[ForecasterName | None, Field(description=(
            f"{FORECASTER_DESCRIPTION} Null for the recommendation of the "
            f"profile."
        ))] = None,
        estimator: Annotated[str | None, Field(description=(
            f"{ESTIMATOR_DESCRIPTION} Null for the recommendation."
        ))] = None,
        estimator_kwargs: Annotated[dict[str, Any] | None, Field(description=(
            f"{ESTIMATOR_KWARGS_DESCRIPTION} Null for the defaults."
        ))] = None,
        lags: Annotated[int | list[int] | None, Field(description=(
            f"{LAGS_DESCRIPTION} Null for the selection from the partial "
            f"autocorrelation."
        ))] = None,
        window_features: Annotated[WindowFeatures | None, Field(description=(
            f"{WINDOW_FEATURES_DESCRIPTION} Null for the deterministic "
            f"selection."
        ))] = None,
        ctx: Context = None,
    ) -> ToolResult:
        profile_entry = store.get(profile_id, "profile_id", ("profile",))
        _check_steps(steps, profile_entry.obj, "steps")

        def work(control: CallControl):
            new_plan = assistant.plan(
                profile          = _copy(profile_entry.obj),
                steps            = steps,
                interval         = interval,
                forecaster       = forecaster,
                estimator        = estimator,
                estimator_kwargs = estimator_kwargs,
                lags             = lags,
                window_features  = window_features,
            )
            _check_foundation_kwargs(
                new_plan.forecaster, new_plan.estimator_kwargs, "estimator_kwargs"
            )
            uncached = _check_plan_model(new_plan, "estimator")
            return (
                new_plan, *_describe_plan(control, profile_entry.obj, new_plan),
                uncached,
            )

        outcome = await run_call(work, report=_report(ctx), label="plan")
        new_plan, object_id, summary, code, uncached = outcome.value

        return _plan_envelope(
            object_id, new_plan, profile_entry, outcome.warnings,
            {"profile_id": profile_entry.id}, summary, code,
            server_notices = state.models.announce(uncached),
        )

    @_reported
    async def refine_plan(
        plan_id: Annotated[str, Field(description="Id of the plan to refine.")],
        overrides: Annotated[RefinePlanArgs, Field(description=(
            "Values to change, e.g. {'estimator': 'Ridge', 'lags': 12}. An "
            "omitted key keeps the value of the plan; {'lags': null} selects "
            "the lags again and {'interval': null} removes the interval."
        ))],
        ctx: Context = None,
    ) -> ToolResult:
        plan_entry = store.get(plan_id, "plan_id", ("plan",))
        if "steps" in overrides:
            _check_steps(overrides["steps"], plan_entry.profile, "overrides.steps")

        def work(control: CallControl):
            try:
                new_plan = assistant.refine_plan(
                    profile = _copy(plan_entry.profile),
                    plan    = _copy(plan_entry.obj),
                    **dict(overrides),
                )
            except SkforecastAIError as exc:
                # The core names the keyword argument; the tool takes it as
                # a key of `overrides`.
                if exc.field in REFINE_PLAN_OVERRIDE_KEYS:
                    exc.field = f"overrides.{exc.field}"
                raise
            _check_foundation_kwargs(
                new_plan.forecaster,
                new_plan.estimator_kwargs,
                "overrides.estimator_kwargs",
            )
            uncached = _check_plan_model(new_plan, "overrides.estimator")
            return (
                new_plan, *_describe_plan(control, plan_entry.profile, new_plan),
                uncached,
            )

        outcome = await run_call(work, report=_report(ctx), label="refine_plan")
        new_plan, object_id, summary, code, uncached = outcome.value

        return _plan_envelope(
            object_id, new_plan, plan_entry, outcome.warnings,
            {"profile_id": plan_entry.profile_id, "parent_plan_id": plan_entry.id},
            summary, code,
            server_notices = state.models.announce(uncached),
        )

    @_reported
    async def create_cv(
        plan_id: Annotated[str, Field(description=(
            "Id of the plan to backtest (from `plan` or `refine_plan`)."
        ))],
        initial_train_size: Annotated[Count | str | None, Field(description=(
            "Observations of the first training set (a number), or the ISO "
            "8601 date that ends it ('2005-06-01'). Null for the default: "
            "70 % of the series, at least what the lags need and leaving room "
            "for two folds, written as a date when the data has dates."
        ))] = None,
        fold_stride: Annotated[int | None, Field(ge=1, description=(
            "Observations the test set advances between folds. Null for "
            "`steps` (back-to-back folds); a larger value means fewer folds."
        ))] = None,
        refit: Annotated[bool | NonNegative | None, Field(description=(
            "Whether to train again in every fold (true), never (false) or "
            "every n folds (an integer). Null for false: train once. "
            "Refitting multiplies the cost; ForecasterStats is refitted in "
            "every fold whatever it says."
        ))] = None,
        fixed_train_size: Annotated[bool | None, Field(description=(
            "Whether the training window keeps its size when refitting "
            "(true) or grows (false). Null for false; it only matters with "
            "`refit`."
        ))] = None,
        gap: Annotated[int | None, Field(ge=0, description=(
            "Observations between the end of training and the test set. Null "
            "for 0."
        ))] = None,
        skip_folds: Annotated[Count | list[Count] | None, Field(description=(
            "Folds are numbered from 0, and fold 0 always runs. An integer n "
            "keeps folds 0, n, 2n, ...; a list skips the folds at those "
            "numbers (each at least 1). Null for every fold."
        ))] = None,
        allow_incomplete_fold: Annotated[bool | None, Field(description=(
            "Whether the last fold may have fewer than `steps` observations. "
            "Null for true."
        ))] = None,
        ctx: Context = None,
    ) -> ToolResult:
        _inputs.check_not_numeric_text(initial_train_size, "initial_train_size")
        plan_entry = store.get(plan_id, "plan_id", ("plan",))

        def work(control: CallControl):
            result = assistant.create_cv(
                profile               = _copy(plan_entry.profile),
                plan                  = _copy(plan_entry.obj),
                initial_train_size    = initial_train_size,
                fold_stride           = fold_stride,
                refit                 = refit,
                fixed_train_size      = fixed_train_size,
                gap                   = gap,
                skip_folds            = skip_folds,
                allow_incomplete_fold = allow_incomplete_fold,
            )
            cost = _cost(result.cv_config, result.plan.forecaster, result.plan.steps)
            # The warning a backtest of this strategy will emit, given now,
            # when the strategy can still change.
            warn_long_training(
                estimator_fits = cost["estimator_fits"],
                n_fits         = cost["n_fits"],
                forecaster     = result.plan.forecaster,
                steps          = result.plan.steps,
            )
            object_id = store.new_id("cv")
            summary = state.summary(object_id, result.describe())
            code_file = state.code_file(object_id, result.code)
            control.wrote(summary[2], code_file)
            return object_id, result, summary, code_file, cost

        outcome = await run_call(work, report=_report(ctx), label="create_cv")
        object_id, result, summary, code_file, cost = outcome.value
        links = {"profile_id": plan_entry.profile_id, "plan_id": plan_entry.id}

        return _register(
            state,
            object_id     = object_id,
            kind          = "cv",
            obj           = result,
            links         = links,
            summary       = summary,
            notices       = build_notices(
                                outcome.warnings,
                                plan_warnings = result.plan.warnings,
                                data_warnings = plan_entry.data_warnings,
                            ),
            source        = plan_entry,
            code          = result.code,
            code_file     = code_file,
            cost          = cost,
            changeable    = list(CV_ARGUMENTS),
        )

    def _data_of(entry: Entry) -> str:
        # The file the profile was read from, checked again before it is
        # read: inside the allowed directory after resolving links, and as it
        # was when it was profiled.
        # A file now larger than the limit changed since it was profiled, and
        # is reported as such without reading it.
        path = _inputs.resolve_csv_path(entry.data_path, state.allowed, "data_path")
        _inputs.check_unchanged(
            path,
            entry.data_sha256,
            "data_path",
            profiled  = True,
            max_bytes = state.max_file_bytes,
        )
        return path

    def _run_plan_locally(plan_obj: Any, argument: str) -> None:
        # Every tool that runs a plan checks it here, besides the check made
        # when the plan was built.
        _check_foundation_kwargs(
            plan_obj.forecaster, plan_obj.estimator_kwargs, argument
        )
        model_id = state.models.model_of(plan_obj.forecaster, plan_obj.estimator)
        state.models.check(model_id, argument)
        state.models.check_backend(model_id, argument)

    def _keep_failure(exc: Exception) -> None:
        # The traceback and the code of a failed script never go in the
        # response: they are kept for `get_failure`, named in the details.
        text = failure_text(exc)
        if text is not None:
            attach_details(exc, {"failure_id": state.add_failure(text)})

    def _finish_run(
        control: CallControl,
        kind: ObjectKind,
        result: Any,
        frames: dict[str, Any],
    ) -> tuple[str, dict[str, str], tuple[str, bool, dict[str, str]], str | None, int]:
        # What every run writes once it ended: its CSV files, its summary and
        # its script when they are long, and the memory it takes, measured
        # here rather than in the event loop.
        control.check()
        object_id = store.new_id(kind)
        files: dict[str, str] = {}
        for role, frame in frames.items():
            files.update(state.write_frame(object_id, role, frame))
            control.wrote(files)
        summary = state.summary(object_id, result.describe())
        code_file = state.code_file(object_id, result.code)
        control.wrote(summary[2], code_file)
        return object_id, files, summary, code_file, estimate_nbytes(result)

    @_reported
    async def backtest(
        cv_id: Annotated[str, Field(description="Id returned by `create_cv`.")],
        plan_id: Annotated[str | None, Field(description=(
            "Plan to backtest, built from the same profile. Null for the plan "
            "the cross-validation strategy was built for."
        ))] = None,
        ctx: Context = None,
    ) -> ToolResult:
        cv_entry = store.get(cv_id, "cv_id", ("cv",))
        cv_result = cv_entry.obj
        if plan_id is None:
            backtested, plan_link = cv_result.plan, cv_entry.envelope.links["plan_id"]
        else:
            plan_entry = store.get(plan_id, "plan_id", ("plan",))
            if plan_entry.profile_id != cv_entry.profile_id:
                raise ServerError(
                    f"The plan {plan_id!r} and the cross-validation strategy "
                    f"{cv_id!r} come from different profiles "
                    f"({plan_entry.profile_id!r} and {cv_entry.profile_id!r}).",
                    code    = "inconsistent_ids",
                    field   = "plan_id",
                    hint    = "Call `create_cv` with this plan.",
                    details = {"plan_id": plan_id, "cv_id": cv_id},
                )
            backtested, plan_link = plan_entry.obj, plan_entry.id
        _run_plan_locally(backtested, "plan_id")

        def work(control: CallControl):
            path = _data_of(cv_entry)
            try:
                result = assistant.backtest(
                    data          = path,
                    cv            = copy.deepcopy(cv_result.cv),
                    profile       = _copy(cv_entry.profile),
                    plan          = _copy(backtested),
                    show_progress = False,
                )
            except SkforecastAIError as exc:
                _keep_failure(exc)
                raise
            _inputs.check_unchanged(path, cv_entry.data_sha256, "data_path")
            frames = {"predictions": result.predictions, "metrics": result.metrics}
            return result, *_finish_run(control, "backtest", result, frames)

        outcome = await run_call(
            work,
            report = _report(ctx),
            label  = backtested.forecaster,
        )
        result, object_id, files, summary, code_file, nbytes = outcome.value
        links = {
            "profile_id": cv_entry.profile_id, "plan_id": plan_link, "cv_id": cv_id,
        }
        cost = _cost(result.cv_config, result.plan.forecaster, result.plan.steps)

        return _register(
            state,
            object_id = object_id,
            kind      = "backtest",
            obj       = result,
            links     = links,
            summary   = summary,
            notices   = build_notices(
                            outcome.warnings,
                            plan_warnings = result.plan.warnings,
                            data_warnings = cv_entry.data_warnings,
                        ),
            source    = cv_entry,
            code      = result.code,
            code_file = code_file,
            files     = files,
            nbytes    = nbytes,
            cost      = cost,
        )

    @_reported
    async def compare(
        cv_id: Annotated[str, Field(description=(
            "Id returned by `create_cv`: every candidate is backtested on its "
            "folds."
        ))],
        candidates: Annotated[list[CandidateArg] | None, Field(
            min_length  = 1,
            description = (
                "Configurations to compare, each {'name': ..., 'config': "
                "{...}}, e.g. [{'name': 'ridge', 'config': {'estimator': "
                "'Ridge'}}]. Null for the candidates recommended by the "
                "profile: the forecasters of its family (with several series, "
                "ForecasterRecursiveMultiSeries and ForecasterFoundation), or "
                "the estimators of the recommended forecaster when that leaves "
                "one, without those above 500 estimator fits. A candidate that "
                "fails is ranked last with its error."
            ),
        )] = None,
        interval: Annotated[Interval | None, Field(description=(
            f"Prediction interval computed for every candidate. "
            f"{INTERVAL_DESCRIPTION} Null for the interval of the plan the "
            f"strategy was built for."
        ))] = None,
        baseline: Annotated[bool, Field(description=(
            "Whether to add a seasonal naive baseline (ForecasterEquivalentDate) "
            "to the ranking."
        ))] = True,
        ctx: Context = None,
    ) -> ToolResult:
        cv_entry = store.get(cv_id, "cv_id", ("cv",))
        profile_obj = cv_entry.profile
        # Without `interval`, the one of the plan of the strategy, so the
        # plan of the winner keeps the interval the agent asked for.
        shared_interval = interval
        if shared_interval is None and cv_entry.obj.plan.interval is not None:
            shared_interval = list(cv_entry.obj.plan.interval)
        configs = None
        if candidates is None:
            # The default candidates are named by their forecaster and run
            # the default foundation model, if any.
            models = {
                name: state.models.model_of(name, None)
                for name in profile_obj.forecaster_candidates
            }
        else:
            configs, models = [], {}
            for position, candidate in enumerate(candidates):
                prefix = f"candidates[{position}]"
                _inputs.check_text_argument(candidate.name, f"{prefix}.name")
                config = dict(candidate.config)
                forecaster_name = config.get("forecaster") or profile_obj.forecaster
                _check_foundation_kwargs(
                    forecaster_name,
                    config.get("estimator_kwargs"),
                    f"{prefix}.config.estimator_kwargs",
                )
                model_id = state.models.model_of(
                    forecaster_name, config.get("estimator")
                )
                state.models.check(model_id, f"{prefix}.config.estimator")
                models[candidate.name] = model_id
                configs.append((candidate.name, config))

        def work(control: CallControl):
            path = _data_of(cv_entry)
            uncached = state.models.uncached(models.values())

            def on_progress(event):
                # The start of a candidate repeats the count of the end of the
                # previous one, so it counts as a half step: the progress then
                # grows with every notification.
                started = event.status == "started"
                control.progress(
                    2 * event.completed + started,
                    2 * event.total,
                    f"{event.candidate}: {event.status}",
                    running = event.candidate if started else None,
                )

            try:
                result = assistant.compare(
                    data              = path,
                    cv                = copy.deepcopy(cv_entry.obj.cv),
                    profile           = _copy(profile_obj),
                    candidates        = copy.deepcopy(configs),
                    interval          = shared_interval,
                    show_progress     = False,
                    baseline          = baseline,
                    progress_callback = on_progress,
                )
            except SkforecastAIError as exc:
                _keep_failure(exc)
                raise
            _inputs.check_unchanged(path, cv_entry.data_sha256, "data_path")
            best = result.best_candidate
            frames = {
                "leaderboard": result.results,
                "best_predictions": best.predictions,
                "best_metrics": best.metrics,
            }
            object_id, files, summary, code_file, nbytes = _finish_run(
                control, "comparison", _Described(result, best.code), frames
            )
            # Long scripts and failures of the candidates, written once; file
            # names hold the position of a candidate, never its name.
            code_files = {}
            for position, (name, candidate) in enumerate(result.candidates.items()):
                name_code = state.code_file(
                    f"{object_id}-candidate-{position}", candidate.code
                )
                if name_code is not None:
                    code_files[name] = name_code
            failures = {}
            for position, (name, failure) in enumerate(result.failures.items()):
                failures[name] = state.long_text(
                    f"{object_id}-failure-{position}.txt",
                    candidate_failure_text(name, failure),
                    MAX_FAILURE_CHARS,
                )
            control.wrote(code_files, *(path for _, path in failures.values()))
            # The plan of the winner, registered so `forecast` can use it.
            best_plan = _describe_plan(control, profile_obj, best.plan)
            return (
                result, object_id, files, summary, code_file, code_files, failures,
                nbytes, best_plan, uncached,
            )

        outcome = await run_call(work, report=_report(ctx), label="compare")
        (
            result, object_id, files, summary, code_file, code_files, failures,
            nbytes, best_plan, uncached,
        ) = outcome.value
        best = result.best_candidate
        best_plan_id, best_summary, best_code = best_plan
        plan_warnings = [
            text for candidate in result.candidates.values()
            for text in candidate.plan.warnings
        ]
        best_texts = set(best.plan.warnings)
        _plan_envelope(
            best_plan_id,
            best.plan,
            cv_entry,
            [r for r in outcome.warnings if notice_text(r) in best_texts],
            {"profile_id": cv_entry.profile_id, "comparison_id": object_id},
            best_summary,
            best_code,
        )
        # The cost of the candidates that ran, each with the strategy it ran.
        estimator_fits = sum(
            _cost(candidate.cv_config, candidate.plan.forecaster, candidate.plan.steps)[
                "estimator_fits"
            ]
            for candidate in result.candidates.values()
        )
        # Only the candidates whose script ran (also those that failed while
        # running) can have downloaded weights.
        ran_models = {
            state.models.model_of(candidate.plan.forecaster, candidate.plan.estimator)
            for candidate in result.candidates.values()
        } | {
            models.get(name) for name, failure in result.failures.items()
            if failure.generated_code is not None
        }
        cost = {
            "n_folds": int(result.cv_config["n_folds"]),
            "n_fits": int(result.cv_config["n_fits"]),
            "estimator_fits": estimator_fits,
        }

        return _register(
            state,
            object_id            = object_id,
            kind                 = "comparison",
            obj                  = result,
            links                = {
                "profile_id": cv_entry.profile_id,
                "cv_id": cv_id,
                "best_plan_id": best_plan_id,
            },
            summary              = summary,
            notices              = build_notices(
                                       outcome.warnings,
                                       plan_warnings  = plan_warnings,
                                       data_warnings  = cv_entry.data_warnings,
                                       server_notices = state.models.announce(
                                           model for model in uncached
                                           if model in ran_models
                                       ),
                                   ),
            source               = cv_entry,
            code                 = best.code,
            code_file            = code_file,
            candidate_code_files = code_files,
            candidate_failures   = failures,
            files                = files,
            nbytes               = nbytes,
            cost                 = cost,
        )

    @_reported
    async def forecast(
        plan_id: Annotated[str, Field(description=(
            "Id of the plan to run (from `plan`, `refine_plan` or "
            "`links.best_plan_id` of `compare`)."
        ))],
        test_size: Annotated[int | float | str | None, Field(description=(
            "Null to forecast the future. To evaluate instead, the test set: "
            "the last n observations (an integer, which must equal `steps`) "
            "or the ISO 8601 date it starts at. A fraction in (0, 1) only "
            "works when it gives exactly `steps` observations."
        ))] = None,
        exog_path: Annotated[str | None, Field(description=(
            "Absolute path of a CSV file with the future values of the "
            "exogenous variables, one row per date (and series) of the "
            "horizon. Required to forecast the future when the data has "
            "exogenous variables. The script of `get_code` reads them from "
            "'exog_future.csv' in its working directory."
        ))] = None,
        ctx: Context = None,
    ) -> ToolResult:
        _inputs.check_not_numeric_text(test_size, "test_size")
        plan_entry = store.get(plan_id, "plan_id", ("plan",))
        _run_plan_locally(plan_entry.obj, "plan_id")

        def work(control: CallControl):
            path = _data_of(plan_entry)
            exog, exog_file, exog_digest = None, None, None
            if exog_path is not None:
                exog_file = _inputs.resolve_csv_path(
                    exog_path, state.allowed, "exog_path"
                )
                _inputs.check_file_size(exog_file, state.max_file_bytes, "exog_path")
                exog_digest = _inputs.file_sha256(exog_file)
                data_profile = plan_entry.profile.data_profile
                exog = load_exog(
                    exog_file,
                    date_column      = data_profile.date_column,
                    series_id_column = data_profile.series_id_column,
                )
            try:
                result = assistant.forecast(
                    data      = path,
                    exog      = exog,
                    test_size = test_size,
                    profile   = _copy(plan_entry.profile),
                    plan      = _copy(plan_entry.obj),
                )
            except SkforecastAIError as exc:
                _keep_failure(exc)
                raise
            _inputs.check_unchanged(path, plan_entry.data_sha256, "data_path")
            if exog_file is not None:
                _inputs.check_unchanged(exog_file, exog_digest, "exog_path")
            frames = {"predictions": result.predictions, "metrics": result.metrics}
            return result, *_finish_run(control, "forecast", result, frames)

        outcome = await run_call(
            work,
            report = _report(ctx),
            label  = plan_entry.obj.forecaster,
        )
        result, object_id, files, summary, code_file, nbytes = outcome.value

        # The plan of an evaluation (with `end_train`) is never registered as
        # a plan: the forecast links the plan it was given.
        return _register(
            state,
            object_id = object_id,
            kind      = "forecast",
            obj       = result,
            links     = {"profile_id": plan_entry.profile_id, "plan_id": plan_id},
            summary   = summary,
            notices   = build_notices(
                            outcome.warnings,
                            plan_warnings = result.plan.warnings,
                            data_warnings = plan_entry.data_warnings,
                        ),
            source    = plan_entry,
            code      = result.code,
            code_file = code_file,
            files     = files,
            nbytes    = nbytes,
        )

    @_reported
    async def get_failure(
        object_id: Annotated[str, Field(description=(
            "`details.failure_id` of an error, or the id of a comparison "
            "whose candidate failed."
        ))],
        candidate: Annotated[str | None, Field(description=(
            "Name of the failed candidate of a comparison."
        ))] = None,
    ) -> FailureResult:
        with state.failures_lock:
            kept = state.failures.get(object_id)
        if kept is None and object_id.startswith("failure-"):
            raise ServerError(
                f"No failure is kept with the id {object_id!r}: the server keeps "
                f"the last {store.max_objects}, and none from a previous run.",
                code    = "unknown_id",
                field   = "object_id",
                details = {"id": object_id},
            )
        if kept is not None and candidate is not None:
            raise ServerError(
                f"{object_id!r} is the failure of one call: `candidate` only "
                f"applies to the id of a comparison.",
                code  = "invalid_argument",
                field = "candidate",
            )
        if kept is None:
            entry = store.get(object_id, "object_id", ("comparison",))
            if candidate not in entry.candidate_failures:
                raise ServerError(
                    f"The comparison {object_id!r} has no failed candidate named "
                    f"{candidate!r}. Failed candidates: "
                    f"{sorted(entry.candidate_failures)}.",
                    code  = "invalid_argument",
                    field = "candidate",
                )
            kept = entry.candidate_failures[candidate]
        text, path = kept

        return FailureResult(
            id             = object_id,
            candidate      = candidate,
            text           = text,
            text_truncated = path is not None,
            files          = {} if path is None else {"failure": path},
        )

    @_reported
    async def get_code(
        object_id: Annotated[str, Field(description=(
            "Id of a plan (its forecasting script), a cross-validation strategy "
            "(the code that builds it), a backtest, a forecast or a comparison "
            "(the script that ran)."
        ))],
        candidate: Annotated[str | None, Field(description=(
            "For a comparison, the candidate whose script to return. Null for "
            "the best one."
        ))] = None,
    ) -> CodeResult:
        entry = store.get(object_id, "object_id")
        if entry.code is None:
            raise ServerError(
                f"{object_id!r} is a {entry.kind}, which has no code: pass the id "
                f"of a plan, a cross-validation strategy, a backtest, a forecast "
                f"or a comparison.",
                code  = "invalid_argument",
                field = "object_id",
            )
        code, code_file = entry.code, entry.code_file
        if candidate is not None:
            if entry.kind != "comparison" or candidate not in entry.obj.candidates:
                names = []
                if entry.kind == "comparison":
                    names = sorted(entry.obj.candidates)
                raise ServerError(
                    f"{object_id!r} has no candidate {candidate!r} that ran. "
                    f"Candidates that ran: {names}.",
                    code  = "invalid_argument",
                    field = "candidate",
                )
            code = entry.obj.candidates[candidate].code
            code_file = entry.candidate_code_files.get(candidate)
        if code_file is None:
            return CodeResult(
                id=entry.id, kind=entry.kind, candidate=candidate, code=code
            )

        return CodeResult(
            id             = entry.id,
            kind           = entry.kind,
            candidate      = candidate,
            code           = code[:MAX_CODE_CHARS],
            code_truncated = True,
            files          = {"code": code_file},
        )

    @_reported
    async def list_objects(
        kind: Annotated[ObjectKind | None, Field(description=(
            "Only the objects of this kind. Null for every kind."
        ))] = None,
    ) -> ObjectList:
        objects = [
            ObjectInfo(id=entry.id, kind=entry.kind, links=entry.envelope.links)
            for entry in store.entries()
            if kind is None or entry.kind == kind
        ]

        return ObjectList(
            objects       = objects,
            max_objects   = store.max_objects,
            max_memory_mb = store.max_bytes // (1024 * 1024),
            removed       = store.removed,
        )

    @_reported
    async def describe_object(
        object_id: Annotated[str, Field(description="Id of a registered object.")],
    ) -> ToolResult:
        return store.get(object_id, "object_id").envelope

    return [
        _StrictTool.build(profile, "profile", (
            "Profile a CSV file: frequency, series, exogenous columns and the "
            "recommended forecaster and estimator. Returns a profile id."
        )),
        _StrictTool.build(plan, "plan", (
            "Build a forecasting plan (lags, window features, metric, "
            "preprocessing, interval) from a profile and a horizon. Returns a "
            "plan id."
        )),
        _StrictTool.build(refine_plan, "refine_plan", (
            "Build a new plan from an existing one, changing some of its "
            "decisions. Returns a new plan id; the original plan is kept."
        )),
        _StrictTool.build(create_cv, "create_cv", (
            "Build a time series cross-validation strategy (TimeSeriesFold) for "
            "a plan. The response states its cost in `cost`. Returns a cv id."
        )),
        _StrictTool.build(backtest, "backtest", (
            "Backtest a plan with a cross-validation strategy: metrics over the "
            "folds, with the predictions and metrics in CSV files. Returns a "
            "backtest id."
        )),
        _StrictTool.build(compare, "compare", (
            "Backtest several configurations on the same folds and rank them by "
            "the metric of the profile. Reports progress per candidate and can "
            "be cancelled between candidates. Returns a comparison id and the "
            "plan of the winner in `links.best_plan_id`."
        )),
        _StrictTool.build(forecast, "forecast", (
            "Run a plan: forecast the future, or evaluate on a test set with "
            "`test_size`. Predictions and metrics go to CSV files. Returns a "
            "forecast id."
        )),
        _StrictTool.build(get_code, "get_code", (
            "Return the Python script of an object: the one that ran, or that "
            "would run for a plan."
        ), read_only=True),
        _StrictTool.build(get_failure, "get_failure", (
            "Return the traceback and the code of a failed run or of a failed "
            "candidate of a comparison."
        ), read_only=True),
        _StrictTool.build(list_objects, "list_objects", (
            "List the ids of the objects the server keeps."
        ), read_only=True),
        _StrictTool.build(describe_object, "describe_object", (
            "Return the response that created an object (summary, links, "
            "notices, files)."
        ), read_only=True),
    ]


def _check_writable(output: Path) -> None:
    """
    Check that the server can write files in its output directory, so a
    directory it cannot write stops the server when it starts rather than
    every run when it ends.
    """

    try:
        with tempfile.NamedTemporaryFile(dir=output, prefix=".skforecast-ai-check-"):
            pass
    except OSError as exc:
        raise InvalidInputError(
            f"The output directory {str(output)!r} cannot be written: "
            f"{exc.strerror or exc}.",
            field = "output_dir",
        ) from exc


# Errors of a stream whose other end is gone: the client closed its pipes.
_DISCONNECTED = (
    BrokenPipeError,
    ConnectionResetError,
    anyio.BrokenResourceError,
    anyio.ClosedResourceError,
)


def _client_disconnected(exc: BaseException) -> bool:
    """
    Whether an exception, or every exception of a group, says that the
    client closed its end of the connection.
    """

    # An exception group (anyio's backport before Python 3.11).
    inner = getattr(exc, "exceptions", None)
    if isinstance(inner, tuple) and inner:
        return all(_client_disconnected(item) for item in inner)

    return isinstance(exc, _DISCONNECTED)


class _OneLineFormatter(logging.Formatter):
    """
    Format of the log of the server: one line per record (the traceback of
    an unexpected error follows it), never wrapped to the terminal width.
    """

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")


def _build_state(
    allow_dir: str | Path,
    output_dir: str | Path | None,
    max_objects: int,
    max_memory_mb: int,
    allow_models: Iterable[str] = (),
    max_file_mb: int = DEFAULT_MAX_FILE_MB,
) -> _ServerState:
    """
    Check the settings of a server and build what its tools share.
    """

    for name, value in (("max_objects", max_objects), ("max_memory_mb", max_memory_mb)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidInputError(
                f"`{name}` must be an integer of at least 1, got {value!r}.",
                field = name,
            )
    if isinstance(max_file_mb, bool) or not isinstance(max_file_mb, int) or (
        max_file_mb < 0
    ):
        raise InvalidInputError(
            f"`max_file_mb` must be an integer of at least 0 (0 for no "
            f"limit), got {max_file_mb!r}.",
            field = "max_file_mb",
        )
    allowed = AllowedDir.from_path(allow_dir)
    if isinstance(allow_models, str):
        allow_models = [allow_models]
    models = ModelPolicy(allowed_prefixes=check_allow_models(allow_models))
    if output_dir is None:
        output = Path(tempfile.mkdtemp(prefix="skforecast-ai-mcp-"))
    else:
        output = Path(os.path.abspath(os.fspath(output_dir)))
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise InvalidInputError(
                f"The output directory {str(output)!r} cannot be created: "
                f"{exc.strerror or exc}.",
                field = "output_dir",
            ) from exc

    _check_writable(output)
    store = Store(
        max_objects = max_objects,
        max_bytes   = max_memory_mb * 1024 * 1024,
    )

    return _ServerState(
        allowed        = allowed,
        output_dir     = output,
        store          = store,
        assistant      = ForecastingAssistant(),
        models         = models,
        max_file_bytes = max_file_mb * 1024 * 1024,
    )


def _build_server(state: _ServerState) -> MCPServer:
    """
    Build the MCP server of a state.
    """

    return MCPServer(
        name         = "skforecast-ai",
        title        = "skforecast-ai",
        instructions = INSTRUCTIONS,
        version      = __version__,
        tools        = _build_tools(state),
    )


def create_server(
    allow_dir: str | Path,
    output_dir: str | Path | None = None,
    max_objects: int = DEFAULT_MAX_OBJECTS,
    max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
    allow_models: Iterable[str] = (),
    max_file_mb: int = DEFAULT_MAX_FILE_MB,
) -> MCPServer:
    """
    Create the MCP server of skforecast-ai, without running it.

    Useful to test the server in memory (`mcp.Client(server)`) or to run it
    with another transport. `run_server()` creates it and serves it over
    stdio, as the `skforecast-ai mcp` command does.

    Parameters
    ----------
    allow_dir : str, Path
        Directory the server may read data from. Only absolute paths of CSV
        files inside it are accepted, also after resolving symbolic links.
    output_dir : str, Path, default None
        Directory of the files the server writes: predictions, metrics and
        leaderboards as CSV, and summaries, scripts and failures too long for
        a response. It is created if it does not exist. When None, a new
        temporary directory, kept when the server stops.
    max_objects : int, default 256
        Most objects the server keeps; the least recently used ones are
        removed beyond it.
    max_memory_mb : int, default 1024
        Memory, in MB, the objects may take (an estimate); the least
        recently used ones are removed beyond it.
    allow_models : iterable of str, default ()
        Model ID prefixes of foundation models with a license restriction
        or gated weights that the server may run (`'google/timesfm-3.0'`).
        Each must start with the prefix of an adapter of skforecast. Models
        without either run without it.
    max_file_mb : int, default 256
        Largest CSV file (data or future exogenous values) the server reads,
        in MB, checked on the size of the file before reading it. 0 for no
        limit.

    Returns
    -------
    server : MCPServer
        Server of the `mcp` package with the tools of skforecast-ai.
    """

    state = _build_state(
        allow_dir, output_dir, max_objects, max_memory_mb, allow_models, max_file_mb
    )

    return _build_server(state)


def run_server(
    allow_dir: str | Path,
    output_dir: str | Path | None = None,
    max_objects: int = DEFAULT_MAX_OBJECTS,
    max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
    allow_models: Iterable[str] = (),
    max_file_mb: int = DEFAULT_MAX_FILE_MB,
) -> None:
    """
    Run the MCP server of skforecast-ai over stdio until the client closes.

    The working directory of the process becomes `output_dir`, so a library
    that writes files next to it (CatBoost writes `catboost_info/`) does not
    write them into the project of the user. While it serves, the logger
    `skforecast_ai.mcp` writes one plain line per record to the standard
    error and does not pass its records to the root logger; both are
    restored when it returns. When the client disconnects, also during a
    call, it logs one line and returns instead of raising, and the standard
    output (the closed pipe of the client) is pointed to the null device so
    flushing it at exit does not fail again.

    Parameters
    ----------
    allow_dir : str, Path
        Directory the server may read data from. Only absolute paths of CSV
        files inside it are accepted, also after resolving symbolic links.
    output_dir : str, Path, default None
        Directory of the files the server writes: predictions, metrics and
        leaderboards as CSV, and summaries, scripts and failures too long for
        a response. It is created if it does not exist. When None, a new
        temporary directory, kept when the server stops.
    max_objects : int, default 256
        Most objects the server keeps.
    max_memory_mb : int, default 1024
        Memory, in MB, the objects may take (an estimate).
    allow_models : iterable of str, default ()
        Model ID prefixes of foundation models with a license restriction
        or gated weights that the server may run.
    max_file_mb : int, default 256
        Largest CSV file the server reads, in MB; 0 for no limit.

    Returns
    -------
    None
    """

    state = _build_state(
        allow_dir, output_dir, max_objects, max_memory_mb, allow_models, max_file_mb
    )
    server = _build_server(state)
    os.chdir(state.output_dir)
    # The log of the server goes to stderr in plain lines; the SDK of MCP
    # configures a handler that wraps them to the width of a terminal.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_OneLineFormatter())
    previous = (logger.level, logger.propagate)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        logger.info(
            "skforecast-ai MCP server: reads CSV files in %s, writes files to %s.",
            state.allowed.path,
            state.output_dir,
        )
        try:
            server.run("stdio")
        except BaseException as exc:
            if not _client_disconnected(exc):
                raise
            # The client went away while a call ran: nothing is left to
            # answer, so the server stops as if the client had closed it.
            logger.info("The client disconnected; the server stops.")
            _discard_stdout()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous[0])
        logger.propagate = previous[1]


def _discard_stdout() -> None:
    """
    Point the standard output to the null device, so flushing it when the
    process ends does not fail again on the closed pipe.
    """

    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
    except (OSError, ValueError):
        pass
