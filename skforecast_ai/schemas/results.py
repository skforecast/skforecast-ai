################################################################################
#                             Result schemas                                   #
#                                                                              #
# Result schemas: workflow outputs from forecast_code, ask, and forecast       #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import traceback
from typing import TYPE_CHECKING, ClassVar
from pydantic import BaseModel, ConfigDict, Field, computed_field
from .._display import (
    DisplayMixin,
    render_cv_config,
    render_dataframe,
    render_explanation,
    render_metrics,
    render_plan,
    render_profile,
)
from ._types import JSONFrame, JSONTimeSeriesFold, OptionalJSONFrame
from .explainable import ExplainableResult
from .plans import ForecastPlan
from .profiles import ForecastingProfile

if TYPE_CHECKING:
    from rich.console import Console, ConsoleOptions, RenderResult


class RenderedScript(BaseModel):
    """
    Structured representation of a rendered forecasting script.

    Splits the rendered script into logical sections so that
    `forecast()` can exec the core logic while `forecast_code()`
    returns the full standalone script.

    Attributes
    ----------
    imports : str
        Import statements required by the script.
    data_loading : str
        Code that loads data from CSV and sets up the index.
    core : str
        Core execution logic (preprocessing, split, fit, predict,
        metrics). Operates on a pre-existing `data` DataFrame variable.
    """

    imports: str
    data_loading: str
    core: str

    @property
    def full_script(self) -> str:
        """Return the complete standalone script (imports + loading + core)."""
        return self.imports + "\n" + self.data_loading + "\n" + self.core

    @property
    def executable(self) -> str:
        """Return code suitable for exec() (imports + core, no CSV loading)."""
        return self.imports + "\n" + self.core


