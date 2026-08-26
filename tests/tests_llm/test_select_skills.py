# Unit test select_skills skforecast_ai.llm.skills

import pytest

from skforecast_ai._constants import (
    MAX_SKILL_TOKENS,
    OLLAMA_MAX_CONTEXT_TOKENS,
    RESERVED_RESPONSE_TOKENS,
)
from skforecast_ai.llm.skills import (
    compute_skill_token_budget,
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
        ("Give me a naive baseline", "baseline-forecasting"),
        ("Does my model beat a seasonal naive?", "baseline-forecasting"),
        ("How do I use ForecasterEquivalentDate?", "baseline-forecasting"),
        ("I want to benchmark my forecaster", "baseline-forecasting"),
        ("What parameters does backtesting_forecaster take?", "complete-api-reference"),
        ("Show me the signature of TimeSeriesFold", "complete-api-reference"),
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
    # Budget of 5000 fits choosing-a-forecaster (2829) +
    # forecasting-single-series (1505) = 4334, but not the next skill by
    # priority, hyperparameter-optimization (5765).
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


@pytest.mark.parametrize(
    "question",
    [
        "What hyperparameters should I tune?",
        "Which parameters did you use for the model?",
    ],
    ids=lambda v: v[:40],
)
def test_select_skills_no_api_reference_on_parameter_talk(question):
    """
    Test that questions merely mentioning parameters do NOT pull in the
    API reference. It is the most expensive skill in the inventory, so it
    is reserved for questions asking for an actual signature.
    """
    result = select_skills(task_type="single_series", question=question)
    assert "complete-api-reference" not in result


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


def test_select_skills_foundation_keeps_hyperparameter_optimization():
    """
    Test that foundation-forecasting does NOT suppress
    hyperparameter-optimization: that skill documents
    `bayesian_search_foundation`, the only way to tune a zero-shot
    forecaster.
    """
    result = select_skills(
        task_type="foundation",
        question="How do I tune context_length with a bayesian search?",
    )
    assert "foundation-forecasting" in result
    assert "hyperparameter-optimization" in result


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
# Integration: the budgeted selection fits the Ollama window
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "task_type",
    ["single_series", "multi_series", "multivariate", "statistical",
     "foundation", None],
    ids=lambda v: f"task_type={v}",
)
@pytest.mark.parametrize("include_reference", [False, True], ids=["no_ref", "ref"])
def test_budgeted_selection_fits_the_ollama_window(task_type, include_reference):
    """
    Test that the budgeted selection never overflows the local context
    window, which is the guarantee the assistant relies on: skills grow
    with every upstream sync, so only the budgeted path can be trusted to
    keep the prompt inside the window.
    """
    context_tokens = 4_000
    budget = compute_skill_token_budget(
        max_context_tokens = OLLAMA_MAX_CONTEXT_TOKENS,
        context_tokens     = context_tokens,
        include_reference  = include_reference,
    )
    skills = select_skills(
        task_type    = task_type,
        question     = "Explain this plan and how to tune and backtest it",
        token_budget = budget,
    )

    total = (
        estimate_prompt_tokens(skills=skills, include_reference=include_reference)
        + context_tokens
        + RESERVED_RESPONSE_TOKENS
    )
    assert total <= OLLAMA_MAX_CONTEXT_TOKENS, (
        f"task_type={task_type!r} uses {total} tokens "
        f"(window: {OLLAMA_MAX_CONTEXT_TOKENS}). Skills: {skills}"
    )
    assert skills, "A modest context must still leave room for one skill"


# A question that trips every keyword pattern at once, which is the largest
# selection the routing table can produce.
ALL_TOPICS_QUESTION = (
    "lags acf backtest refit hyperparameter optuna prediction interval quantile "
    "metric mase rolling window features select_features rfecv drift monitor "
    "naive baseline traceback debug what parameters does it take signature api"
)


