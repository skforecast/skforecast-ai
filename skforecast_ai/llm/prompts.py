"""System prompts, skill loader, and prompt builders for the LLM agent."""

from __future__ import annotations

from pathlib import Path

from ..schemas import ForecasterProfile, ForecastPlan

_PACKAGE_DIR = Path(__file__).resolve().parent.parent
_REPO_DIR = _PACKAGE_DIR.parent
_SKILLS_DIR = _REPO_DIR / "skills"
_RESOURCES_DIR = _PACKAGE_DIR / "resources"

ALL_SKILLS = [
    "choosing-a-forecaster",
    "complete-api-reference",
    "deep-learning-forecasting",
    "drift-detection",
    "feature-engineering",
    "feature-selection",
    "forecasting-multiple-series",
    "forecasting-single-series",
    "foundation-forecasting",
    "hyperparameter-optimization",
    "prediction-intervals",
    "statistical-models",
    "troubleshooting-common-errors",
]

DEFAULT_SKILLS = [
    "choosing-a-forecaster",
    "forecasting-single-series",
    "forecasting-multiple-series",
]

_SYSTEM_PROMPT_TEMPLATE = """\
You are a forecasting assistant built on skforecast. Your role is to \
explain forecasting concepts, answer questions about skforecast, and \
describe pre-computed forecasting plans in plain language.

## Core Rules

1. You NEVER make forecasting decisions yourself. All recommendations \
come from deterministic code outside your control.
2. You explain pre-computed outputs (ForecasterProfile, ForecastPlan) \
in plain language when context is provided in the user message.
3. You answer general questions about time series forecasting and the \
skforecast library using the skills and reference below.
4. Every recommendation must be reproducible from deterministic Python code.
5. If you cannot validate something, warn the user explicitly.
6. Be concise and focus on practical guidance.

## Skills Reference

{skills_content}

## Skforecast API Reference

{reference_content}
"""

def load_skill(skill_name: str) -> str:
    """
    Load a skill's SKILL.md content and its references.

    Parameters
    ----------
    skill_name : str
        Name of the skill directory under `skforecast_ai/skills/`.

    Returns
    -------
    content : str
        Full text of the SKILL.md file concatenated with any reference
        files found in the skill's `references/` subdirectory.
    """
    skill_dir = _SKILLS_DIR / skill_name

    if not skill_dir.exists():
        raise FileNotFoundError(
            f"Skill '{skill_name}' not found. "
            f"Expected directory: {skill_dir}"
        )

    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        raise FileNotFoundError(
            f"SKILL.md not found for skill '{skill_name}'. "
            f"Expected file: {skill_file}"
        )

    content = skill_file.read_text(encoding="utf-8")

    references_dir = skill_dir / "references"
    if references_dir.exists() and references_dir.is_dir():
        for ref_file in sorted(references_dir.iterdir()):
            if ref_file.is_file():
                ref_content = ref_file.read_text(encoding="utf-8")
                content += f"\n\n---\n\n## Reference: {ref_file.name}\n\n{ref_content}"

    return content


def load_llms_reference() -> str:
    """
    Load the skforecast API reference text.

    Returns
    -------
    content : str
        Full text of `skforecast_ai/resources/llms-full.txt`.
    """
    ref_file = _RESOURCES_DIR / "llms-full.txt"

    if not ref_file.exists():
        raise FileNotFoundError(
            f"LLM reference file not found. Expected: {ref_file}"
        )

    return ref_file.read_text(encoding="utf-8")


def build_system_prompt(
    skills: list[str] | None = None,
    include_reference: bool = True,
) -> str:
    """
    Assemble the system prompt from skills and API reference.

    Parameters
    ----------
    skills : list, default None
        List of skill names to include. If None, all available skills
        are loaded.
    include_reference : bool, default True
        Whether to include the `llms-full.txt` API reference content.

    Returns
    -------
    prompt : str
        Complete system prompt string ready for agent configuration.
    """
    skill_names = skills if skills is not None else DEFAULT_SKILLS

    skills_parts = []
    for name in skill_names:
        try:
            skill_content = load_skill(name)
            skills_parts.append(f"### {name}\n\n{skill_content}")
        except FileNotFoundError:
            continue

    skills_content = "\n\n".join(skills_parts) if skills_parts else "(No skills loaded)"

    if include_reference:
        try:
            reference_content = load_llms_reference()
        except FileNotFoundError:
            reference_content = "(Reference file not available)"
    else:
        reference_content = "(Reference not included)"

    return _SYSTEM_PROMPT_TEMPLATE.format(
        skills_content=skills_content,
        reference_content=reference_content,
    )


def build_context_message(
    forecaster_profile: ForecasterProfile | None = None,
    plan: ForecastPlan | None = None,
) -> str:
    """
    Serialize a profile and/or plan into a context block for the LLM.

    Produces a concise plain-text summary suitable for inclusion in the
    user message so the LLM can explain or discuss the deterministic
    outputs without needing tool access.

    Parameters
    ----------
    forecaster_profile : ForecasterProfile, default None
        High-level profile of the forecasting problem.
    plan : ForecastPlan, default None
        Detailed forecasting plan.

    Returns
    -------
    context : str
        Plain-text context block. Empty string if both arguments are
        None.
    """
    if forecaster_profile is None and plan is None:
        return ""

    parts: list[str] = []

    if forecaster_profile is not None:
        dp = forecaster_profile.data_profile
        parts.append("## Data & Profile Summary")
        parts.append(f"- Observations: {dp.n_observations}")
        parts.append(f"- Series: {dp.n_series}")
        parts.append(f"- Frequency: {dp.frequency or 'unknown'}")
        parts.append(f"- Target: {dp.target}")
        exog = ", ".join(dp.exog_columns) if dp.exog_columns else "none"
        parts.append(f"- Exogenous columns: {exog}")
        if dp.warnings:
            parts.append(f"- Warnings: {'; '.join(dp.warnings)}")
        parts.append(f"- Task type: {forecaster_profile.task_type}")
        parts.append(f"- Forecaster: {forecaster_profile.forecaster}")
        parts.append(f"- Estimator: {forecaster_profile.estimator or 'none'}")
        parts.append(f"- Explanation: {forecaster_profile.explanation}")

    if plan is not None:
        parts.append("")
        parts.append("## Forecast Plan")
        parts.append(f"- Forecaster: {plan.forecaster}")
        parts.append(f"- Estimator: {plan.estimator or 'none'}")
        parts.append(f"- Steps: {plan.steps}")
        parts.append(f"- Forecaster kwargs: {plan.forecaster_kwargs}")
        parts.append(f"- Interval method: {plan.interval_method or 'none'}")
        parts.append(f"- Use exog: {plan.use_exog}")
        parts.append(f"- Explanation: {plan.explanation}")

    return "\n".join(parts)
