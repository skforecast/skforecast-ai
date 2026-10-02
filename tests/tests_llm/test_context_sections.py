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
    render_script_section,
    render_winning_candidate_section,
)

from tests.fixtures_assistant import df_single, make_comparison_result
from tests.fixtures_llm import plan_single, profile_single

assistant = ForecastingAssistant()

profile = assistant.profile(data=df_single, target="sales", date_column="date")
plan = assistant.plan(profile, steps=5)
profile_categorical = assistant.profile(
    data=df_single.assign(
        weather=np.where(np.arange(len(df_single)) % 2 == 0, "clear", "rain")
    ),
    target="sales",
    date_column="date",
)

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
        (render_cv_section(cv_config), "backtesting_strategy"),
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


def test_render_dataset_section_reports_range_scale_and_quality():
    """
    Test that the dataset section states the date range, the target
    scale, that there are no missing values, and that no irregularities
    were detected, so the model can judge metrics and answer data
    questions without guessing.
    """
    section = render_dataset_section(profile)
    dp = profile.data_profile
    start = dp.series_lengths["sales"].start
    end = dp.series_lengths["sales"].end

    assert f"- Date range: {start} to {end}" in section
    assert "- Target statistics: min" in section
    assert "- Missing values: none" in section
    assert "- Index irregularities: none detected" in section


def test_render_dataset_section_reports_categorical_exog():
    """
    Test that categorical exogenous columns are named, since statistical
    models cannot use them and the plan treats them specially.
    """
    section = render_dataset_section(profile_categorical)

    assert "- Categorical exogenous columns: weather" in section


def test_render_profile_decision_section_reports_temporal_structure():
    """
    Test that the profile decision carries the significant lags and the
    suggested window and calendar features, so a profile can be explained
    before any plan exists.
    """
    section = render_profile_decision_section(profile)
    first_lag = profile.series_pacf[0].lags[0]

    assert section.startswith("<profile_decision>\n" + profile.explanation)
    assert f"- Significant lags (partial autocorrelation, strongest first): {first_lag}" in section
    assert "- Suggested window features: mean(window=" in section


def test_render_script_section_describes_the_script_contract():
    """
    Test that the script section states the mode, the files the script
    reads, what it defines and which packages it imports, all taken from
    the code, without reproducing the code.
    """
    code = (
        "import pandas as pd\n"
        "from skforecast.recursive import ForecasterRecursive\n"
        "data = pd.read_csv('sales.csv')\n"
        "exog_future = pd.read_csv('exog_future.csv')\n"
        "predictions = None\n"
    )

    section = render_script_section(plan, code)

    assert "<script>" in section
    assert "- Mode: prediction: trains on all the data" in section
    assert "- Files read: sales.csv, exog_future.csv" in section
    assert "- Packages imported: pandas, skforecast" in section
    assert "- Length: 5 lines" in section
    assert "ForecasterRecursive" not in section
    assert render_script_section(None, code) == ""
    assert render_script_section(plan, None) == ""


_BACKTEST_CODE = (
    "import pandas as pd\n"
    "data = pd.read_csv('sales.csv')\n"
    "metrics, predictions = backtesting_forecaster(\n"
    "    forecaster = forecaster,\n"
    ")\n"
)


