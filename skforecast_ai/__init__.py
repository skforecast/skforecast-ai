"""skforecast-ai: AI-powered forecasting assistant built on skforecast."""

__version__ = "0.1.0"

from .assistant import ForecastingAssistant
from .exceptions import ForecastExecutionError, LLMRequiredError
from .schemas import (
    ForecasterAnalysis,
    AskResult,
    DataProfile,
    ForecasterProfile,
    ForecastPlan,
    GeneratedCode,
    GenerateResult,
    PreprocessingStep,
    RunResult,
)

__all__ = [
    "ForecasterAnalysis",
    "AskResult",
    "DataProfile",
    "ForecastExecutionError",
    "ForecasterProfile",
    "ForecastingAssistant",
    "ForecastPlan",
    "GeneratedCode",
    "GenerateResult",
    "LLMRequiredError",
    "PreprocessingStep",
    "RunResult",
    "__version__",
]
