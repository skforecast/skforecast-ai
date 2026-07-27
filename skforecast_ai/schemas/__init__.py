"""Pydantic schemas for skforecast-ai data contracts."""

from .plans import CVParams, ForecastPlan, PreprocessingStep, PlanOverrides
from .profiles import DataProfile, ForecastingProfile, SeriesLengthInfo, SeriesPacf
from .results import (
    AskResult,
    BacktestResult,
    CandidateFailure,
    CodeGenerationResult,
    ComparisonResult,
    ExplainableResult,
    ForecastResult,
    LLMContext,
    RenderedScript,
    SingleRunResult,
)

__all__ = [
    "AskResult",
    "BacktestResult",
    "CandidateFailure",
    "CodeGenerationResult",
    "ComparisonResult",
    "CVParams",
    "DataProfile",
    "ExplainableResult",
    "ForecastingProfile",
    "ForecastPlan",
    "ForecastResult",
    "LLMContext",
    "PlanOverrides",
    "PreprocessingStep",
    "RenderedScript",
    "SeriesLengthInfo",
    "SeriesPacf",
    "SingleRunResult",
]