@pytest.mark.parametrize(
    "task_type",
    ["single_series", "multi_series", "multivariate", "statistical",
     "foundation", None],
    ids=lambda v: f"task_type={v}",
)
def test_worst_reachable_selection_fits_the_smallest_window(task_type):
    """
    Test that the largest selection the routing table can produce still
    leaves room for the answer in the smallest supported window.

    Asserting a ceiling on the whole inventory would test a combination
    `select_skills` never returns, and would go red on any upstream sync
    that merely writes more documentation. This asserts what the caller
    can actually be served.
    """
    skills = select_skills(task_type=task_type, question=ALL_TOPICS_QUESTION)

    skill_tokens = sum(_SKILL_TOKEN_ESTIMATES[s] for s in skills)
    assert skill_tokens <= MAX_SKILL_TOKENS, (
        f"task_type={task_type!r} selects {skill_tokens} tokens of skills "
        f"(cap: {MAX_SKILL_TOKENS}). Skills: {skills}"
    )

    total = (
        estimate_prompt_tokens(skills=skills, include_reference=True)
        + RESERVED_RESPONSE_TOKENS
    )
    assert total <= OLLAMA_MAX_CONTEXT_TOKENS, (
        f"task_type={task_type!r} needs {total} tokens "
        f"(window: {OLLAMA_MAX_CONTEXT_TOKENS}). Skills: {skills}"
    )


def test_select_skills_applies_the_cap_without_an_explicit_budget():
    """
    Test that `MAX_SKILL_TOKENS` is enforced even when no budget is passed.

    Only local models expose a context window up front, so a hosted model
    is called with `token_budget=None`; without the cap a question that
    matches many topics would be sent unbounded.
    """
    uncapped = select_skills(
        task_type="single_series", question=ALL_TOPICS_QUESTION
    )

    assert sum(_SKILL_TOKEN_ESTIMATES[s] for s in uncapped) <= MAX_SKILL_TOKENS
    assert uncapped[0] == "choosing-a-forecaster"
    # The question matches every pattern, so the cap must have dropped the
    # lowest-priority matches.
    assert "complete-api-reference" not in uncapped


def test_skill_inventory_matches_the_skills_directory():
    """
    Test that `ALL_SKILLS` and `_SKILL_TOKEN_ESTIMATES` describe exactly
    the skills present on disk.

    `tools/sync_skforecast_assets.py` refreshes `skills/` by deleting the
    directory and rewriting it from the pinned skforecast release, so a
    renamed or newly added skill upstream leaves both constants stale. A
    removed skill then raises `FileNotFoundError` at request time, and an
    added one is simply never selectable. Run
    `python tools/measure_skill_tokens.py --update` after syncing.
    """
    from skforecast_ai.llm.skills import ALL_SKILLS, _SKILLS_DIR

    on_disk = {
        path.name for path in _SKILLS_DIR.iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    }

    assert set(ALL_SKILLS) == on_disk
    assert set(_SKILL_TOKEN_ESTIMATES) == on_disk


def test_skill_inventory_follows_the_upstream_order():
    """
    Test that `ALL_SKILLS` holds each skill exactly once, in the canonical
    order published upstream as `SKILL_ORDER`.

    The order is the routing priority used to trim a selection to budget,
    so an upstream reordering that set comparison would not catch must
    still be reviewed deliberately.
    """
    from skforecast_ai.llm.skills import ALL_SKILLS

    assert ALL_SKILLS == [
        "choosing-a-forecaster",
        "autocorrelation-and-lag-selection",
        "feature-engineering",
        "forecasting-single-series",
        "forecasting-multiple-series",
        "foundation-forecasting",
        "baseline-forecasting",
        "metric-selection",
        "backtesting-configuration",
        "hyperparameter-optimization",
        "feature-selection",
        "prediction-intervals",
        "statistical-models",
        "deep-learning-forecasting",
        "drift-detection",
        "troubleshooting-common-errors",
        "complete-api-reference",
    ]
    assert len(set(ALL_SKILLS)) == len(ALL_SKILLS)


def test_select_skills_output_follows_the_inventory_order():
    """
    Test that a selection is returned in `ALL_SKILLS` order regardless of
    the order the keyword patterns matched in.
    """
    from skforecast_ai.llm.skills import ALL_SKILLS

    result = select_skills(
        task_type="single_series",
        question=(
            "Which metric should I use to check the model beats a naive "
            "baseline, and how do I tune it and get prediction intervals?"
        ),
    )

    assert result == sorted(result, key=ALL_SKILLS.index)
    assert "baseline-forecasting" in result


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
