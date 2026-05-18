"""LLM provider abstraction for skforecast-ai."""

from .prompts import (
    build_context_message,
    build_system_prompt,
    load_llms_reference,
    load_skill,
)
from .provider import check_ollama_reachable, create_model, parse_model_string

__all__ = [
    "build_context_message",
    "build_system_prompt",
    "check_ollama_reachable",
    "create_model",
    "load_llms_reference",
    "load_skill",
    "parse_model_string",
]


def _lazy_import_agent():
    """Lazy import to avoid requiring pydantic-ai for Tier 0 mode."""
    from .agent import create_forecasting_agent

    return create_forecasting_agent


def __getattr__(name):
    if name == "create_forecasting_agent":
        return _lazy_import_agent()
    raise AttributeError(f"module 'skforecast_ai.llm' has no attribute {name!r}")
