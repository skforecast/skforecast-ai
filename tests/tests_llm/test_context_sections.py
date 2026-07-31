# Unit test context section renderers skforecast_ai.llm.context

import numpy as np
import pandas as pd
import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai._constants import MAX_LEADERBOARD_ROWS
from skforecast_ai.llm.context import (
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

from tests.fixtures_assistant import df_single, make_comparison_result

assistant = ForecastingAssistant()

profile = assistant.profile(data=df_single, target="sales", date_column="date")
plan = assistant.plan(profile, steps=5)

# `11.5` is an interior value: not the minimum, the maximum, or the mean,
# so it can only reach the context through a row-level rendering.
predictions = pd.DataFrame({"pred": [10.0, 11.5, 15.0]})
metrics = pd.DataFrame({"series": ["sales"], "MAE": [1.5]})
cv_config = {"steps": 5, "initial_train_size": 80, "n_folds": 4}


# =============================================================================
# Tests: empty input renders nothing
# =============================================================================
@pytest.mark.parametrize(
    "renderer, empty_input",
    [
        (render_dataset_section, None),
        (render_profile_decision_section, None),
        (render_plan_section, None),
        (render_cv_section, None),
        (render_deterministic_summary_section, None),
        (render_metrics_section, None),
        (render_predictions_section, None),
        (render_failures_section, None),
        (render_failures_section, {}),
    ],
    ids=lambda dt: f"renderer: {getattr(dt, '__name__', dt)}"
)
def test_section_renderer_output_when_input_is_empty(renderer, empty_input):
    """
    Test that every renderer returns an empty string for empty input, so
    a composed section list can include it unconditionally without
    emitting a stray tag.
    """
    assert renderer(empty_input) == ""


# =============================================================================
# Tests: populated input renders one balanced tagged block
# =============================================================================
@pytest.mark.parametrize(
    "section, tag",
    [
        (render_dataset_section(profile), "dataset"),
        (render_profile_decision_section(profile), "profile_decision"),
        (render_plan_section(plan), "forecast_plan"),
        (render_cv_section(cv_config), "cross_validation"),
        (render_deterministic_summary_section("Ran 4 folds."),
         "deterministic_summary"),
        (render_metrics_section(metrics), "evaluation_metrics"),
        (render_predictions_section(predictions), "predictions"),
    ],
    ids=lambda dt: f"tag: {dt}" if isinstance(dt, str) else ""
)
def test_section_renderer_output_is_a_balanced_tagged_block(section, tag):
    """
    Test that each renderer emits exactly one opening and one closing tag
    of its own name and nothing else at the top level.
    """
    assert section.startswith(f"<{tag}>\n")
    assert section.endswith(f"\n</{tag}>")
    assert section.count(f"<{tag}>") == 1
    assert section.count(f"</{tag}>") == 1


def test_render_dataset_section_reports_exog_and_missing_values():
    """
    Test that the dataset section reports the exogenous columns and omits
    the missing-value lines when there are none to report.
    """
    section = render_dataset_section(profile)

    assert "- Observations: 100" in section
    assert "- Frequency: D" in section
    assert "- Target: sales" in section
    assert "- Exogenous columns: promo" in section
    assert "Missing in target" not in section


def test_render_cv_section_prepends_note_when_provided():
    """
    Test that the shared-strategy note used by a comparison is rendered
    ahead of the parameters rather than mixed in with them.
    """
    section = render_cv_section(cv_config, note="Applied to every candidate.")

    body = section.splitlines()
    assert body[1] == "Applied to every candidate."
    assert body[2] == "- steps: 5"


def test_render_metrics_section_states_that_none_were_computed():
    """
    Test that prediction mode renders an explicit no-metrics statement,
    so the absence of the section cannot be read as a completed
    evaluation.
    """
    section = render_metrics_section(None, has_predictions=True)

    assert "<evaluation_metrics>" in section
    assert "No evaluation metrics were computed" in section


def test_render_predictions_section_withholds_values_when_send_data_false():
    """
    Test that row-level values are replaced by aggregate statistics when
    `send_data` is False.
    """
    section = render_predictions_section(predictions, send_data=False)

    assert "Shape: 3 rows x 1 columns" in section
    assert "11.5" not in section


def test_render_winning_candidate_section_nests_the_plan():
    """
    Test that the winner's plan is nested inside the winning-candidate
    tag, so it cannot be mistaken for the configuration shared by every
    candidate.
    """
    section = render_winning_candidate_section("winner", plan)

    assert section.startswith("<winning_candidate>")
    assert section.endswith("</winning_candidate>")
    assert "Name: winner" in section
    assert section.index("<forecast_plan>") < section.index(
        "</winning_candidate>"
    )


# =============================================================================
# Tests: leaderboard truncation
# =============================================================================
def test_render_leaderboard_section_output_when_all_rows_fit():
    """
    Test that a leaderboard within the row cap is rendered in full with
    no omission notice.
    """
    results = pd.DataFrame({
        "rank": [1, 2],
        "name": ["winner", "runner_up"],
        "MAE": [1.0, 2.0],
    })

    section = render_leaderboard_section(results)

    assert "Candidates listed: 2 (all shown below)." in section
    assert "winner" in section
    assert "runner_up" in section
    assert "omitted" not in section


def test_render_leaderboard_section_keeps_top_rows_when_truncated():
    """
    Test that a large leaderboard keeps its top rows rather than a head
    and a tail. The table is sorted by the ranking metric, so the top
    rows are the ones a ranking question needs.
    """
    n_candidates = 50
    results = pd.DataFrame({
        "rank": np.arange(1, n_candidates + 1),
        "name": [f"cand_{i:02d}" for i in range(n_candidates)],
        "MAE": np.arange(n_candidates, dtype=float),
    })

    section = render_leaderboard_section(results)
    omitted = n_candidates - MAX_LEADERBOARD_ROWS

    assert f"Candidates listed: {n_candidates}." in section
    assert f"Only the top {MAX_LEADERBOARD_ROWS} rows are shown" in section
    assert f"... ({omitted} lower-ranked candidates omitted) ..." in section
    assert "cand_00" in section
    assert "cand_49" not in section


def test_render_leaderboard_section_omits_numeric_summary_of_rank():
    """
    Test that a truncated leaderboard carries no per-column min/max/mean.
    Summarizing the `rank` column describes a counter, not the results,
    and reading it as a metric range is a plausible mistake.
    """
    results = pd.DataFrame({
        "rank": np.arange(1, 51),
        "MAE": np.arange(50, dtype=float),
    })

    section = render_leaderboard_section(results)

    assert "Per-column summary" not in section
    assert "min=" not in section
    assert "mean=" not in section


def test_render_leaderboard_section_respects_explicit_max_rows():
    """
    Test that the row cap is a parameter rather than a hardcoded literal.
    """
    results = pd.DataFrame({"rank": [1, 2, 3], "MAE": [1.0, 2.0, 3.0]})

    section = render_leaderboard_section(results, max_rows=2)

    assert "Candidates listed: 3." in section
    assert "... (1 lower-ranked candidates omitted) ..." in section


def test_render_comparison_overview_section_counts_failures_as_candidates():
    """
    Test that the candidate count includes the ones that failed, so the
    total matches what the user asked to compare.
    """
    comparison = make_comparison_result(assistant, with_failure=True)

    section = render_comparison_overview_section(comparison)

    assert "- Candidates evaluated: 3" in section
    assert "- Winner: winner" in section


def test_render_failures_section_withholds_tracebacks():
    """
    Test that a failure contributes a one-line summary only. Full
    tracebacks are verbose and can expose local filesystem paths.
    """
    comparison = make_comparison_result(assistant, with_failure=True)

    section = render_failures_section(comparison.failures)

    assert "<failed_candidates>" in section
    assert "- broken: ImportError: No module named 'lightgbm'" in section
    assert "Traceback" not in section


# =============================================================================
# Tests: join_sections
# =============================================================================
def test_join_sections_output_when_all_sections_are_empty():
    """
    Test that joining nothing produces an empty string rather than an
    empty wrapper, so `ask()` can tell there is no context to send.
    """
    assert join_sections([]) == ""
    assert join_sections(["", None, ""]) == ""


def test_join_sections_drops_empty_entries():
    """
    Test that empty entries are dropped without leaving blank lines
    between the sections that remain.
    """
    result = join_sections(["<a>\n1\n</a>", None, "", "<b>\n2\n</b>"])

    assert result == (
        "<forecast_context>\n<a>\n1\n</a>\n<b>\n2\n</b>\n</forecast_context>"
    )


def test_join_sections_does_not_modify_input():
    """
    Test that the caller's section list is left untouched.
    """
    sections = ["<a>\n1\n</a>", "", None]
    sections_original = list(sections)

    join_sections(sections)

    assert sections == sections_original


# =============================================================================
# Tests: build_context_message composes the renderers
# =============================================================================
def test_build_context_message_matches_the_composed_sections():
    """
    Test that the convenience entry point produces exactly what composing
    the renderers by hand produces, so the two cannot diverge.
    """
    composed = join_sections([
        render_dataset_section(profile),
        render_profile_decision_section(profile),
        render_plan_section(plan),
        render_cv_section(cv_config),
        render_deterministic_summary_section("Ran 4 folds."),
        render_metrics_section(metrics, has_predictions=True),
        render_predictions_section(predictions, send_data=True),
    ])

    result = build_context_message(
        profile     = profile,
        plan        = plan,
        predictions = predictions,
        metrics     = metrics,
        cv_config   = cv_config,
        explanation = "Ran 4 folds.",
        send_data   = True,
    )

    assert result == composed
