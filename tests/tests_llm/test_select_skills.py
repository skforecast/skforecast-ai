# Unit test select_skills skforecast_ai.llm.skills

import pytest

from skforecast_ai.llm.skills import (
    estimate_prompt_tokens,
    select_skills,
    _REFERENCE_TOKEN_ESTIMATE,
    _SKILL_TOKEN_ESTIMATES,
    _STATIC_PROMPT_TOKEN_ESTIMATE,
)


# ---------------------------------------------------------------------------
# select_skills: routing by task_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "task_type, expected",
    [
        ("single_series", ["choosing-a-forecaster", "forecasting-single-series"]),
        ("multi_series", ["choosing-a-forecaster", "forecasting-multiple-series"]),
        ("multivariate", ["choosing-a-forecaster", "forecasting-multiple-series"]),
        ("statistical", ["statistical-models"]),
        ("foundation", ["foundation-forecasting"]),
        (None, ["choosing-a-forecaster"]),
    ],
    ids=lambda v: f"task_type={v}" if not isinstance(v, list) else str(v),
)
def test_select_skills_base_routing(task_type, expected):
    """
    Test that select_skills returns correct base skills for each task_type
    when the question has no matching keywords.
    """
    result = select_skills(task_type=task_type, question="general question")
    assert result == expected


# ---------------------------------------------------------------------------
# select_skills: keyword augmentation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "question, expected_skill",
    [
        ("How do I get prediction intervals?", "prediction-intervals"),
        ("What is the confidence level?", "prediction-intervals"),
        ("How to use bayesian search?", "hyperparameter-optimization"),
        ("What lags should I use?", "autocorrelation-and-lag-selection"),
        ("Show me rolling window features", "feature-engineering"),
        ("How does feature selection work?", "feature-selection"),
        ("Can I use LSTM for forecasting?", "deep-learning-forecasting"),
        ("How to use Chronos model?", "foundation-forecasting"),
        ("Fit an ARIMA model", "statistical-models"),
        ("I need drift detection", "drift-detection"),
        ("I get a traceback error", "troubleshooting-common-errors"),
    ],
    ids=lambda v: v[:40] if isinstance(v, str) else v,
)
def test_select_skills_keyword_augmentation(question, expected_skill):
    """
    Test that keyword patterns in the question add the corresponding skill.
    """
    result = select_skills(task_type=None, question=question)
    assert expected_skill in result


def test_select_skills_no_duplicate_when_base_matches_keyword():
    """
    Test that a skill already in the base set is not duplicated when
    keywords also match it.
    """
    result = select_skills(
        task_type="statistical",
        question="How do I fit an ARIMA model?",
    )
    assert result.count("statistical-models") == 1


def test_select_skills_combines_base_and_augmented():
    """
    Test that base skills come first, followed by augmented skills.
    """
    result = select_skills(
        task_type="single_series",
        question="How to add prediction intervals with bootstrap?",
    )
    assert result[0] == "choosing-a-forecaster"
    assert result[1] == "forecasting-single-series"
    assert "prediction-intervals" in result
    assert result.index("prediction-intervals") > 1


# ---------------------------------------------------------------------------
# select_skills: token budget enforcement
# ---------------------------------------------------------------------------

def test_select_skills_trims_to_budget():
    """
    Test that skills are trimmed when token_budget is too small to fit all.
    """
    result = select_skills(
        task_type="single_series",
        question="How to add prediction intervals and hyperparameter tuning?",
        token_budget=5000,
    )
    # Budget of 5000 fits choosing-a-forecaster (2702) +
    # forecasting-single-series (1223) = 3925, but not prediction-intervals (3203)
    assert "choosing-a-forecaster" in result
    assert "forecasting-single-series" in result
    assert "prediction-intervals" not in result


def test_select_skills_returns_empty_when_budget_zero():
    """
    Test that an empty list is returned when token_budget is 0.
    """
    result = select_skills(
        task_type="single_series",
        question="anything",
        token_budget=0,
    )
    assert result == []