class LLMContext(BaseModel):
    """
    Everything `ask()` needs in order to explain a result object.

    Produced by `ExplainableResult._build_llm_context`. Keeping the four
    fields in a single object means `ask()` never reads a result's own
    attributes, so a new kind of result can be explained without touching
    `ask()`.

    Attributes
    ----------
    text : str
        Rendered plain-text context block inserted into the user message.
    profile : ForecastingProfile, default None
        Profile echoed back on `AskResult` and used to select skills.
    plan : ForecastPlan, default None
        Plan echoed back on `AskResult`.
    code : str, default None
        Generated script echoed back on `AskResult`. When not None,
        `ask()` strips code blocks from the LLM response, since a
        validated script already exists.
    sends_result_values : bool, default True
        Whether `text` ships values the result owns (predictions or
        metrics), which `ask()` sends regardless of `send_data_to_llm`.
        `ask()` emits `DataSentToLLMWarning` only when this is True and
        `send_data_to_llm` is False, so a result that holds no such values
        (for example a generated script) does not warn about data it never
        sends. Defaults to True so a result type that does not declare it
        keeps the warning.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str
    profile: ForecastingProfile | None = None
    plan: ForecastPlan | None = None
    code: str | None = None
    sends_result_values: bool = True


class CodeGenerationResult(DisplayMixin, ExplainableResult, BaseModel):
    """
    Result of the `forecast_code` workflow.

    Attributes
    ----------
    profile : ForecastingProfile
        Profile of the input dataset and high-level modeling decisions.
    plan : ForecastPlan
        Detailed forecasting plan.
    code : str
        Generated Python script.
    """

    profile: ForecastingProfile
    plan: ForecastPlan
    code: str

    def _build_llm_context(self, *, send_data: bool) -> LLMContext:
        """
        Describe the generated script to the LLM.

        Parameters
        ----------
        send_data : bool
            Whether raw data values may be included. Has no effect here:
            a generated script carries no predictions, only the profile
            and plan it was rendered from. The parameter is part of the
            `ExplainableResult` interface.

        Returns
        -------
        context : LLMContext
            Context block covering the dataset, the profile decisions, and
            the plan behind the script.
        """

        # Deferred import: `llm.context` imports from this package, so a
        # module-level import here would be circular.
        from ..llm.context import build_context_message

        # With no predictions, metrics, or cross-validation to report, the
        # single-run composition reduces to the dataset, profile decision,
        # and plan sections.
        return LLMContext(
            text                = build_context_message(
                                      profile=self.profile, plan=self.plan
                                  ),
            profile             = self.profile,
            plan                = self.plan,
            code                = self.code,
            sends_result_values = False,
        )

    def _rich_body(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield render_profile(self.profile)
        yield render_plan(self.plan)


class SingleRunResult(DisplayMixin, ExplainableResult, BaseModel):
    """
    Shared base for the result of a single forecasting or backtesting run.

    Declares the fields that every single run produces, and renders them
    into an LLM context block through `_build_llm_context`. Concrete
    results (for example `ForecastResult` and `BacktestResult`) inherit
    from this class and add the fields specific to them.

    Aggregate results that wrap several runs (for example
    `ComparisonResult`) do not inherit from this class; they implement
    `ExplainableResult` directly so they can send a compact summary rather
    than a concatenation of everything they wrap.

    Every result serializes to JSON with `model_dump(mode="json")` or
    `model_dump_json()`: DataFrames become lists of row records with the
    index as a leading column. `model_dump()` keeps the live DataFrames.

    Attributes
    ----------
    profile : ForecastingProfile
        Profile of the input dataset and high-level modeling decisions.
    plan : ForecastPlan
        Detailed forecasting plan that was executed.
    code : str
        Generated Python script equivalent to the execution.
    predictions : pandas DataFrame
        Forecasted values produced by the run.
    metrics : pandas DataFrame
        Evaluation metrics produced by the run.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: ForecastingProfile
    plan: ForecastPlan
    code: str
    predictions: JSONFrame
    metrics: OptionalJSONFrame

    def _build_llm_context(self, *, send_data: bool) -> LLMContext:
        """
        Describe a single run to the LLM.

        Parameters
        ----------
        send_data : bool
            Whether raw prediction values may be included.

        Returns
        -------
        context : LLMContext
            Context block covering the profile, plan, cross-validation
            configuration, deterministic summary, metrics, and predictions
            of this run.
        """

        # Deferred import: `llm.context` imports from this package, so a
        # module-level import here would be circular.
        from ..llm.context import (
            join_sections,
            render_cv_section,
            render_dataset_section,
            render_deterministic_summary_section,
            render_metrics_section,
            render_plan_section,
            render_predictions_section,
            render_profile_decision_section,
        )

        # Only runs that were cross-validated carry these fields. Sending
        # the deterministic explanation matters: it already states facts
        # such as the fold count, which the LLM would otherwise try to
        # re-derive from the truncated prediction table.
        cv_config = getattr(self, "cv_config", None)
        explanation = getattr(self, "explanation", None)

        return LLMContext(
            text    = join_sections([
                          render_dataset_section(self.profile),
                          render_profile_decision_section(self.profile),
                          render_plan_section(self.plan),
                          render_cv_section(cv_config),
                          render_deterministic_summary_section(explanation),
                          render_metrics_section(
                              self.metrics,
                              has_predictions = self.predictions is not None,
                          ),
                          render_predictions_section(
                              self.predictions, send_data=send_data
                          ),
                      ]),
            profile = self.profile,
            plan    = self.plan,
            code    = self.code,
        )


