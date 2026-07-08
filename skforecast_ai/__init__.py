"""skforecast-ai: AI-powered forecasting assistant built on skforecast.

Works with any scikit-learn compatible estimator (LightGBM, XGBoost, CatBoost,
Keras, etc.), statistical models (ARIMA, SARIMAX, ETS, ARAR), and zero-shot
foundation models.

Docs:      https://skforecast.org
Source:    https://github.com/skforecast/skforecast-ai
LLM ref:   https://skforecast.org/latest/llms.txt
LLM full:  https://skforecast.org/latest/llms-full.txt
Examples:  https://skforecast.org/latest/examples/examples_english.html
"""

__version__ = "0.1.0"

from .assistant import ForecastingAssistant
from .exceptions import ForecastExecutionError, LLMRequiredError
from .llm.skills import ALL_SKILLS
from .schemas import (
    AskResult,
    BacktestResult,
    DataProfile,
    ForecastingProfile,
    ForecastPlan,
    RenderedScript,
    CodeGenerationResult,
    PreprocessingStep,
    ForecastResult,
    SeriesPacf,
)

__all__ = [
    "ALL_SKILLS",
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
    "SeriesPacf",
    "__version__",
]
