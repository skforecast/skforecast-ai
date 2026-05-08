"""System prompts, skill loader, and prompt builders for the LLM agent."""

from pathlib import Path

from ..schemas import DataProfile, ForecastPlan

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
You are a forecasting assistant built on skforecast. Your role is to help \
users build accurate time series forecasting pipelines.

## Core Rules

1. You NEVER make forecasting decisions yourself. All recommendations come \
from deterministic tools (profile_data, build_forecaster_profile_tool, \
generate_plan_tool, generate_code_tool).
2. You translate the user's natural-language intent into tool calls.
3. You explain the deterministic outputs in plain language when asked.
4. You NEVER see raw datasets. Only metadata (schema, summary stats) is \
available to you via the profile_data tool.
5. Every recommendation must be reproducible from deterministic Python code.
6. If you cannot validate something, warn the user explicitly.

## Available Tools

- `profile_data`: Inspect a dataset and return a DataProfile with metadata, \
detected features, and warnings.
- `build_forecaster_profile_tool`: From a DataProfile, select the recommended \
forecaster + estimator and the compatible candidates.
- `generate_plan_tool`: From a ForecasterProfile, build a detailed \
ForecastPlan (lags, metric, backtesting, intervals, NaN handling, \
preprocessing).
- `generate_code_tool`: Produce a complete Python script from a ForecastPlan \
and DataProfile.

## Workflow

1. Use `profile_data` to understand the user's dataset.
2. Use `build_forecaster_profile_tool` to pick the forecaster + estimator.
3. Use `generate_plan_tool` to produce the detailed forecasting plan.
4. Use `generate_code_tool` to produce executable code.
5. Explain the plan and code to the user in plain language.

## Skills Reference

{skills_content}

## Skforecast API Reference

{reference_content}
"""

_EXPLAIN_PROMPT_TEMPLATE = """\
Explain the following forecasting plan in plain language. Be concise and \
focus on why each choice was made.

## Data Profile

- Observations: {n_observations}
- Series: {n_series}
- Frequency: {frequency}
- Exogenous columns: {exog_columns}
- Warnings: {profile_warnings}

## Forecast Plan

- Task type: {task_type}
- Forecaster: {forecaster}
- Estimator: {estimator}
- steps: {steps}
- Forecaster kwargs: {forecaster_kwargs}
- Interval method: {interval_method}
- Use exogenous: {use_exog}
- Explanation: {explanation}

Provide a clear, non-technical explanation of this plan suitable for a data \
scientist who is new to skforecast.
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


def build_explain_prompt(plan: ForecastPlan, profile: DataProfile) -> str:
    """
    Build a prompt to explain a forecasting plan in plain language.

    Parameters
    ----------
    plan : ForecastPlan
        Validated forecast plan to explain.
    profile : DataProfile
        Data profile providing context about the dataset.

    Returns
    -------
    prompt : str
        User-message prompt for the LLM to generate an explanation.
    """
    return _EXPLAIN_PROMPT_TEMPLATE.format(
        n_observations=profile.n_observations,
        n_series=profile.n_series,
        frequency=profile.frequency or "unknown",
        exog_columns=(
            ", ".join(profile.exog_columns) if profile.exog_columns else "none"
        ),
        profile_warnings=(
            "; ".join(profile.warnings) if profile.warnings else "none"
        ),
        task_type=plan.task_type,
        forecaster=plan.forecaster,
        estimator=plan.estimator or "none",
        steps=plan.steps,
        forecaster_kwargs=plan.forecaster_kwargs,
        interval_method=plan.interval_method or "none",
        use_exog=plan.use_exog,
        explanation=plan.explanation,
    )
