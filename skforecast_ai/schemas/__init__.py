"""Pydantic schemas for skforecast-ai data contracts."""

from .plans import (
    CANDIDATE_CONFIG_KEYS,
    REFINE_PLAN_OVERRIDE_KEYS,
    CandidateConfig,
    CVParams,
    ForecastPlan,
    PlanOverrides,
    PreprocessingStep,
    RefinePlanOverrides,
)
from .profiles import DataProfile, ForecastingProfile, SeriesLengthInfo, SeriesPacf
from .results import (
    AskResult,
    BacktestResult,
    CandidateFailure,
    CodeGenerationResult,
    ComparisonResult,
    CVResult,
    ExplainableResult,
    ForecastResult,
    LLMContext,
    RenderedScript,
    SingleRunResult,
)

__all__ = [
    "CANDIDATE_CONFIG_KEYS",
    "REFINE_PLAN_OVERRIDE_KEYS",
    "AskResult",
    "BacktestResult",
    "CandidateConfig",
    "CandidateFailure",
    "CodeGenerationResult",
    "ComparisonResult",
    "CVParams",
    "CVResult",
    "DataProfile",
    "ExplainableResult",
    "ForecastingProfile",
    "ForecastPlan",
    "ForecastResult",
    "LLMContext",
    "PlanOverrides",
    "PreprocessingStep",
    "RefinePlanOverrides",
    "RenderedScript",
    "SeriesLengthInfo",
    "SeriesPacf",
    "SingleRunResult",
]
