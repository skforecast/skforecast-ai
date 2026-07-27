# Unit test build_comparison_context

from skforecast_ai import ForecastingAssistant
from skforecast_ai.llm.context import build_comparison_context

from tests.fixtures_assistant import make_comparison_result

assistant = ForecastingAssistant()


# =============================================================================
# Tests: sections rendered
# =============================================================================
def test_build_comparison_context_output_when_all_candidates_succeed():
    """
    Test that the context includes the dataset, leaderboard, ranking
    metric, shared CV strategy, and winning candidate sections, and omits
    the failed-candidates section when every candidate succeeded.
    """
    comparison = make_comparison_result(assistant)

    context = build_comparison_context(comparison)

    assert "## Dataset" in context
    assert "## Forecaster Comparison" in context
    assert "- Candidates evaluated: 2" in context
    assert "- Ranking metric: MAE" in context
    assert "- Winner: winner" in context
    assert "### Leaderboard" in context
    assert "runner_up" in context
    assert "### Shared Cross-Validation Strategy" in context
    assert "- initial_train_size: 70" in context
    assert "### Deterministic Summary" in context
    assert "## Winning Candidate: winner" in context

    assert "### Failed Candidates" not in context


def test_build_comparison_context_guardrail_against_re_ranking():
    """
    Test that the context states the ranking is deterministic so the LLM
    does not reorder or recompute the leaderboard.
    """
    comparison = make_comparison_result(assistant)

    context = build_comparison_context(comparison)

    assert (
        "The ranking is a deterministic ascending sort of the MAE column "
        "(lower is better). Do not re-rank the candidates or recompute the "
        "table." in context
    )


def test_build_comparison_context_output_when_some_candidates_fail():
    """
    Test that each failed candidate contributes a one-line summary and
    that the full traceback is withheld.
    """
    comparison = make_comparison_result(assistant, with_failure=True)

    context = build_comparison_context(comparison)

    assert "- Candidates evaluated: 3" in context
    assert "### Failed Candidates" in context
    assert "- broken: ImportError: No module named 'lightgbm'" in context

    assert "SECRET_FRAME" not in context
    assert "Traceback (most recent call last)" not in context


# =============================================================================
# Tests: payload is compact
# =============================================================================
def test_build_comparison_context_excludes_non_winning_candidate_detail():
    """
    Test that only the winning candidate is detailed: the other
    candidates' generated code and predictions are withheld, so the
    payload does not grow with the number of candidates.
    """
    comparison = make_comparison_result(assistant)

    context = build_comparison_context(comparison)

    assert "# runner up code" not in context
    assert "# winner code" not in context
    assert "### Predictions" not in context


def test_build_comparison_context_states_shared_sections_once():
    """
    Test that the shared profile and cross-validation strategy are
    emitted once rather than repeated for the winning candidate.
    """
    comparison = make_comparison_result(assistant)

    context = build_comparison_context(comparison)

    assert context.count("## Dataset") == 1
    assert context.count("## Profile Decision") == 1
    assert context.count("### Shared Cross-Validation Strategy") == 1
    assert context.count("## Forecast Plan") == 1
