"""Result schemas: workflow outputs from forecast_code, ask, and forecast."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from .plans import ForecastPlan
from .profiles import ForecastingProfile


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


class CodeGenerationResult(BaseModel):
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


class AskResult(BaseModel):
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


class ForecastResult(BaseModel):
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
    metrics : pandas DataFrame
        Evaluation metrics. DataFrame with columns
        `['series', 'MAE', 'MSE', 'MASE']`. For single-series tasks
        this contains one row; for multi-series tasks one row per level.
    predictions : pandas DataFrame
        Forecasted values for the requested steps.
    intervals : pandas DataFrame, default None
        Prediction intervals or quantile predictions when available.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: ForecastingProfile
    plan: ForecastPlan
    code: str
    metrics: Any  # pd.DataFrame
    predictions: Any  # pd.DataFrame
    intervals: Any = None  # pd.DataFrame | None


class BacktestResult(BaseModel):
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

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: ForecastingProfile
    plan: ForecastPlan
    cv_config: dict
    metrics: Any  # pd.DataFrame
    predictions: Any  # pd.DataFrame
    code: str
    explanation: str
