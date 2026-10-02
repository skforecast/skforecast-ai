# Unit test describe skforecast_ai.schemas.explainable

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant
from skforecast_ai._constants import MAX_LEADERBOARD_ROWS
from skforecast_ai.llm.context import (
    LEADERBOARD_NOTE,
    PLAN_CODE_NOTE,
    RANKING_NOTE,
    SCRIPT_NOTE,
)

from tests.fixtures_assistant import df_no_exog
from tests.fixtures_llm import (
    GOLDEN_DESCRIBE_SCENARIOS,
    GOLDEN_SCENARIOS,
    ROW_LEVEL_MARKER,
    make_backtest_result,
    make_code_generation_result,
    make_comparison_result,
    make_cv_result,
    make_forecast_result,
    make_single_run_result,
    predictions_single,
    profile_single,
)

GOLDEN_DESCRIBE_DIR = Path(__file__).parent / "golden_describe"

# Each sentence addressed to the LLM of `ask()`, with the separator that
# precedes it in the context, so removing both gives `describe()`.
ASK_INSTRUCTIONS = (
    ("\n\n", PLAN_CODE_NOTE),
    ("\n", SCRIPT_NOTE),
    (" ", RANKING_NOTE),
    (" ", LEADERBOARD_NOTE),
)

# The golden scenarios, every list within the limits of describe(), plus
# a comparison whose leaderboard is truncated, the only case that renders
# `LEADERBOARD_NOTE`.
DESCRIBE_CASES = {
    **GOLDEN_SCENARIOS,
    "comparison_truncated_leaderboard": lambda: make_comparison_result(
        n_candidates=MAX_LEADERBOARD_ROWS + 3
    ),
}


def _without_ask_instructions(text: str) -> str:
    """Remove the sentences addressed to the LLM of `ask()` from a context."""
    for separator, sentence in ASK_INSTRUCTIONS:
        text = text.replace(separator + sentence, "")
    return text


# =============================================================================
# Tests: describe() matches its golden file
# =============================================================================
@pytest.mark.parametrize(
    "scenario",
    sorted(GOLDEN_DESCRIBE_SCENARIOS),
    ids=lambda dt: f"golden describe: {dt}"
)
def test_describe_output_matches_golden(scenario):
    """
    Test that describe() for each result scenario matches the stored golden
    file byte for byte. Regenerate with
    `python tools/ai/update_golden_contexts.py` and review the diff
    whenever the change is intentional.
    """
    path = GOLDEN_DESCRIBE_DIR / f"{scenario}.txt"
    assert path.exists(), (
        f"Missing golden file for '{scenario}'. "
        f"Run 'python tools/ai/update_golden_contexts.py' to create it."
    )

    description = GOLDEN_DESCRIBE_SCENARIOS[scenario]().describe()

    assert description + "\n" == path.read_text(encoding="utf-8")


def test_describe_golden_directory_has_no_orphan_files():
    """
    Test that every describe() golden file on disk still belongs to a
    scenario, so renaming or deleting a scenario cannot leave a stale file
    behind.
    """
    on_disk = {path.stem for path in GOLDEN_DESCRIBE_DIR.glob("*.txt")}

    assert on_disk == set(GOLDEN_DESCRIBE_SCENARIOS)


# =============================================================================
# Tests: describe() is the context of ask() without its instructions
# =============================================================================
@pytest.mark.parametrize(
    "scenario",
    sorted(DESCRIBE_CASES),
    ids=lambda dt: f"{dt}"
)
def test_describe_output_equals_ask_context_without_llm_instructions(scenario):
    """
    Test that describe() is exactly the context ask() builds with
    `send_data=False`, minus the sentences addressed to the LLM, and that
    none of those sentences is left in it.
    """
    result = DESCRIBE_CASES[scenario]()
    context = result.to_llm_context(send_data=False).text

    description = result.describe()

    assert description == _without_ask_instructions(context)
    for _, sentence in ASK_INSTRUCTIONS:
        assert sentence not in description


@pytest.mark.parametrize(
    "scenario, expected_sentences",
    [
        ("code_generation_result", [PLAN_CODE_NOTE, SCRIPT_NOTE]),
        ("forecast_single_series_no_intervals", [PLAN_CODE_NOTE]),
        ("comparison_all_succeeded", [PLAN_CODE_NOTE, RANKING_NOTE]),
        (
            "comparison_truncated_leaderboard",
            [PLAN_CODE_NOTE, RANKING_NOTE, LEADERBOARD_NOTE],
        ),
    ],
    ids=lambda value: f"{value}",
)
def test_describe_output_when_ask_context_has_llm_instructions(
    scenario, expected_sentences
):
    """
    Test that the context of ask() still holds each sentence addressed to
    the LLM where it did before, so the equality with describe() is not
    met by removing nothing.
    """
    context = DESCRIBE_CASES[scenario]().to_llm_context(send_data=False).text

    for sentence in expected_sentences:
        assert sentence in context


