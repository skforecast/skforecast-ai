# Unit test prompts skforecast_ai.llm

import re

import pytest

from skforecast_ai._constants import MAX_STATIC_PROMPT_TOKENS
from skforecast_ai.llm.prompts import (
    _CV_ROLE_PROMPT,
    _PLAN_REFINEMENT_ROLE_PROMPT,
    _STATIC_ROLE_PROMPT,
)
from skforecast_ai.llm.skills import _STATIC_PROMPT_TOKEN_ESTIMATE

ALL_ROLE_PROMPTS = [
    ("static", _STATIC_ROLE_PROMPT),
    ("cv", _CV_ROLE_PROMPT),
    ("plan_refinement", _PLAN_REFINEMENT_ROLE_PROMPT),
]


# ---------------------------------------------------------------------------
# Structure shared by every role prompt
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name, prompt",
    ALL_ROLE_PROMPTS,
    ids=lambda dt: f"role prompt: {dt}"
)
def test_role_prompt_structure(name, prompt):
    """
    Test that every role prompt is a non-empty string carrying a numbered
    rules block, so the agents always receive an explicit contract.
    """
    assert isinstance(prompt, str)
    assert prompt.strip()
    assert "## Rules" in prompt

    numbers = [int(n) for n in re.findall(r"^(\d+)\. ", prompt, re.M)]
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.parametrize(
    "name, prompt",
    ALL_ROLE_PROMPTS,
    ids=lambda dt: f"role prompt: {dt}"
)
def test_role_prompt_uses_plain_ascii_punctuation(name, prompt):
    """
    Test that no role prompt contains en dashes or em dashes. The prompts
    instruct the model to avoid them, so they must not model the opposite.
    """
    assert "\u2013" not in prompt
    assert "\u2014" not in prompt


# ---------------------------------------------------------------------------
# Static role prompt: required directives
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "directive",
    [
        # Grounding: values must come from the context, never from arithmetic.
        "Use only values that appear verbatim inside `<forecast_context>`",
        "Do NOT compute new numbers",
        "say it is not available",
        "Do not describe trends or progressions from a partial sample",
        # Attribution: no feature importances or ranking rationale are sent.
        "Feature importances are never provided",
        "ranking their contribution is not",
        "A leaderboard reports what, not why",
        "Never state a causal relationship",
        # Metric interpretation: one phrasing, no derived restatements.
        "Do not restate a metric in a second, derived form",
        # Scope of advice: report decisions, advise only when asked.
        "never second-guess or re-derive them",
        "must not contain invented numeric thresholds",
        "Never present a suggestion as a decision that has already been made",
        # Output contract.
        "Open with a direct answer to the question",
        "Cover only what was asked",
        "Do NOT use markdown tables or horizontal rules",
        "Do not use en dashes or em dashes",
    ],
    ids=lambda dt: f"directive: {dt[:45]}"
)
def test_static_role_prompt_contains_directive(directive):
    """
    Test that each grounding, attribution, metric, advice, and output
    directive is present in the static role prompt. These rules are the
    contract that keeps explanations tied to deterministic output.
    """
    assert directive in _STATIC_ROLE_PROMPT


def test_static_role_prompt_documents_context_tags():
    """
    Test that the static role prompt names the tags the context block
    emits, so the model knows which content is authoritative.
    """
    for tag in ["<forecast_context>", "<dataset>", "<forecast_plan>",
                "<cross_validation>", "<deterministic_summary>",
                "<evaluation_metrics>", "<predictions>", "<leaderboard>",
                "<question>"]:
        assert tag in _STATIC_ROLE_PROMPT


@pytest.mark.parametrize(
    "superseded",
    [
        "You NEVER make forecasting decisions",
        "interpret them relative to baselines",
        "Structure explanations with clear headings for distinct aspects",
        "Be concise and focus on practical guidance",
    ],
    ids=lambda dt: f"superseded: {dt[:45]}"
)
def test_static_role_prompt_omits_superseded_wording(superseded):
    """
    Test that the superseded rules are gone. The old wording either
    invited derived arithmetic or conflicted with the questions users
    actually ask, so a revert must fail loudly.
    """
    assert superseded not in _STATIC_ROLE_PROMPT


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------

def test_static_prompt_token_estimate_is_derived_from_the_prompt():
    """
    Test that the estimate used to size the Ollama context window is
    computed from the prompt rather than hardcoded, so it cannot drift
    from the prompt it describes when the prompt is edited.
    """
    assert _STATIC_PROMPT_TOKEN_ESTIMATE == len(_STATIC_ROLE_PROMPT) // 4


def test_static_role_prompt_within_ceiling():
    """
    Test that the static role prompt stays under its ceiling. It is paid
    on every call and cannot be trimmed at selection time, so growth here
    comes straight out of the budget available for skills.
    """
    assert _STATIC_PROMPT_TOKEN_ESTIMATE <= MAX_STATIC_PROMPT_TOKENS
