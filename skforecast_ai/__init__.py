"""skforecast-ai: AI-powered forecasting assistant built on skforecast."""

__version__ = "0.1.0"

from .assistant import ForecastingAssistant
from .exceptions import ForecastExecutionError, LLMRequiredError
from .llm.skills import ALL_SKILLS
from .schemas import (
    ForecastingAnalysis,
    AskResult,
    DataProfile,
    ForecastingProfile,
    ForecastPlan,
    GeneratedCode,
    CodeGenerationResult,
    PreprocessingStep,
    ForecastResult,
)

__all__ = [
    "ALL_SKILLS",
    "ForecastingAnalysis",
    "AskResult",
    "DataProfile",
    "ForecastExecutionError",
    "ForecastingProfile",
    "ForecastingAssistant",
    "ForecastPlan",
    "GeneratedCode",
    "CodeGenerationResult",
    "LLMRequiredError",
    "PreprocessingStep",
    "ForecastResult",
    "__version__",
]
