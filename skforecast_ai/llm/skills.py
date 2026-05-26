"""Skill inventory, loading, selection, and token budgeting."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _PACKAGE_DIR / "skills"
_RESOURCES_DIR = _PACKAGE_DIR / "resources"

ALL_SKILLS = [
    "autocorrelation-and-lag-selection",
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
    "metric-selection",
    "prediction-intervals",
    "statistical-models",
    "troubleshooting-common-errors",
]

# ---------------------------------------------------------------------------
# Skill selection: routing table + keyword augmentation
# ---------------------------------------------------------------------------

_TASK_TYPE_SKILLS: dict[str | None, list[str]] = {
    "single_series": ["choosing-a-forecaster", "forecasting-single-series"],
    "multi_series": ["choosing-a-forecaster", "forecasting-multiple-series"],
    "multivariate": ["choosing-a-forecaster", "forecasting-multiple-series"],
    "statistical": ["statistical-models"],
    "foundation": ["foundation-forecasting"],
    None: ["choosing-a-forecaster"],
}

_KEYWORD_SKILLS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"interval|confidence|quantile|conformal|bootstrap", re.I), "prediction-intervals"),
    (re.compile(r"hyperparameter|search|bayesian|optuna|grid|tuning", re.I), "hyperparameter-optimization"),
    (re.compile(r"\blags?\b|autocorrelation|\bacf\b|\bpacf\b", re.I), "autocorrelation-and-lag-selection"),
    (re.compile(r"feature.*(engineer|roll|window)|rolling|window.feature", re.I), "feature-engineering"),
    (re.compile(r"feature.selection|rfecv|select.feature", re.I), "feature-selection"),
    (re.compile(r"metric|mae|mse|mape|rmse|smape|mase|pinball|crps|coverage", re.I), "metric-selection"),
    (re.compile(r"rnn|lstm|deep.learn|keras|neural", re.I), "deep-learning-forecasting"),
    (re.compile(r"chronos|timesfm|moirai|foundation|zero.shot|tabicl", re.I), "foundation-forecasting"),
    (re.compile(r"arima|sarimax|\bets\b|arar|\bstatistical\b", re.I), "statistical-models"),
    (re.compile(r"drift|monitor|deploy", re.I), "drift-detection"),
    (re.compile(r"traceback|debug|troubleshoot|exception|TypeError|ValueError", re.I), "troubleshooting-common-errors"),
]

# When a skill in the key set is selected, the skills in the value set are
# removed. This prevents conflicting guidance (e.g., ForecasterFoundation
# handles multi-series natively, so loading the ForecasterRecursiveMultiSeries
# skill would be misleading).
_SKILL_OVERRIDES: dict[str, set[str]] = {
    "foundation-forecasting": {
        "autocorrelation-and-lag-selection",
        "forecasting-single-series",
        "forecasting-multiple-series",
        "feature-engineering",
        "feature-selection",
        "hyperparameter-optimization",
        "prediction-intervals",
    },
    "deep-learning-forecasting": {
        "forecasting-single-series",
        "forecasting-multiple-series",
        "feature-selection",
        "hyperparameter-optimization",
    },
    "statistical-models": {
        "forecasting-single-series",
        "forecasting-multiple-series",
        "feature-engineering",
        "feature-selection",
    },
}

# Measured token estimates (chars / 4) for each skill (SKILL.md + references/).
_SKILL_TOKEN_ESTIMATES: dict[str, int] = {
    "choosing-a-forecaster": 2810,
    "forecasting-single-series": 1224,
    "forecasting-multiple-series": 1482,
    "statistical-models": 3755,
    "foundation-forecasting": 3211,
    "hyperparameter-optimization": 3378,
    "prediction-intervals": 3225,
    "autocorrelation-and-lag-selection": 2044,
    "feature-engineering": 8126,
    "feature-selection": 1407,
    "metric-selection": 5072,
    "deep-learning-forecasting": 3883,
    "drift-detection": 1249,
    "troubleshooting-common-errors": 2108,
    "complete-api-reference": 11409,
}

_REFERENCE_TOKEN_ESTIMATE = 7600  # llms-base.txt measured size
_STATIC_PROMPT_TOKEN_ESTIMATE = 200


@lru_cache(maxsize=None)
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


@lru_cache(maxsize=1)
def load_llms_reference() -> str:
    """
    Load the skforecast API reference text.

    Returns
    -------
    content : str
        Full text of `skforecast_ai/resources/llms-base.txt`.
    """
    ref_file = _RESOURCES_DIR / "llms-base.txt"

    if not ref_file.exists():
        raise FileNotFoundError(
            f"LLM reference file not found. Expected: {ref_file}"
        )

    return ref_file.read_text(encoding="utf-8")


def select_skills(
    task_type: str | None,
    question: str,
    token_budget: int | None = None,
) -> list[str]:
    """
    Select relevant skills based on task_type and question keywords.

    Uses a two-step strategy:

    1. **Profile-based**: resolve base skills from the forecaster's
       `task_type` using a deterministic routing table.
    2. **Keyword augmentation**: scan the user question for topic
       keywords and append matching skills.

    Parameters
    ----------
    task_type : str, None
        The forecasting task category from `ForecastingProfile.task_type`
        (e.g., `'single_series'`, `'statistical'`). If None, falls
        back to a minimal general-purpose skill set.
    question : str
        The user's natural-language question.
    token_budget : int, None, default None
        Maximum tokens available for skill content. If None, no budget
        limit is applied. When set, skills are included in order until
        the budget is exhausted.

    Returns
    -------
    skills : list of str
        Ordered list of skill names to load.
    """
    base = list(_TASK_TYPE_SKILLS.get(task_type, _TASK_TYPE_SKILLS[None]))

    augmented: list[str] = []
    for pattern, skill_name in _KEYWORD_SKILLS:
        if pattern.search(question) and skill_name not in base:
            augmented.append(skill_name)

    selected = base + [s for s in augmented if s not in base]

    # Conflict resolution: remove skills suppressed by higher-priority ones.
    suppressed: set[str] = set()
    for skill in selected:
        if skill in _SKILL_OVERRIDES:
            suppressed.update(_SKILL_OVERRIDES[skill])
    if suppressed:
        selected = [s for s in selected if s not in suppressed]

    if token_budget is not None:
        before_trim = list(selected)
        selected = _trim_to_budget(selected, token_budget)
        if len(selected) < len(before_trim):
            dropped = [s for s in before_trim if s not in selected]
            logger.info(
                "Skills trimmed to budget (%d tokens): kept %s, dropped %s",
                token_budget,
                selected,
                dropped,
            )

    logger.debug(
        "select_skills(task_type=%r) -> base=%s, augmented=%s, final=%s",
        task_type,
        base,
        augmented,
        selected,
    )

    return selected


def _trim_to_budget(skills: list[str], budget: int) -> list[str]:
    """Keep skills in order until the token budget is exhausted."""
    result: list[str] = []
    used = 0
    for skill in skills:
        cost = _SKILL_TOKEN_ESTIMATES.get(skill, 5000)
        if used + cost <= budget:
            result.append(skill)
            used += cost
        else:
            break
    return result


def estimate_prompt_tokens(
    skills: list[str],
    include_reference: bool = False,
) -> int:
    """
    Estimate total prompt tokens for a given skill + reference config.

    Parameters
    ----------
    skills : list of str
        Skill names to include.
    include_reference : bool, default False
        Whether the API reference will be included.

    Returns
    -------
    tokens : int
        Estimated token count.
    """
    total = _STATIC_PROMPT_TOKEN_ESTIMATE
    for skill in skills:
        total += _SKILL_TOKEN_ESTIMATES.get(skill, 5000)
    if include_reference:
        total += _REFERENCE_TOKEN_ESTIMATE
    return total
