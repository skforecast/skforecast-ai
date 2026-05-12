"""skforecast-ai: AI-powered forecasting assistant built on skforecast."""

__version__ = "0.1.0"

from .assistant import ForecastingAssistant
from .exceptions import LLMRequiredError
from .schemas import (
    ForecasterAnalysis,
    AskResult,
    DataProfile,
    ForecasterProfile,
    ForecastPlan,
    GenerateResult,
    PreprocessingStep,
    RunResult,
)

__all__ = [
    "ForecasterAnalysis",
    "AskResult",
    "DataProfile",
    "ForecasterProfile",
    "ForecastingAssistant",
    "ForecastPlan",
    "GenerateResult",
    "LLMRequiredError",
    "PreprocessingStep",
    "RunResult",
    "__version__",
]
