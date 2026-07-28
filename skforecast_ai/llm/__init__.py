"""LLM provider abstraction for skforecast-ai."""

from .context import (
    build_comparison_context,
    build_context_message,
    join_sections,
    render_comparison_overview_section,
    render_cv_section,
    render_dataset_section,
    render_deterministic_summary_section,
    render_failures_section,
    render_leaderboard_section,
    render_metrics_section,
    render_plan_section,
    render_predictions_section,
    render_profile_decision_section,
    render_winning_candidate_section,
)
from .provider import create_model, ensure_ollama_reachable, parse_model_string
from .skills import (
    ALL_SKILLS,
    compute_skill_token_budget,
    estimate_context_tokens,
    estimate_prompt_tokens,
    load_llms_reference,
    load_skill,
    select_skills,
)

__all__ = [
    "ALL_SKILLS",
    "build_comparison_context",
    "build_context_message",
    "compute_skill_token_budget",
    "create_model",
    "ensure_ollama_reachable",
    "estimate_context_tokens",
    "estimate_prompt_tokens",
    "join_sections",
    "load_llms_reference",
    "load_skill",
    "parse_model_string",
    "render_comparison_overview_section",
    "render_cv_section",
    "render_dataset_section",
    "render_deterministic_summary_section",
    "render_failures_section",
    "render_leaderboard_section",
    "render_metrics_section",
    "render_plan_section",
    "render_predictions_section",
    "render_profile_decision_section",
    "render_winning_candidate_section",
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


def _lazy_import_plan_refinement_agent():
    """Lazy import for plan refinement agent."""
    from .agent import PlanRefinementDeps, create_plan_refinement_agent

    return create_plan_refinement_agent, PlanRefinementDeps


def __getattr__(name):
    if name in ("create_forecasting_agent", "AskDeps"):
        create_forecasting_agent, AskDeps = _lazy_import_agent()
        if name == "create_forecasting_agent":
            return create_forecasting_agent
        return AskDeps
    if name in ("create_plan_refinement_agent", "PlanRefinementDeps"):
        create_plan_refinement_agent, PlanRefinementDeps = _lazy_import_plan_refinement_agent()
        if name == "create_plan_refinement_agent":
            return create_plan_refinement_agent
        return PlanRefinementDeps
    raise AttributeError(f"module 'skforecast_ai.llm' has no attribute {name!r}")
