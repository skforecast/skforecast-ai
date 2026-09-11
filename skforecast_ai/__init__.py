"""skforecast-ai: AI-powered forecasting assistant built on skforecast.

Works with any scikit-learn compatible estimator (LightGBM, XGBoost, CatBoost,
Keras, etc.), statistical models (ARIMA, SARIMAX, ETS, ARAR), and zero-shot
foundation models.

Docs:      https://ai.skforecast.org
Source:    https://github.com/skforecast/skforecast-ai
LLM ref:   https://skforecast.org/latest/llms.txt
LLM full:  https://skforecast.org/latest/llms-full.txt
Examples:  https://skforecast.org/latest/examples/examples_english.html
"""

__version__ = "0.3.1"

from .assistant import ForecastingAssistant
from .exceptions import (
    AllCandidatesFailedError,
    CandidateFailedWarning,
    DataSentToLLMWarning,
    ForecastExecutionError,
    LLMCallError,
    LLMRequiredError,
    UnrecommendedForecasterWarning,
)
from .llm.skills import ALL_SKILLS
from .schemas import (
    AskResult,
    BacktestResult,
    CandidateFailure,
    ComparisonResult,
    CVResult,
    DataProfile,
    ExplainableResult,
    ForecastingProfile,
    ForecastPlan,
    LLMCheckResult,
    LLMContext,
    RenderedScript,
    CodeGenerationResult,
    PreprocessingStep,
    ForecastResult,
    SeriesPacf,
    SingleRunResult,
)

__all__ = [
    "ALL_SKILLS",
    "AllCandidatesFailedError",
    "AskResult",
    "BacktestResult",
    "CandidateFailedWarning",
    "CandidateFailure",
    "ComparisonResult",
    "CVResult",
    "DataProfile",
    "DataSentToLLMWarning",
    "ExplainableResult",
    "ForecastExecutionError",
    "ForecastingProfile",
    "ForecastingAssistant",
    "ForecastPlan",
    "LLMCheckResult",
    "LLMContext",
    "RenderedScript",
    "CodeGenerationResult",
    "LLMCallError",
    "LLMRequiredError",
    "PreprocessingStep",
    "ForecastResult",
    "SeriesPacf",
    "SingleRunResult",
    "UnrecommendedForecasterWarning",
    "__version__",
]
