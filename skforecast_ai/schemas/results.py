################################################################################
#                             Result schemas                                   #
#                                                                              #
# Result schemas: workflow outputs from forecast_code, ask, and forecast       #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import traceback
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, ConfigDict, Field
from .._display import (
    DisplayMixin,
    render_cv_config,
    render_dataframe,
    render_explanation,
    render_metrics,
    render_plan,
    render_profile,
)
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
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str
    profile: ForecastingProfile | None = None
    plan: ForecastPlan | None = None
    code: str | None = None


class ExplainableResult:
    """
    Capability shared by every result that can describe itself to an LLM.

    Mirrors `DisplayMixin`, which lets a result describe itself to a
    terminal. Subclasses must implement `_build_llm_context`, returning
    the context block plus the artifacts `ask()` echoes back on its
    `AskResult`.

    Each result decides its own payload, so an aggregate result (for
    example `ComparisonResult`) can send a compact summary instead of the
    concatenated payloads of everything it wraps.
    """

    def _build_llm_context(
        self, *, send_data: bool
    ) -> LLMContext:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError(
            f"{type(self).__name__} must implement _build_llm_context"
        )

    def to_llm_context(self, *, send_data: bool = False) -> LLMContext:
        """
        Build the LLM context for this result.

        Parameters
        ----------
        send_data : bool, default False
            Whether raw data values may be included. When False, only
            aggregate statistics are shown for row-level data. The
            decision belongs to the caller, so the privacy policy stays
            owned by `ForecastingAssistant`.

        Returns
        -------
        context : LLMContext
            Rendered context block plus the artifacts `ask()` echoes back.
        """

        return self._build_llm_context(send_data=send_data)


class CodeGenerationResult(DisplayMixin, BaseModel):
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
    predictions: Any  # pd.DataFrame
    metrics: Any  # pd.DataFrame | None

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

    def _rich_body(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield render_explanation(self.explanation)
        yield render_cv_config(self.cv_config)
        yield render_metrics(self.metrics, title="Backtest Metrics")
        yield render_dataframe(self.predictions, title="Backtest Predictions")
        yield render_profile(self.profile)
        yield render_plan(self.plan)


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
    """

    profile: ForecastingProfile | None = None
    plan: ForecastPlan | None = None
    code: str | None = None
    explanation: str

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

    `best_name` and `best_candidate` are plain properties rather than
    fields, so the winning `BacktestResult` is not serialized a second
    time by `model_dump()`.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: ForecastingProfile
    cv_config: dict
    results: Any  # pd.DataFrame
    candidates: dict[str, BacktestResult] = Field(min_length=1)
    failures: dict[str, CandidateFailure] = Field(default_factory=dict)
    ranking_metric: str
    explanation: str

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
        yield render_explanation(self.explanation)
        yield render_dataframe(self.results, title="Comparison Results")