@pytest.mark.parametrize(
    "task_type, cv_config, expected_mode",
    [
        (
            "single_series",
            {"steps": 5, "n_folds": 6, "n_fits": 6},
            "backtesting: predicts 6 folds of 5 steps, training the forecaster "
            "6 times, and scores the predictions of every fold against the "
            "held-out observations",
        ),
        (
            "single_series",
            {"steps": 5, "n_folds": 1, "n_fits": 1},
            "backtesting: predicts 1 fold of 5 steps, training the forecaster "
            "1 time, and scores the predictions of every fold against the "
            "held-out observations",
        ),
        (
            "foundation",
            {"steps": 5, "n_folds": 3, "n_fits": 0},
            "backtesting: predicts 3 folds of 5 steps, without training the "
            "model (foundation model), and scores the predictions of every fold "
            "against the held-out observations",
        ),
        (
            "single_series",
            None,
            "backtesting: predicts every fold of a cross-validation strategy "
            "and scores it against the held-out observations (its folds could "
            "not be counted from the script)",
        ),
    ],
    ids=["several folds", "one fold", "foundation", "strategy not counted"],
)
def test_render_script_section_describes_backtesting_script(
    task_type, cv_config, expected_mode
):
    """
    Test that a script that calls a backtesting function is described as a
    backtest, with the folds and trainings of its strategy when they are
    known, and never as a prediction.
    """
    backtest_plan = plan.model_copy(update={"task_type": task_type})

    section = render_script_section(backtest_plan, _BACKTEST_CODE, cv_config=cv_config)

    assert f"- Mode: {expected_mode}\n" in section
    assert (
        "- Variables defined: metrics (one column per metric, one row per "
        "series when there are several), and predictions of every fold with "
        "a `fold` column\n"
    ) in section
    assert "prediction: trains on all the data" not in section

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


def test_render_comparison_overview_section_names_the_baseline():
    """
    Test that the overview names the baseline and how to read the rows
    ranked below it, and says nothing about a baseline when there is none.
    """
    comparison = make_comparison_result(assistant)
    with_baseline = comparison.model_copy(update={"baseline_name": "runner_up"})

    assert "- Baseline: runner_up (ForecasterEquivalentDate, repeats past values)." in (
        render_comparison_overview_section(with_baseline)
    )
    assert "Baseline" not in render_comparison_overview_section(comparison)


def test_render_plan_section_includes_baseline_offset():
    """
    Test that the plan section of a baseline plan states its offset, which
    is the only setting the baseline has.
    """
    baseline_plan = assistant.plan(
        profile, steps=5, forecaster="ForecasterEquivalentDate"
    )

    section = render_plan_section(baseline_plan)

    assert "- Baseline offset: 7 steps (n_offsets=1)" in section
    assert "- Estimator" not in section


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


def test_render_failures_section_output_when_for_describe_cuts_the_list():
    """
    Test that with `for_describe=True` only the first 15 failures are
    listed, followed by a line with the total, while the context of ask()
    lists all of them.
    """
    failure = make_comparison_result(assistant, with_failure=True).failures["broken"]
    failures = {f"broken_{i:02d}": failure for i in range(20)}

    section = render_failures_section(failures, for_describe=True)
    section_ask = render_failures_section(failures)

    assert "- broken_14: ImportError: No module named 'lightgbm'" in section
    assert "broken_15" not in section
    assert "Failures shown: the first 15 of 20" in section
    assert "- broken_19: ImportError: No module named 'lightgbm'" in section_ask
    assert "Failures shown" not in section_ask


# =============================================================================
# Tests: limits applied only for describe()
# =============================================================================
def _profile_with(**fields):
    """Copy of `profile_single` whose data profile has `fields` replaced."""
    data_profile = profile_single.data_profile.model_copy(update=fields)
    return profile_single.model_copy(update={"data_profile": data_profile})


def test_render_metrics_section_output_when_for_describe_and_forecast_metrics():
    """
    Test that with `for_describe=True` the per-series metrics of a forecast
    (a `series` column, no aggregated rows) keep the rows of the first 5
    series and say so without mentioning aggregated rows.
    """
    metrics = pd.DataFrame({
        "series": [f"s{i}" for i in range(8)],
        "MAE":    [float(i) for i in range(8)],
    })

    section = render_metrics_section(metrics, for_describe=True)

    expected = (
        "<evaluation_metrics>\n"
        "Rows of the first 5 of 8 series.\n"
        "series  MAE\n"
        "    s0  0.0\n"
        "    s1  1.0\n"
        "    s2  2.0\n"
        "    s3  3.0\n"
        "    s4  4.0\n"
        "</evaluation_metrics>"
    )
    assert section == expected
    assert render_metrics_section(metrics) == (
        f"<evaluation_metrics>\n{metrics.to_string(index=False)}\n"
        f"</evaluation_metrics>"
    )


