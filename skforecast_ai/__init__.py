"""skforecast-ai: AI-powered forecasting assistant built on skforecast."""

__version__ = "0.1.0"

from .assistant import ForecastingAssistant
from .exceptions import LLMRequiredError
from .generation import generate_code
from .schemas import (
    AnalysisContext,
    AskResult,
    DataProfile,
    ForecasterProfile,
    ForecastPlan,
    GenerateResult,
    PreprocessingStep,
    RunResult,
)

__all__ = [
    "AnalysisContext",
    "AskResult",
    "DataProfile",
    "ForecasterProfile",
    "ForecastingAssistant",
    "ForecastPlan",
    "GenerateResult",
    "LLMRequiredError",
    "PreprocessingStep",
    "RunResult",
    "generate_code",
    "__version__",
]