# =============================================================================
# Tests: describe() never includes row-level values
# =============================================================================
@pytest.mark.parametrize(
    "build_result",
    [
        make_single_run_result,
        make_forecast_result,
        lambda: make_backtest_result(predictions=predictions_single),
    ],
    ids=["SingleRunResult", "ForecastResult", "BacktestResult"],
)
def test_describe_output_has_no_row_level_values(build_result):
    """
    Test that describe() summarizes the predictions instead of listing
    them: the marker value planted in a prediction row never appears,
    while the context of ask() with `send_data=True` does carry it.
    """
    result = build_result()

    description = result.describe()

    assert ROW_LEVEL_MARKER not in description
    assert ROW_LEVEL_MARKER in result.to_llm_context(send_data=True).text


# =============================================================================
# Tests: every result type
# =============================================================================
@pytest.mark.parametrize(
    "build_result",
    [
        lambda: profile_single,
        make_code_generation_result,
        make_cv_result,
        make_single_run_result,
        make_forecast_result,
        make_backtest_result,
        make_comparison_result,
    ],
    ids=[
        "ForecastingProfile",
        "CodeGenerationResult",
        "CVResult",
        "SingleRunResult",
        "ForecastResult",
        "BacktestResult",
        "ComparisonResult",
    ],
)
def test_describe_output_when_each_result_type(build_result):
    """
    Test that every result type that ask() accepts describes itself with a
    non-empty text wrapped in the same `<forecast_context>` tag as the
    context of ask(), starting with the dataset section.
    """
    description = build_result().describe()

    assert isinstance(description, str)
    assert description.startswith("<forecast_context>\n<dataset>\n")
    assert description.endswith("\n</forecast_context>")