@pytest.mark.parametrize(
    "metrics",
    [
        pd.DataFrame({
            "levels": ["a", "b", "c", "d", "e", "average", "pooling"],
            "MAE":    [1.0, 2.0, 3.0, 4.0, 5.0, 3.0, 3.0],
        }),
        pd.DataFrame({"MAE": [float(i) for i in range(8)]}),
    ],
    ids=["five series", "no series column"],
)
def test_render_metrics_section_output_when_for_describe_keeps_whole_table(
    metrics,
):
    """
    Test that with `for_describe=True` a table of at most 5 series, or one
    without a `levels` or `series` column, is rendered whole.
    """
    section = render_metrics_section(metrics, for_describe=True)

    assert section == render_metrics_section(metrics)


def test_render_dataset_section_output_when_for_describe_at_the_limit():
    """
    Test that with `for_describe=True` lists of exactly 15 items are not
    cut, and that 16 exogenous columns with missing values are cut to 15,
    the categorical ones too, with the totals stated.
    """
    columns_15 = [f"x{i:02d}" for i in range(15)]
    columns_16 = [f"x{i:02d}" for i in range(16)]
    profile_15 = _profile_with(
        exog_columns     = columns_15,
        categorical_exog = columns_15,
        missing_exog     = dict.fromkeys(columns_15, 2),
    )
    profile_16 = _profile_with(
        exog_columns     = columns_16,
        categorical_exog = columns_16,
        missing_exog     = dict.fromkeys(columns_16, 2),
    )

    section_15 = render_dataset_section(profile_15, for_describe=True)
    section_16 = render_dataset_section(profile_16, for_describe=True)

    assert section_15 == render_dataset_section(profile_15)
    shown = ", ".join(columns_15)
    assert f"- Exogenous columns: {shown} (first 15 of 16)\n" in section_16
    assert (
        f"- Categorical exogenous columns: {shown} (first 15 of 16)\n"
        in section_16
    )
    assert (
        f"- Missing in exog: {dict.fromkeys(columns_15, 2)} "
        f"(first 15 of 16 columns, 32 missing values in all)\n"
        in section_16
    )


def test_render_plan_section_output_when_for_describe_cuts_window_features():
    """
    Test that with `for_describe=True` the plan keeps the first 15 window
    features and says how many there are, while ask() lists all of them.
    """
    window_features = [
        {"stats": ["mean"], "window_size": size} for size in range(2, 18)
    ]
    plan = plan_single.model_copy(
        update={
            "forecaster_kwargs": {
                **plan_single.forecaster_kwargs,
                "window_features": window_features,
            }
        }
    )

    section = render_plan_section(plan, for_describe=True)

    assert (
        f"- Window features: {window_features[:15]} (first 15 of 16)\n"
        in section
    )
    assert f"- Window features: {window_features}\n" in render_plan_section(plan)


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


def test_render_cv_section_omits_training_parameters_when_not_trained():
    """
    Test that the section of a forecaster that is not trained (a foundation
    model) leaves out `refit` and `fixed_train_size`, which do not apply to
    it, and keeps the other parameters.
    """
    cv_config = {
        "steps": 5,
        "initial_train_size": 70,
        "refit": False,
        "fixed_train_size": True,
        "gap": 0,
        "n_folds": 6,
    }

    section = render_cv_section(cv_config, trains=False)

    assert section == (
        "<backtesting_strategy>\n"
        "- steps: 5\n"
        "- initial_train_size: 70\n"
        "- gap: 0\n"
        "- n_folds: 6\n"
        "</backtesting_strategy>"
    )