def test_select_skills_no_limit_when_budget_none():
    """
    Test that all matched skills are returned when token_budget is None.
    """
    result = select_skills(
        task_type="single_series",
        question="How to add prediction intervals and hyperparameter tuning?",
        token_budget=None,
    )
    assert "choosing-a-forecaster" in result
    assert "forecasting-single-series" in result
    assert "prediction-intervals" in result
    assert "hyperparameter-optimization" in result


# ---------------------------------------------------------------------------
# select_skills: false positive protection
# ---------------------------------------------------------------------------

def test_select_skills_no_troubleshooting_on_common_words():
    """
    Test that common words like 'error' or 'warning' do NOT trigger the
    troubleshooting skill (only specific patterns like 'traceback' do).
    """
    result = select_skills(
        task_type="single_series",
        question="Will I get a warning if my data has missing values?",
    )
    assert "troubleshooting-common-errors" not in result

    result2 = select_skills(
        task_type="single_series",
        question="What is the prediction error metric?",
    )
    assert "troubleshooting-common-errors" not in result2


# ---------------------------------------------------------------------------
# select_skills: conflict resolution (skill overrides)
# ---------------------------------------------------------------------------

def test_select_skills_foundation_overrides_multi_series():
    """
    Test that foundation-forecasting suppresses forecasting-multiple-series
    because ForecasterFoundation handles multi-series natively.
    """
    result = select_skills(
        task_type="multi_series",
        question="How do I forecast multiple series with Chronos?",
    )
    assert "foundation-forecasting" in result
    assert "forecasting-multiple-series" not in result


def test_select_skills_foundation_overrides_single_series():
    """
    Test that foundation-forecasting suppresses forecasting-single-series
    because ForecasterFoundation has its own single-series workflow.
    """
    result = select_skills(
        task_type="single_series",
        question="Use TimesFM for my single series",
    )
    assert "foundation-forecasting" in result
    assert "forecasting-single-series" not in result


def test_select_skills_statistical_overrides_multi_series():
    """
    Test that statistical-models suppresses forecasting-multiple-series
    because ForecasterStats does not support multi-series.
    """
    result = select_skills(
        task_type="multi_series",
        question="Fit an ARIMA model",
    )
    assert "statistical-models" in result
    assert "forecasting-multiple-series" not in result


def test_select_skills_deep_learning_overrides_multi_series():
    """
    Test that deep-learning-forecasting suppresses forecasting-multiple-series
    because ForecasterRnn has its own workflow.
    """
    result = select_skills(
        task_type="multi_series",
        question="Use LSTM for my series",
    )
    assert "deep-learning-forecasting" in result
    assert "forecasting-multiple-series" not in result


def test_select_skills_foundation_task_type_unchanged():
    """
    Test that task_type='foundation' still works correctly (no regression).
    """
    result = select_skills(
        task_type="foundation",
        question="How do I forecast multiple series?",
    )
    assert "foundation-forecasting" in result
    assert "forecasting-multiple-series" not in result


# ---------------------------------------------------------------------------
# estimate_prompt_tokens
# ---------------------------------------------------------------------------

def test_estimate_prompt_tokens_basic():
    """
    Test that estimate_prompt_tokens returns the sum of static prompt
    plus skill estimates.
    """
    result = estimate_prompt_tokens(
        skills=["choosing-a-forecaster"],
        include_reference=False,
    )
    assert result == (
        _STATIC_PROMPT_TOKEN_ESTIMATE
        + _SKILL_TOKEN_ESTIMATES["choosing-a-forecaster"]
    )


def test_estimate_prompt_tokens_with_reference():
    """
    Test that estimate_prompt_tokens adds exactly the reference estimate
    when include_reference=True.
    """
    base = estimate_prompt_tokens(
        skills=["choosing-a-forecaster"],
        include_reference=False,
    )
    result = estimate_prompt_tokens(
        skills=["choosing-a-forecaster"],
        include_reference=True,
    )
    assert result == base + _REFERENCE_TOKEN_ESTIMATE


def test_estimate_prompt_tokens_multiple_skills():
    """
    Test that estimate_prompt_tokens sums all skill estimates.
    """
    skills = ["choosing-a-forecaster", "forecasting-single-series"]
    result = estimate_prompt_tokens(skills=skills, include_reference=False)
    assert result == (
        _STATIC_PROMPT_TOKEN_ESTIMATE
        + sum(_SKILL_TOKEN_ESTIMATES[s] for s in skills)
    )


