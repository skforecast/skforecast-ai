"""skforecast-ai: AI-powered forecasting assistant built on skforecast."""

__version__ = "0.1.0"

from .assistant import ForecastingAssistant
from .exceptions import ForecastExecutionError, LLMRequiredError
from .llm.skills import ALL_SKILLS
from .schemas import (
    ForecastingAnalysis,
    AskResult,
    BacktestResult,
    DataProfile,
    ForecastingProfile,
    ForecastPlan,
    RenderedScript,
    CodeGenerationResult,
    PreprocessingStep,
    ForecastResult,
)

__all__ = [
    "ALL_SKILLS",
    "ForecastingAnalysis",
    "AskResult",
    "BacktestResult",
    "DataProfile",
    "ForecastExecutionError",
    "ForecastingProfile",
    "ForecastingAssistant",
    "ForecastPlan",
    "RenderedScript",
    "CodeGenerationResult",
    "LLMRequiredError",
    "PreprocessingStep",
    "ForecastResult",
    "__version__",
]
