# Unit test compute_skill_token_budget skforecast_ai.llm.skills

from skforecast_ai._constants import (
    MAX_STATIC_PROMPT_TOKENS,
    OLLAMA_MAX_CONTEXT_TOKENS,
    RESERVED_RESPONSE_TOKENS,
)
from skforecast_ai.llm.skills import (
    _REFERENCE_TOKEN_ESTIMATE,
    _STATIC_PROMPT_TOKEN_ESTIMATE,
    compute_skill_token_budget,
    estimate_context_tokens,
    select_skills,
)


# =============================================================================
# Tests: estimate_context_tokens
# =============================================================================
def test_estimate_context_tokens_output():
    """
    Test that the context estimate uses the same four-characters-per-token
    approximation as the measured skill estimates, so the two are
    comparable when budgeting.
    """
    assert estimate_context_tokens("") == 0
    assert estimate_context_tokens("a" * 400) == 100


# =============================================================================
# Tests: compute_skill_token_budget
# =============================================================================
def test_compute_skill_token_budget_subtracts_the_fixed_costs():
    """
    Test that the budget is the window minus the costs that cannot be
    trimmed at selection time: the static role prompt, the rendered
    context, and the space reserved for the answer.
    """
    result = compute_skill_token_budget(
        max_context_tokens = 20_000,
        context_tokens     = 1_000,
    )

    expected = (
        20_000
        - _STATIC_PROMPT_TOKEN_ESTIMATE
        - 1_000
        - RESERVED_RESPONSE_TOKENS
    )
    assert result == expected


def test_compute_skill_token_budget_subtracts_the_reference_when_included():
    """
    Test that the API reference is charged against the budget. It is
    appended to the same instructions the skills go into, so ignoring it
    would overstate the room available.
    """
    without = compute_skill_token_budget(
        max_context_tokens = 20_000,
        context_tokens     = 1_000,
        include_reference  = False,
    )
    with_reference = compute_skill_token_budget(
        max_context_tokens = 20_000,
        context_tokens     = 1_000,
        include_reference  = True,
    )

    assert without - with_reference == _REFERENCE_TOKEN_ESTIMATE


def test_compute_skill_token_budget_output_when_context_exceeds_window():
    """
    Test that an oversized context yields a zero budget rather than a
    negative one, so `select_skills` drops every skill instead of
    misinterpreting the sign.
    """
    result = compute_skill_token_budget(
        max_context_tokens = 4_096,
        context_tokens     = 100_000,
    )

    assert result == 0


def test_compute_skill_token_budget_trims_skills_when_context_is_large():
    """
    Test the end-to-end effect: a context block large enough to crowd out
    the skills causes fewer skills to be selected than an empty context
    would.
    """
    question = "How should I configure backtesting and prediction intervals?"

    unbudgeted = select_skills(task_type="single_series", question=question)
    budgeted = select_skills(
        task_type    = "single_series",
        question     = question,
        token_budget = compute_skill_token_budget(
                           max_context_tokens = OLLAMA_MAX_CONTEXT_TOKENS,
                           context_tokens     = OLLAMA_MAX_CONTEXT_TOKENS - 5_000,
                       ),
    )

    assert len(budgeted) < len(unbudgeted)
    # Trimming keeps the highest-priority skills, never reorders them.
    assert budgeted == unbudgeted[:len(budgeted)]


# =============================================================================
# Tests: the static prompt fits its share of the window
# =============================================================================
def test_static_prompt_ceiling_leaves_room_for_skills():
    """
    Test that the ceiling on the untrimmable static prompt is a small
    fraction of the smallest supported window, so the role prompt cannot
    grow into the budget the skills need.
    """
    assert MAX_STATIC_PROMPT_TOKENS < OLLAMA_MAX_CONTEXT_TOKENS * 0.1
