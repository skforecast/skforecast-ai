"""Pydantic AI agent for forecasting Q&A and explanation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from ..schemas import CVParams, ForecastingProfile, ForecastPlan
from .prompts import _CV_ROLE_PROMPT, _STATIC_ROLE_PROMPT
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


# ---------------------------------------------------------------------------
# CV configuration agent (structured output)
# ---------------------------------------------------------------------------


@dataclass
class CVDeps:
    """
    Runtime dependencies for the CV configuration agent.

    Attributes
    ----------
    n_observations : int
        Total number of observations in the dataset.
    frequency : str, None
        Pandas frequency string (e.g. 'D', 'h').
    steps : int
        Forecast horizon (number of steps ahead).
    task_type : str
        Forecasting task type (e.g. 'single_series', 'multi_series').
    lags : int, list, None
        Lag structure from the plan. Used to communicate minimum
        training size constraints.
    """

    n_observations: int
    frequency: str | None
    steps: int
    task_type: str
    lags: int | list | None = None


def create_cv_agent(
    model,
) -> Agent[CVDeps, CVParams]:
    """
    Create a Pydantic AI agent for CV configuration with structured output.

    The agent translates natural-language deployment scenarios into
    `TimeSeriesFold` parameters. It returns a `CVParams` Pydantic model
    (not free text).

    Parameters
    ----------
    model : str, Model
        Pydantic AI model instance or string identifier.

    Returns
    -------
    agent : Agent[CVDeps, CVParams]
        Configured agent that returns structured `CVParams`.
    """
    agent: Agent[CVDeps, CVParams] = Agent(
        model,
        output_type=CVParams,
        deps_type=CVDeps,
        instructions=_CV_ROLE_PROMPT,
        retries=2,
    )

    @agent.instructions
    def _data_context(ctx: RunContext[CVDeps]) -> str:
        """Inject dataset context and skill into dynamic instructions."""
        deps = ctx.deps

        parts: list[str] = []

        # Data context
        parts.append("## Dataset Context")
        parts.append(f"- Total observations: {deps.n_observations}")
        parts.append(f"- Frequency: {deps.frequency or 'unknown'}")
        parts.append(f"- Forecast horizon (steps): {deps.steps}")
        parts.append(f"- Task type: {deps.task_type}")
        if deps.lags is not None:
            max_lag = (
                deps.lags if isinstance(deps.lags, int) else max(deps.lags)
            )
            parts.append(f"- Lags: {deps.lags} (max_lag={max_lag})")
            parts.append(
                f"- Minimum viable initial_train_size: {2 * max_lag}"
            )
        else:
            parts.append(
                f"- Minimum viable initial_train_size: {2 * deps.steps}"
            )
        parts.append(
            f"- Maximum initial_train_size for ≥2 folds: "
            f"{deps.n_observations - 2 * deps.steps}"
        )
        parts.append("")

        # Load backtesting configuration skill
        try:
            skill_content = load_skill("backtesting-configuration")
            parts.append(f"## Reference\n\n{skill_content}")
        except FileNotFoundError:
            logger.warning(
                "Skill 'backtesting-configuration' not found, skipping."
            )

        total_chars = sum(len(p) for p in parts)
        logger.info(
            "CV agent dynamic instructions: ~%d tokens",
            total_chars // 4,
        )

        return "\n".join(parts)

    return agent
