"""Pydantic AI agent for forecasting Q&A and explanation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from ..schemas import ForecastingProfile, ForecastPlan
from .prompts import _STATIC_ROLE_PROMPT
from .skills import load_llms_reference, load_skill, select_skills

logger = logging.getLogger(__name__)


@dataclass
class AskDeps:
    """
    Runtime dependencies for the forecasting ask agent.

    Carries all per-call context needed by dynamic instructions.

    Attributes
    ----------
    profile : ForecastingProfile, None
        The profiled dataset/forecaster info. None in Q&A mode.
    plan : ForecastPlan, None
        The generated forecast plan. None in Q&A mode.
    question : str
        The user's natural-language question.
    include_reference : bool
        Whether to append the API reference to instructions.
    skills_override : list of str, None
        Explicit skill list. When set, bypasses dynamic selection.
    """

    profile: ForecastingProfile | None
    plan: ForecastPlan | None
    question: str
    include_reference: bool = False
    skills_override: list[str] | None = None


def create_forecasting_agent(
    model,
) -> Agent[AskDeps, str]:
    """
    Create a Pydantic AI agent for forecasting Q&A and explanation.

    The agent uses pydantic-ai's `instructions` mechanism:

    - **Static instructions** (constructor): The role prompt (~200 tokens).
    Auto-sorted first by pydantic-ai for prompt-cache optimization.
    - **Dynamic instructions** (decorator): Skills and optional reference,
    selected per-call based on `AskDeps`.

    The agent is a lightweight natural-language layer. It does NOT make
    forecasting decisions or call tools. All recommendations come from
    deterministic code; the agent only explains or answers questions.

    Parameters
    ----------
    model : str, Model
        Pydantic AI model instance or string identifier. Typically
        produced by `create_model()` from the provider module.

    Returns
    -------
    agent : Agent[AskDeps, str]
        Configured Pydantic AI agent that returns free-text responses.
        Pass `deps=AskDeps(...)` when calling `run_sync()`.
    """
    agent: Agent[AskDeps, str] = Agent(
        model,
        output_type=str,
        deps_type=AskDeps,
        instructions=_STATIC_ROLE_PROMPT,
        retries=2,
    )

    @agent.instructions
    def _dynamic_skills_and_reference(ctx: RunContext[AskDeps]) -> str:
        """Select and load skills + optional reference based on deps."""
        deps = ctx.deps

        # Resolve skill list
        if deps.skills_override is not None:
            skill_names = deps.skills_override
            logger.debug("Using skills_override: %s", skill_names)
        else:
            task_type = (
                deps.profile.task_type
                if deps.profile is not None
                else None
            )
            skill_names = select_skills(
                task_type=task_type,
                question=deps.question,
            )
            logger.debug("Dynamic skill selection: %s", skill_names)

        # Build skills content
        parts: list[str] = []
        for name in skill_names:
            try:
                parts.append(f"### {name}\n\n{load_skill(name)}")
            except FileNotFoundError:
                logger.warning("Skill '%s' not found, skipping.", name)
                continue

        # Optionally append API reference
        if deps.include_reference:
            try:
                ref = load_llms_reference()
                parts.append(f"## Skforecast API Reference\n\n{ref}")
                logger.debug("API reference included.")
            except FileNotFoundError:
                logger.warning("API reference file not found, skipping.")

        # Conditional no-code reinforcement (Explain/Results mode only)
        if deps.plan is not None:
            parts.append(
                "---\n"
                "REMINDER: Do NOT output code blocks. The user already has a "
                "validated script in `result.code`. Focus on explaining the "
                "strategy, parameters, and results in plain language."
            )

        total_chars = sum(len(p) for p in parts)
        logger.info(
            "Dynamic instructions: %d skills loaded, ~%d tokens",
            len(skill_names),
            total_chars // 4,
        )

        return "\n\n".join(parts)

    return agent