class ForecastResult(SingleRunResult):
    """
    Result of the `forecast` workflow (executes the pipeline end-to-end).

    Attributes
    ----------
    profile : ForecastingProfile
        Profile of the input dataset and high-level modeling decisions.
    plan : ForecastPlan
        Detailed forecasting plan that was executed.
    code : str
        Generated Python script equivalent to the execution.
    metrics : pandas DataFrame, None
        Evaluation metrics. DataFrame with columns
        `['series', 'MAE', 'MSE', 'MASE']`. For single-series tasks
        this contains one row; for multi-series tasks one row per level.
        None in prediction mode (`test_size=None`), where there is no
        ground truth to evaluate against.
    predictions : pandas DataFrame
        Forecasted values for the requested steps. When prediction
        intervals (or quantiles) are requested, the corresponding
        bound columns are included alongside the point predictions.
    """

    def _rich_body(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield render_profile(self.profile)
        yield render_plan(self.plan)
        if self.metrics is not None:
            yield render_metrics(self.metrics, title="Forecast Metrics")
        yield render_dataframe(self.predictions, title="Predictions")


class BacktestResult(SingleRunResult):
    """
    Result of the `backtest` workflow.

    Attributes
    ----------
    profile : ForecastingProfile
        Profile of the input dataset and high-level modeling decisions.
    plan : ForecastPlan
        Detailed forecasting plan that was executed.
    cv_config : dict
        Resolved `TimeSeriesFold` parameters plus the resulting `n_folds`,
        for traceability.
    metrics : pandas DataFrame
        Backtesting metric values returned by skforecast.
    predictions : pandas DataFrame
        Full backtest predictions across all folds.
    code : str
        Generated Python script reproducing the backtesting workflow.
    explanation : str
        Human-readable explanation of the backtesting configuration
        and results summary.
    """

    cv_config: dict
    explanation: str

    _explanation_title: ClassVar[str] = "Backtest Explanation"

    def _rich_body(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield render_explanation(self.explanation, title="Backtest Explanation")
        yield render_cv_config(self.cv_config)
        yield render_metrics(self.metrics, title="Backtest Metrics")
        yield render_dataframe(self.predictions, title="Backtest Predictions")
        yield render_profile(self.profile)
        yield render_plan(self.plan)


class CVResult(DisplayMixin, ExplainableResult, BaseModel):
    """
    Result of the `create_cv` workflow (a cross-validation strategy).

    Wraps the `TimeSeriesFold` splitter together with the resolved
    parameters, the fold count, the snippet that builds the splitter, and
    the explanation of the choices. Pass it to `backtest()`,
    `backtest_code()` or `compare()` as `cv`, or to `ask()` as `result`.

    Attributes
    ----------
    profile : ForecastingProfile
        Profile of the input dataset and high-level modeling decisions
        the strategy was derived from.
    plan : ForecastPlan
        Forecasting plan the strategy was derived from (its `steps` is the
        fold horizon).
    cv : TimeSeriesFold
        Configured cross-validation fold splitter.
    cv_config : dict
        Resolved `TimeSeriesFold` parameters plus the resulting `n_folds`.
    code : str
        Python snippet that builds the same `TimeSeriesFold`.
    explanation : str
        Human-readable explanation of the chosen configuration. When the
        strategy was derived from a prompt, the LLM reasoning comes first.

    Notes
    -----
    `create_cv()` used to return a `(TimeSeriesFold, str)` tuple. A
    `CVResult` is not iterable, so unpacking it raises a `TypeError` that
    points to the `cv` and `explanation` attributes.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: ForecastingProfile
    plan: ForecastPlan
    cv: JSONTimeSeriesFold
    cv_config: dict
    code: str
    explanation: str

    _explanation_title: ClassVar[str] = "Cross-Validation Explanation"

    def __iter__(self):
        # Pydantic models iterate over (field, value) pairs, which would let
        # the old `cv, explanation = create_cv(...)` silently unpack the
        # wrong things (or fail with a puzzling "too many values" error).
        raise TypeError(
            "`create_cv()` returns a `CVResult`, not a tuple. Use "
            "`result.cv` for the TimeSeriesFold and `result.explanation` "
            "for the explanation, or pass the result itself as `cv` to "
            "`backtest()`, `backtest_code()` or `compare()`."
        )

    def _build_llm_context(self, *, send_data: bool) -> LLMContext:
        """
        Describe the cross-validation strategy to the LLM.

        Parameters
        ----------
        send_data : bool
            Whether raw data values may be included. Has no effect here:
            a strategy carries no predictions or metrics. The parameter is
            part of the `ExplainableResult` interface.

        Returns
        -------
        context : LLMContext
            Context block covering the dataset, the profile decisions, the
            plan, the resolved cross-validation parameters, and the
            deterministic explanation.
        """

        # Deferred import: `llm.context` imports from this package, so a
        # module-level import here would be circular.
        from ..llm.context import build_context_message

        return LLMContext(
            text                = build_context_message(
                                      profile     = self.profile,
                                      plan        = self.plan,
                                      cv_config   = self.cv_config,
                                      explanation = self.explanation,
                                  ),
            profile             = self.profile,
            plan                = self.plan,
            code                = self.code,
            sends_result_values = False,
        )

    def _rich_body(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield render_explanation(self.explanation, title=self._explanation_title)
        yield render_cv_config(self.cv_config)


class AskResult(DisplayMixin, BaseModel):
    """
    Result of the `ask` workflow (requires LLM).

    Attributes
    ----------
    profile : ForecastingProfile, default None
        Profile of the input dataset and high-level modeling decisions,
        if data was provided.
    plan : ForecastPlan, default None
        Detailed forecasting plan, if the agent produced one.
    code : str, default None
        Generated Python script, if the agent produced one.
    explanation : str
        LLM-generated explanation or response.
    skills : list of str, default []
        Names of the skill documents sent to the model, after any
        trimming to fit the context budget. Recorded because the budget
        depends on the profile and context size at call time, so the
        selection cannot be re-derived from the question alone.
    """

    profile: ForecastingProfile | None = None
    plan: ForecastPlan | None = None
    code: str | None = None
    explanation: str
    skills: list[str] = Field(default_factory=list)

    _explanation_title: ClassVar[str] = "Assistant Response"

    def _rich_body(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield render_explanation(self.explanation, title="Assistant Response")


class CandidateFailure(BaseModel):
    """
    Reason why a single `compare()` candidate failed to run.

    Holds a plain-data snapshot of the failure instead of the live
    exception. An exception object keeps its traceback frames alive, and
    those frames reference the execution namespace (which contains a copy
    of the dataset, the fitted forecaster and the predictions), so
    retaining one per failed candidate would pin an unbounded amount of
    memory. The formatted traceback carries the same debugging
    information at a fixed, small cost, and keeps `ComparisonResult`
    serializable.

    Attributes
    ----------
    error_type : str
        Class name of the root-cause exception, for example
        `'ImportError'`.
    message : str
        Message of the root-cause exception.
    traceback : str
        Full formatted traceback of the failure.
    generated_code : str, default None
        Generated script that failed, when the failure happened while
        executing rendered code. `None` for failures raised before
        execution, such as an invalid plan.
    """

    error_type: str
    message: str
    traceback: str
    generated_code: str | None = None

    @classmethod
    def from_exception(cls, exc: Exception) -> CandidateFailure:
        """
        Build a `CandidateFailure` from the exception a candidate raised.

        A `ForecastExecutionError` wraps the generated code and the
        formatted execution traceback; it is unwrapped to its
        `original_error` root cause so the failure reports the underlying
        reason rather than the verbose execution-context message.

        Parameters
        ----------
        exc : Exception
            Exception raised while evaluating a candidate.

        Returns
        -------
        failure : CandidateFailure
            Plain-data snapshot of the failure.
        """

        from ..exceptions import ForecastExecutionError

        if isinstance(exc, ForecastExecutionError):
            root = exc.original_error
            formatted = exc.execution_traceback
            generated_code = exc.generated_code
        else:
            root = exc
            formatted = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
            generated_code = None

        return cls(
            error_type     = type(root).__name__,
            message        = str(root),
            traceback      = formatted,
            generated_code = generated_code,
        )

    def summary(self, max_length: int = 200) -> str:
        """
        Build a concise one-line `"ErrorType: message"` summary.

        Parameters
        ----------
        max_length : int, default 200
            Maximum length of the returned summary. Longer summaries are
            truncated with a trailing ellipsis.

        Returns
        -------
        summary : str
            Single-line summary of the failure.
        """

        lines = [line.strip() for line in self.message.splitlines() if line.strip()]
        first_line = lines[0] if lines else ""
        summary = f"{self.error_type}: {first_line}" if first_line else self.error_type
        if len(summary) > max_length:
            summary = summary[: max_length - 3].rstrip() + "..."

        return summary


class ComparisonResult(DisplayMixin, ExplainableResult, BaseModel):
    """
    Result of the `compare` workflow (ranks several forecasters).

    Backtests several forecaster/estimator configurations with the same
    cross-validation strategy and returns a metric-ranked leaderboard
    plus the winning configuration as a reusable `BacktestResult`.

    Attributes
    ----------
    profile : ForecastingProfile
        Shared profile used for every candidate.
    cv_config : dict
        Resolved `TimeSeriesFold` parameters plus the resulting `n_folds`,
        applied identically to
        every candidate.
    results : pandas DataFrame
        Ranked comparison table, one row per candidate sorted best to
        worst by `ranking_metric`. Columns are
        `['rank', 'name', 'forecaster', 'estimator', <metric columns...>]`,
        plus an `'error'` column when at least one candidate failed.
    candidates : dict
        Mapping of candidate name to the full `BacktestResult` of every
        candidate that ran successfully, ordered best to worst. Never
        empty, so `best_name` and `best_candidate` are always resolvable.
    failures : dict
        Mapping of candidate name to a `CandidateFailure` describing why
        it failed, in the order the candidates were evaluated. Empty when
        every candidate succeeded. Each entry carries the root-cause type
        and message, the full formatted traceback, and the generated code
        that failed.
    ranking_metric : str
        Name of the metric used to sort `results`.
    explanation : str
        Human-readable summary of the comparison.
    best_name : str
        Name of the top-ranked candidate.
    best_candidate : BacktestResult
        Top-ranked candidate. Always present: a comparison in which every
        candidate fails raises `AllCandidatesFailedError` instead of
        returning a result.

    Notes
    -----
    Every candidate name appears in exactly one of `candidates` and
    `failures`, never in both and never in neither. The two mappings
    therefore partition the candidates that were evaluated, and their
    union matches the `'name'` column of `results`.

    `best_name` is a computed field, so it is included by `model_dump()`;
    `best_candidate` is a plain property, so the winning `BacktestResult`
    is not serialized a second time.

    Every result serializes to JSON with `model_dump(mode="json")` or
    `model_dump_json()`: DataFrames become lists of row records with the
    index as a leading column. `model_dump()` keeps the live DataFrames.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: ForecastingProfile
    cv_config: dict
    results: JSONFrame
    candidates: dict[str, BacktestResult] = Field(min_length=1)
    failures: dict[str, CandidateFailure] = Field(default_factory=dict)
    ranking_metric: str
    explanation: str

    _explanation_title: ClassVar[str] = "Comparison Explanation"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def best_name(self) -> str:
        """Return the name of the top-ranked candidate."""
        return next(iter(self.candidates))

    @property
    def best_candidate(self) -> BacktestResult:
        """Return the `BacktestResult` of the top-ranked candidate."""
        return self.candidates[self.best_name]

    def _build_llm_context(self, *, send_data: bool) -> LLMContext:
        """
        Describe the comparison to the LLM.

        Sends the leaderboard, the shared profile and cross-validation
        strategy, one line per failure, and the winning candidate's plan.
        The non-winning candidates' plans, code, and predictions are
        withheld: the leaderboard already carries the numbers a ranking
        question needs, so the payload does not grow with the number of
        candidates. A specific candidate can still be explained by passing
        `candidates['<name>']` to `ask()` directly.

        Parameters
        ----------
        send_data : bool
            Whether raw data values may be included. Has no effect here:
            a comparison renders aggregated leaderboard metrics only,
            never row-level predictions. The parameter is part of the
            `ExplainableResult` interface.

        Returns
        -------
        context : LLMContext
            Context block for the comparison. The echoed `plan` and `code`
            are the winning candidate's, since that is the actionable
            output of a comparison.
        """

        # Deferred import: `llm.context` imports from this package, so a
        # module-level import here would be circular.
        from ..llm.context import build_comparison_context

        best = self.best_candidate

        return LLMContext(
            text    = build_comparison_context(self),
            profile = self.profile,
            plan    = best.plan,
            code    = best.code,
        )

    def _rich_body(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield render_explanation(self.explanation, title="Comparison Explanation")
        yield render_dataframe(self.results, title="Comparison Results")