def test_describe_output_when_backtest_code_result():
    """
    Test that the script of `backtest_code()` is described as a backtest,
    with the folds and trainings of its strategy and the same
    `<backtesting_strategy>` section as the result of `backtest()`, in
    describe() and in the context of ask().
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = assistant.create_cv(profile, plan)
    result = assistant.backtest_code(
        data        = df_no_exog,
        cv          = cv,
        target      = "sales",
        date_column = "date",
        profile     = profile,
        plan        = plan,
    )

    backtest = assistant.backtest(
        data          = df_no_exog,
        cv            = cv,
        profile       = profile,
        plan          = plan,
        show_progress = False,
    )

    description = result.describe()

    assert (
        "- Mode: backtesting: predicts 6 folds of 5 steps, training the "
        "forecaster 1 time, and scores the predictions of every fold against "
        "the held-out observations\n"
    ) in description
    assert "- Mode: prediction" not in description
    strategy = description[
        description.index("<backtesting_strategy>"):
        description.index("</backtesting_strategy>")
    ]
    # The script does not write `fixed_train_size` without refits (it has
    # no effect then), so it is the only line of `backtest()` left out.
    assert strategy == backtest.describe()[
        backtest.describe().index("<backtesting_strategy>"):
        backtest.describe().index("</backtesting_strategy>")
    ].replace("- fixed_train_size: False\n", "")
    assert "- n_folds: 6\n- n_fits: 1\n" in strategy
    assert description == _without_ask_instructions(
        result.to_llm_context(send_data=False).text
    )


# =============================================================================
# Tests: limits of describe() with many series
# =============================================================================
def test_describe_output_when_many_series_cuts_each_list():
    """
    Test that describe() keeps the first 15 items of each list (target
    columns, exogenous columns, series with missing values, lags) and the
    statistics, significant lags and metrics of the first 5 series plus
    the aggregated metric rows, and says how many there are.
    """
    description = GOLDEN_DESCRIBE_SCENARIOS["backtest_many_series"]().describe()

    expected_lines = [
        "- Target: ['series_000', 'series_001', 'series_002', 'series_003', "
        "'series_004', 'series_005', 'series_006', 'series_007', 'series_008', "
        "'series_009', 'series_010', 'series_011', 'series_012', 'series_013', "
        "'series_014'] (first 15 of 500)",
        "- Exogenous columns: exog_00, exog_01, exog_02, exog_03, exog_04, "
        "exog_05, exog_06, exog_07, exog_08, exog_09, exog_10, exog_11, "
        "exog_12, exog_13, exog_14 (first 15 of 20)",
        "- Target statistics shown for the first 5 of 500 series",
        "- Missing in target: {'series_000': 1, 'series_001': 1, "
        "'series_002': 1, 'series_003': 1, 'series_004': 1, 'series_005': 1, "
        "'series_006': 1, 'series_007': 1, 'series_008': 1, 'series_009': 1, "
        "'series_010': 1, 'series_011': 1, 'series_012': 1, 'series_013': 1, "
        "'series_014': 1} (first 15 of 30 series, 30 missing values in all)",
        "- Significant lags shown only for the first 5 of 500 series (a series "
        "without significant lags has no line)",
        "- Lags: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15] "
        "(first 15 of 30)",
    ]
    for line in expected_lines:
        assert f"{line}\n" in description

    expected_metrics = (
        "<evaluation_metrics>\n"
        "Rows of the first 5 of 500 series, plus the aggregated rows.\n"
        "          levels  mean_absolute_error\n"
        "      series_000                 5.00\n"
        "      series_001                 5.01\n"
        "      series_002                 5.02\n"
        "      series_003                 5.03\n"
        "      series_004                 5.04\n"
        "         average                 7.50\n"
        "weighted_average                 7.50\n"
        "         pooling                 7.40\n"
        "</evaluation_metrics>"
    )
    assert expected_metrics in description
    assert "series_015" not in description.split("<profile_decision>")[0]
    assert "series_005 " not in description


def test_describe_output_when_many_series_stays_short_and_ask_is_whole():
    """
    Test that describe() of 500 series stays under 4,500 characters, while
    the context of ask() keeps every series and lag, as before the limits.
    """
    result = GOLDEN_DESCRIBE_SCENARIOS["backtest_many_series"]()

    description = result.describe()
    context = result.to_llm_context(send_data=False).text

    assert len(description) < 4500
    assert len(context) > 25000
    assert "'series_499'" in context
    assert "      series_499 " in context
    assert "(first 15 of" not in context


def test_describe_output_when_many_data_warnings():
    """
    Test that describe() lists the first 15 data warnings of the profile
    and a line with their total.
    """
    data_profile = profile_single.data_profile.model_copy(
        update={"warnings": [f"Note number {i}." for i in range(20)]}
    )
    profile = profile_single.model_copy(update={"data_profile": data_profile})

    description = profile.describe()

    assert "- Data warning: Note number 14.\n" in description
    assert "Note number 15." not in description
    assert "- Data warnings shown: the first 15 of 20\n" in description
    assert "- Data warning: Note number 19.\n" in (
        profile.to_llm_context(send_data=False).text
    )


def test_describe_output_when_many_categorical_exog_cuts_preprocessing_reason():
    """
    Test that, with 500 categorical exogenous columns, the reason of the
    categorical preprocessing step names the first 15 and their total, in
    describe() and in the context of ask(), since it is cut where the plan
    is built: describe() of the plan stays under 3,000 characters (7,855
    when the reason listed every column).
    """
    rng = np.random.default_rng(0)
    index = pd.date_range("2023-01-01", periods=120, freq="D", name="date")
    data = pd.concat(
        [
            pd.DataFrame({"y": rng.normal(100, 10, 120).round(2)}, index=index),
            pd.DataFrame(
                {f"cat_{i:03d}": rng.choice(["a", "b"], 120) for i in range(500)},
                index=index,
            ),
        ],
        axis=1,
    )
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=data, target="y")
    plan = assistant.plan(profile, steps=3)
    result = assistant.forecast_code(profile=profile, plan=plan)

    description = result.describe()
    context = result.to_llm_context(send_data=False).text

    expected = (
        "Categorical exogenous variables detected: ['cat_000', 'cat_001', "
        "'cat_002', 'cat_003', 'cat_004', 'cat_005', 'cat_006', 'cat_007', "
        "'cat_008', 'cat_009', 'cat_010', 'cat_011', 'cat_012', 'cat_013', "
        "'cat_014'] (first 15 of 500)."
    )
    assert expected in description
    assert expected in context
    assert "'cat_015'" not in description
    assert len(description) < 3000


def test_describe_output_when_backtest_code_strategy_cannot_be_counted():
    """
    Test that the script of `backtest_code()` with a `pd.Timestamp` as
    `initial_train_size`, whose folds cannot be counted, is still described
    as a backtest, saying that the folds were not counted, instead of
    failing.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv = TimeSeriesFold(steps=5, initial_train_size=pd.Timestamp("2023-03-11"))
    result = assistant.backtest_code(data=None, cv=cv, profile=profile, plan=plan)

    description = result.describe()

    assert "initial_train_size = pd.Timestamp('2023-03-11 00:00:00')" in result.code
    assert (
        "- Mode: backtesting: predicts every fold of a cross-validation "
        "strategy and scores it against the held-out observations (its folds "
        "could not be counted from the script)\n"
    ) in description
    assert "<backtesting_strategy>" not in description
