"""LLM provider abstraction for skforecast-ai."""

from .context import build_context_message
from .provider import create_model, ensure_ollama_reachable, parse_model_string
from .skills import (
    ALL_SKILLS,
    estimate_prompt_tokens,
    load_llms_reference,
    load_skill,
    select_skills,
)

__all__ = [
    "ALL_SKILLS",
    "build_context_message",
    "create_model",
    "ensure_ollama_reachable",
    "estimate_prompt_tokens",
    "load_llms_reference",
    "load_skill",
    "parse_model_string",
    "select_skills",
]


def _lazy_import_agent():
    """Lazy import to avoid requiring pydantic-ai for Tier 0 mode."""
    from .agent import AskDeps, create_forecasting_agent

    return create_forecasting_agent, AskDeps


def _lazy_import_cv_agent():
    """Lazy import for CV configuration agent."""
    from .agent import CVDeps, create_cv_agent

    return create_cv_agent, CVDeps


def __getattr__(name):
    if name in ("create_forecasting_agent", "AskDeps"):
        create_forecasting_agent, AskDeps = _lazy_import_agent()
        if name == "create_forecasting_agent":
            return create_forecasting_agent
        return AskDeps
    raise AttributeError(f"module 'skforecast_ai.llm' has no attribute {name!r}")
