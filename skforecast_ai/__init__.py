"""skforecast-ai: Python time series forecasting assistant built on skforecast.

Works with any scikit-learn compatible estimator (LightGBM, XGBoost, CatBoost,
Keras, etc.), statistical models (ARIMA, SARIMAX, ETS, ARAR), and zero-shot
foundation models.

Docs:      https://ai.skforecast.org
Source:    https://github.com/skforecast/skforecast-ai
LLM ref:   https://skforecast.org/latest/llms.txt
LLM full:  https://skforecast.org/latest/llms-full.txt
Examples:  https://skforecast.org/latest/examples/examples_english.html
"""

__version__ = "0.4.0"

from .assistant import ForecastingAssistant
from .exceptions import (
    AllCandidatesFailedError,
    CandidateFailedWarning,
    DataNotFoundError,
    DataSentToLLMWarning,
    ForecastExecutionError,
    InvalidInputError,
    InvalidInputTypeError,
    LLMCallError,
    LLMRequiredError,
    MissingBackendWarning,
    PlanEditsDiscardedWarning,
    SkforecastAIError,
    UnrecommendedForecasterWarning,
)
from .llm.skills import ALL_SKILLS
from .schemas import (
    AskResult,
    BacktestResult,
    CandidateFailure,
    CompareProgress,
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
    "CompareProgress",
    "ComparisonResult",
    "CVResult",
    "DataNotFoundError",
    "DataProfile",
    "DataSentToLLMWarning",
    "ExplainableResult",
    "ForecastExecutionError",
    "ForecastingProfile",
    "ForecastingAssistant",
    "ForecastPlan",
    "InvalidInputError",
    "InvalidInputTypeError",
    "LLMCheckResult",
    "LLMContext",
    "RenderedScript",
    "CodeGenerationResult",
    "LLMCallError",
    "LLMRequiredError",
    "MissingBackendWarning",
    "PlanEditsDiscardedWarning",
    "PreprocessingStep",
    "ForecastResult",
    "SeriesPacf",
    "SingleRunResult",
    "SkforecastAIError",
    "UnrecommendedForecasterWarning",
    "__version__",
]
