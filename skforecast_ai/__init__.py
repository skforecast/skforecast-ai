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

__version__ = "0.4.1"

# Aliased so they do not show up as public names of the package.
import importlib as _importlib
import typing as _typing

from .exceptions import (
    AllCandidatesFailedError,
    CandidateFailedWarning,
    DataContentError,
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

# The other public names are imported on first access (PEP 562), not here:
# the assistant loads pandas, scikit-learn, scipy and skforecast, and the
# MCP server (`skforecast-ai mcp`) answers the handshake of its client
# before it needs any of them. `from skforecast_ai import ForecastingAssistant`,
# `skforecast_ai.ForecastingAssistant` and `from skforecast_ai import *` work
# as before. The imports below are only read by type checkers and editors.
if _typing.TYPE_CHECKING:
    from .assistant import ForecastingAssistant
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

# Submodules that importing the package loaded before the names were
# imported on first access, so `import skforecast_ai` followed by
# `skforecast_ai.schemas.ForecastPlan` still works. Others (`mcp`, `cli`)
# need their own import, as before.
_LAZY_SUBMODULES = frozenset({
    "_constants", "_dates", "_display", "_foundation", "_future_exog",
    "_last_window", "_utils", "_validation", "assistant", "execution", "llm",
    "profiling", "recommendation", "rendering", "schemas",
})

# Module of each name imported on first access, relative to this package.
_LAZY_NAMES = {
    "ForecastingAssistant": ".assistant",
    "ALL_SKILLS": ".llm.skills",
    "AskResult": ".schemas",
    "BacktestResult": ".schemas",
    "CandidateFailure": ".schemas",
    "CompareProgress": ".schemas",
    "ComparisonResult": ".schemas",
    "CVResult": ".schemas",
    "DataProfile": ".schemas",
    "ExplainableResult": ".schemas",
    "ForecastingProfile": ".schemas",
    "ForecastPlan": ".schemas",
    "LLMCheckResult": ".schemas",
    "LLMContext": ".schemas",
    "RenderedScript": ".schemas",
    "CodeGenerationResult": ".schemas",
    "PreprocessingStep": ".schemas",
    "ForecastResult": ".schemas",
    "SeriesPacf": ".schemas",
    "SingleRunResult": ".schemas",
}

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
    "DataContentError",
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


def __getattr__(name: str) -> object:
    """
    Import a public name, or a submodule the package used to load with it,
    on first access and keep it in the namespace of the package, so later
    accesses do not come back here.

    Parameters
    ----------
    name : str
        Name looked up on the package.

    Returns
    -------
    value : object
        The class, object or submodule of that name.
    """

    if name in _LAZY_SUBMODULES:
        # Importing a submodule also sets it as an attribute of the package.
        return _importlib.import_module(f".{name}", __name__)
    module = _LAZY_NAMES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_importlib.import_module(module, __name__), name)
    globals()[name] = value

    return value


def __dir__() -> list[str]:
    """
    Names of the package, with the public names not imported yet.

    Returns
    -------
    names : list of str
        Sorted names of the namespace and of `__all__`.
    """

    return sorted(set(globals()) | set(__all__))