def test_estimate_prompt_tokens_unknown_skill_uses_default():
    """
    Test that estimate_prompt_tokens falls back to the 5000-token default
    for an unknown skill name (not present in _SKILL_TOKEN_ESTIMATES).
    """
    result = estimate_prompt_tokens(
        skills=["this-skill-does-not-exist"],
        include_reference=False,
    )
    assert result == _STATIC_PROMPT_TOKEN_ESTIMATE + 5000


def test_estimate_prompt_tokens_empty_skills():
    """
    Test that estimate_prompt_tokens with empty skills returns only the
    static prompt estimate.
    """
    result = estimate_prompt_tokens(skills=[], include_reference=False)
    assert result == _STATIC_PROMPT_TOKEN_ESTIMATE


# ---------------------------------------------------------------------------
# Integration: prompt fits within Ollama 8K context
# ---------------------------------------------------------------------------

def test_prompt_fits_8k_for_minimal_ollama_case():
    """
    Test that for any single task_type with a short question and no
    reference, the estimated prompt tokens stay well within the 8K
    Ollama context limit (leaving 30% for generation headroom = 5,734
    tokens available for prompt).
    """
    task_types = [
        "single_series",
        "multi_series",
        "multivariate",
        "statistical",
        "foundation",
        None,
    ]
    max_prompt_budget = 5734  # 70% of 8192

    for task_type in task_types:
        skills = select_skills(
            task_type=task_type,
            question="Explain this plan",
        )
        tokens = estimate_prompt_tokens(skills=skills, include_reference=False)
        assert tokens <= max_prompt_budget, (
            f"task_type={task_type!r} uses {tokens} tokens "
            f"(max allowed: {max_prompt_budget}). Skills: {skills}"
        )


def test_prompt_with_reference_fits_32k():
    """
    Test that even with the API reference included, the estimated prompt
    tokens fit within a 32K Ollama context (22,937 token prompt budget).
    """
    skills = select_skills(
        task_type="single_series",
        question="How to add prediction intervals and hyperparameter tuning?",
    )
    tokens = estimate_prompt_tokens(skills=skills, include_reference=True)
    max_prompt_budget = 22_937  # 70% of 32768
    assert tokens <= max_prompt_budget, (
        f"Prompt with reference uses {tokens} tokens "
        f"(max allowed: {max_prompt_budget}). Skills: {skills}"
    )


def test_worst_case_all_skills_estimate():
    """
    Test that loading ALL skills (worst case) plus reference stays under
    128K context models (89,600 token prompt budget).
    """
    from skforecast_ai.llm.skills import ALL_SKILLS

    tokens = estimate_prompt_tokens(skills=ALL_SKILLS, include_reference=True)
    max_prompt_budget = 89_600  # 70% of 128K
    assert tokens <= max_prompt_budget, (
        f"All skills + reference = {tokens} tokens "
        f"(max allowed: {max_prompt_budget})"
    )


# ---------------------------------------------------------------------------
# Logging: skill selection logs at debug level
# ---------------------------------------------------------------------------

def test_select_skills_logs_debug(caplog):
    """
    Test that select_skills emits a DEBUG log with the final skill list.
    """
    import logging

    with caplog.at_level(logging.DEBUG, logger="skforecast_ai.llm.skills"):
        select_skills(task_type="single_series", question="general question")

    assert any("select_skills" in record.message for record in caplog.records)
    assert any("choosing-a-forecaster" in record.message for record in caplog.records)


def test_select_skills_logs_info_when_trimmed(caplog):
    """
    Test that select_skills emits an INFO log when skills are trimmed
    due to token budget.
    """
    import logging

    with caplog.at_level(logging.INFO, logger="skforecast_ai.llm.skills"):
        select_skills(
            task_type="single_series",
            question="prediction intervals and hyperparameter tuning",
            token_budget=5000,
        )

    assert any("trimmed" in record.message.lower() for record in caplog.records)
