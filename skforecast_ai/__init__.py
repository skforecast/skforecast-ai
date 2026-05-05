"""skforecast-ai: AI-powered forecasting assistant built on skforecast."""

__version__ = "0.1.0"

from .assistant import ForecastingAssistant
from .exceptions import LLMRequiredError
from .generation import generate_code
from .recommendation import recommend_plan
from .schemas import (
    AnalysisContext,
    AskResult,
    DataProfile,
    ForecastPlan,
    GenerateResult,
    PreprocessingStep,
    RecommendResult,
    RunResult,
)

__all__ = [
    "AnalysisContext",
    "AskResult",
    "DataProfile",
    "ForecastingAssistant",
    "ForecastPlan",
    "GenerateResult",
    "LLMRequiredError",
    "PreprocessingStep",
    "RecommendResult",
    "RunResult",
    "generate_code",
    "recommend_plan",
    "__version__",
]
