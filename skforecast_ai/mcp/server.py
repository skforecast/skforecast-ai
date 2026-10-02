################################################################################
#                                 MCP server                                   #
#                                                                              #
# The deterministic workflow of ForecastingAssistant as tools for agents       #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import functools
import json
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, get_args, get_origin
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from mcp.server.mcpserver.tools import Tool
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
from mcp.types import ToolAnnotations
from pydantic import ConfigDict, Field, ValidationError
from .. import __version__
from ..assistant import ForecastingAssistant
from ..exceptions import InvalidInputError, SkforecastAIError
from ..recommendation import count_estimator_fits
from ..schemas.plans import REFINE_PLAN_OVERRIDE_KEYS
from . import _inputs
from ._errors import ServerError, argument_error_payload, tool_error
from ._inputs import AllowedDir
from ._runtime import CallControl, build_notices, notice_text, run_call
from ._store import Entry, Store, estimate_nbytes
from .models import (
    CodeResult,
    ObjectInfo,
    ObjectKind,
    ObjectList,
    RefinePlanArgs,
    ToolResult,
)

logger = logging.getLogger("skforecast_ai.mcp")

# Longest summary and code a response carries; the full text goes to a file.
MAX_SUMMARY_CHARS = 20_000
MAX_CODE_CHARS = 20_000

DEFAULT_MAX_OBJECTS = 256
DEFAULT_MAX_MEMORY_MB = 1024

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
`create_cv`. Each tool returns an `id`; later tools take ids, never objects. \
Every response has a plain-text `summary` and the warnings of the call in \
`notices`; it never holds rows of data. `get_code` returns the script of a \
plan or a cross-validation strategy, `describe_object` the response that \
created an object, `list_objects` the ids registered now.

