"""Pydantic AI agent for forecasting Q&A and explanation."""

from __future__ import annotations

from pydantic_ai import Agent

from .prompts import build_system_prompt


def create_forecasting_agent(
    model,
    skills: list[str] | None = None,
    include_reference: bool = False,
) -> Agent[None, str]:
    """
    Create a Pydantic AI agent for forecasting Q&A and explanation.

    The agent is a lightweight natural-language layer. It does NOT make
    forecasting decisions or call tools. All recommendations come from
    deterministic code; the agent only explains or answers questions.

    Parameters
    ----------
    model : str, Model
        Pydantic AI model instance or string identifier. Typically
        produced by `create_model()` from the provider module.
    skills : list, default None
        List of skill names to include in the system prompt. If None,
        the default skill set is loaded.
    include_reference : bool, default False
        Whether to include the `llms-full.txt` API reference in the
        system prompt.

    Returns
    -------
    agent : Agent[None, str]
        Configured Pydantic AI agent that returns free-text responses.
    """
    system_prompt = build_system_prompt(
        skills=skills,
        include_reference=include_reference,
    )

    return Agent(
        model,
        output_type=str,
        system_prompt=system_prompt,
        retries=2,
    )
