################################################################################
#                             Result schemas                                   #
#                                                                              #
# Result schemas: workflow outputs from forecast_code, ask, and forecast       #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, ConfigDict
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


class WorkflowResult(DisplayMixin, BaseModel):
    """
    Base for workflow results that `ask()` can explain.

    Declares the superset of optional fields that `ask()` reads from a
    result object. Concrete workflow results (for example `ForecastResult`
    and `BacktestResult`) inherit from this class and tighten the fields
    they always populate. `ask()` consumes these fields structurally, so
    adding a new workflow result requires no changes to `ask()`.

    Attributes
    ----------
    profile : ForecastingProfile, default None
        Profile of the input dataset and high-level modeling decisions.
    plan : ForecastPlan, default None
        Detailed forecasting plan that was executed.
    code : str, default None
        Generated Python script equivalent to the execution.
    predictions : pandas DataFrame, default None
        Forecasted values produced by the workflow.
    metrics : pandas DataFrame, default None
        Evaluation metrics produced by the workflow.
    cv_config : dict, default None
        Resolved cross-validation parameters, when applicable.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: ForecastingProfile | None = None
    plan: ForecastPlan | None = None
    code: str | None = None
    predictions: Any = None  # pd.DataFrame | None
    metrics: Any = None  # pd.DataFrame | None
    cv_config: dict | None = None


class ForecastResult(WorkflowResult):
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

    profile: ForecastingProfile
    plan: ForecastPlan
    code: str
    metrics: Any  # pd.DataFrame | None
    predictions: Any  # pd.DataFrame

    def _rich_body(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield render_profile(self.profile)
        yield render_plan(self.plan)
        if self.metrics is not None:
            yield render_metrics(self.metrics, title="Forecast Metrics")
        yield render_dataframe(self.predictions, title="Predictions")


class BacktestResult(WorkflowResult):
    """
    Result of the `backtest` workflow.

    Attributes
    ----------
    profile : ForecastingProfile
        Profile of the input dataset and high-level modeling decisions.
    plan : ForecastPlan
        Detailed forecasting plan that was executed.
    cv_config : dict
        Resolved `TimeSeriesFold` parameters for traceability.
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

    profile: ForecastingProfile
    plan: ForecastPlan
    cv_config: dict
    metrics: Any  # pd.DataFrame
    predictions: Any  # pd.DataFrame
    code: str
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