Errors are JSON objects with `code`, `message`, `field`, `hint` and \
`details`. Dates are ISO 8601 text ('2012-01-01'); counts are numbers.\
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
    """

    allowed: AllowedDir
    output_dir: Path
    store: Store
    assistant: ForecastingAssistant

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


def _copy(obj: Any) -> Any:
    """
    Deep copy of a registered object, so no call of the core can change it.
    """

    return obj.model_copy(deep=True)


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
    """

    text, truncated, files = summary
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
    state.store.add(
        Entry(
            id            = object_id,
            kind          = kind,
            obj           = obj,
            envelope      = envelope,
            profile       = profile,
            profile_id    = profile_id,
            data_path     = data_path,
            data_sha256   = data_sha256,
            data_warnings = data_warnings,
            code          = code,
            code_file     = code_file,
            nbytes        = estimate_nbytes(obj) + len(text) + len(code or ""),
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
    ) -> ToolResult:
        _inputs.check_text_argument(target, "target")
        _inputs.check_text_argument(date_column, "date_column")
        _inputs.check_text_argument(series_id_column, "series_id_column")

        def work(control: CallControl):
            path = _inputs.resolve_csv_path(data_path, state.allowed, "data_path")
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
            control.check()
            return object_id, result, path, digest, summary

        outcome = await run_call(work)
        object_id, result, path, digest, summary = outcome.value

        return _register(
            state,
            object_id     = object_id,
            kind          = "profile",
            obj           = result,
            links         = {},
            summary       = summary,
            notices       = build_notices(outcome.warnings, default_source="data"),
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
    ) -> ToolResult:
        return _register(
            state,
            object_id  = object_id,
            kind       = "plan",
            obj        = new_plan,
            links      = links,
            summary    = summary,
            notices    = build_notices(
                             outcome_warnings,
                             plan_warnings = new_plan.warnings,
                             data_warnings = source.data_warnings,
                         ),
            source     = source,
            code       = code[0],
            code_file  = code[1],
            changeable = sorted(REFINE_PLAN_OVERRIDE_KEYS),
        )

    def _describe_plan(control: CallControl, profile_obj: Any, new_plan: Any):
        script = assistant.forecast_code(profile=_copy(profile_obj), plan=new_plan)
        object_id = store.new_id("plan")
        summary = state.summary(object_id, script.describe())
        code_file = state.code_file(object_id, script.code)
        control.check()
        return object_id, summary, (script.code, code_file)

    @_reported
    async def plan(
        profile_id: Annotated[str, Field(description="Id returned by `profile`.")],
        steps: Annotated[int, Field(description=(
            "Forecast horizon: number of steps ahead to predict (at least 1)."
        ))],
        interval: Annotated[list[float] | None, Field(description=(
            "Prediction interval as two quantiles, e.g. [0.1, 0.9] for 80 %. "
            "Null for no interval."
        ))] = None,
        forecaster: Annotated[str | None, Field(description=(
            "skforecast forecaster class to use instead of the recommended one, "
            "e.g. 'ForecasterRecursive'. Null for the recommendation."
        ))] = None,
        estimator: Annotated[str | None, Field(description=(
            "Estimator class (e.g. 'LGBMRegressor'), or the Hugging Face model "
            "id of a foundation model. Null for the recommendation."
        ))] = None,
        estimator_kwargs: Annotated[dict[str, Any] | None, Field(description=(
            "Keyword arguments of the estimator, e.g. {'n_estimators': 200}."
        ))] = None,
        lags: Annotated[int | list[int] | None, Field(description=(
            "Lags: n for 1..n, or a list of positive integers. Null for the "
            "selection from the partial autocorrelation."
        ))] = None,
        window_features: Annotated[
            list[dict[str, list[str] | int]] | None,
            Field(description=(
                "Rolling features, e.g. [{'stats': ['mean', 'std'], "
                "'window_size': 7}], one entry per window size. Null for the "
                "deterministic selection."
            )),
        ] = None,
    ) -> ToolResult:
        profile_entry = store.get(profile_id, "profile_id", ("profile",))

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
            return new_plan, *_describe_plan(control, profile_entry.obj, new_plan)

        outcome = await run_call(work)
        new_plan, object_id, summary, code = outcome.value

        return _plan_envelope(
            object_id, new_plan, profile_entry, outcome.warnings,
            {"profile_id": profile_entry.id}, summary, code,
        )

    @_reported
    async def refine_plan(
        plan_id: Annotated[str, Field(description="Id of the plan to refine.")],
        overrides: Annotated[RefinePlanArgs, Field(description=(
            "Values to change. An omitted key keeps the value of the plan. "
            "`estimator_kwargs`, `interval`, `lags` and `window_features` "
            "also accept null, which asks for the deterministic default "
            "({'lags': null} selects the lags again, {'interval': null} "
            "removes the interval)."
        ))],
    ) -> ToolResult:
        plan_entry = store.get(plan_id, "plan_id", ("plan",))

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
            return new_plan, *_describe_plan(control, plan_entry.profile, new_plan)

        outcome = await run_call(work)
        new_plan, object_id, summary, code = outcome.value

        return _plan_envelope(
            object_id, new_plan, plan_entry, outcome.warnings,
            {"profile_id": plan_entry.profile_id, "parent_plan_id": plan_entry.id},
            summary, code,
        )

    @_reported
    async def create_cv(
        plan_id: Annotated[str, Field(description=(
            "Id of the plan to backtest (from `plan` or `refine_plan`)."
        ))],
        initial_train_size: Annotated[Count | str | None, Field(description=(
            "Observations of the first training set, or the ISO 8601 date that "
            "ends it. Null for the default."
        ))] = None,
        fold_stride: Annotated[int | None, Field(ge=1, description=(
            "Observations the test set advances between folds. Null for "
            "`steps` (back-to-back folds)."
        ))] = None,
        refit: Annotated[bool | NonNegative | None, Field(description=(
            "Whether to train again in every fold (true), never (false, the "
            "default) or every n folds (an integer). Refitting multiplies the "
            "cost."
        ))] = None,
        fixed_train_size: Annotated[bool | None, Field(description=(
            "Whether the training window keeps its size when refitting."
        ))] = None,
        gap: Annotated[int | None, Field(ge=0, description=(
            "Observations between the end of training and the test set."
        ))] = None,
        skip_folds: Annotated[Count | list[NonNegative] | None, Field(description=(
            "Keep every n-th fold (an integer), or skip the listed folds."
        ))] = None,
        allow_incomplete_fold: Annotated[bool | None, Field(description=(
            "Whether the last fold may have fewer than `steps` observations."
        ))] = None,
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
            object_id = store.new_id("cv")
            summary = state.summary(object_id, result.describe())
            code_file = state.code_file(object_id, result.code)
            control.check()
            return object_id, result, summary, code_file

        outcome = await run_call(work)
        object_id, result, summary, code_file = outcome.value
        cost = _cost(result.cv_config, result.plan.forecaster, result.plan.steps)
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

    @_reported
    async def get_code(
        object_id: Annotated[str, Field(description=(
            "Id of a plan (its forecasting script) or of a cross-validation "
            "strategy (the code that builds it)."
        ))],
    ) -> CodeResult:
        entry = store.get(object_id, "object_id")
        if entry.code is None:
            raise ServerError(
                f"{object_id!r} is a {entry.kind}, which has no code: pass the id "
                f"of a plan or a cross-validation strategy.",
                code  = "invalid_argument",
                field = "object_id",
            )
        if entry.code_file is None:
            return CodeResult(id=entry.id, kind=entry.kind, code=entry.code)

        return CodeResult(
            id             = entry.id,
            kind           = entry.kind,
            code           = entry.code[:MAX_CODE_CHARS],
            code_truncated = True,
            files          = {"code": entry.code_file},
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
        _StrictTool.build(get_code, "get_code", (
            "Return the Python code of a plan or a cross-validation strategy."
        ), read_only=True),
        _StrictTool.build(list_objects, "list_objects", (
            "List the ids of the objects the server keeps."
        ), read_only=True),
        _StrictTool.build(describe_object, "describe_object", (
            "Return the response that created an object (summary, links, "
            "notices, files)."
        ), read_only=True),
    ]


def _build_state(
    allow_dir: str | Path,
    output_dir: str | Path | None,
    max_objects: int,
    max_memory_mb: int,
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
    allowed = AllowedDir.from_path(allow_dir)
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

    store = Store(
        max_objects = max_objects,
        max_bytes   = max_memory_mb * 1024 * 1024,
    )

    return _ServerState(
        allowed    = allowed,
        output_dir = output,
        store      = store,
        assistant  = ForecastingAssistant(),
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
        Directory of the files the server writes (long summaries and code).
        It is created if it does not exist. When None, a new temporary
        directory.
    max_objects : int, default 256
        Most objects the server keeps; the least recently used ones are
        removed beyond it.
    max_memory_mb : int, default 1024
        Memory, in MB, the objects may take (an estimate); the least
        recently used ones are removed beyond it.

    Returns
    -------
    server : MCPServer
        Server of the `mcp` package with the tools of skforecast-ai.
    """

    state = _build_state(allow_dir, output_dir, max_objects, max_memory_mb)

    return _build_server(state)


def run_server(
    allow_dir: str | Path,
    output_dir: str | Path | None = None,
    max_objects: int = DEFAULT_MAX_OBJECTS,
    max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
) -> None:
    """
    Run the MCP server of skforecast-ai over stdio until the client closes.

    The working directory of the process becomes `output_dir`, so a library
    that writes files next to it (CatBoost writes `catboost_info/`) does not
    write them into the project of the user.

    Parameters
    ----------
    allow_dir : str, Path
        Directory the server may read data from. Only absolute paths of CSV
        files inside it are accepted, also after resolving symbolic links.
    output_dir : str, Path, default None
        Directory of the files the server writes. It is created if it does
        not exist. When None, a new temporary directory.
    max_objects : int, default 256
        Most objects the server keeps.
    max_memory_mb : int, default 1024
        Memory, in MB, the objects may take (an estimate).

    Returns
    -------
    None
    """

    state = _build_state(allow_dir, output_dir, max_objects, max_memory_mb)
    server = _build_server(state)
    os.chdir(state.output_dir)
    logger.info(
        "skforecast-ai MCP server: reads CSV files in %s, writes files to %s.",
        state.allowed.path,
        state.output_dir,
    )
    server.run("stdio")
