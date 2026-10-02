# Unit test describe skforecast_ai.schemas.explainable

from pathlib import Path

import pytest

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

# The golden scenarios plus a comparison whose leaderboard is truncated,
# the only case that renders `LEADERBOARD_NOTE`.
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
    sorted(GOLDEN_SCENARIOS),
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

    description = GOLDEN_SCENARIOS[scenario]().describe()

    assert description + "\n" == path.read_text(encoding="utf-8")


def test_describe_golden_directory_has_no_orphan_files():
    """
    Test that every describe() golden file on disk still belongs to a
    scenario, so renaming or deleting a scenario cannot leave a stale file
    behind.
    """
    on_disk = {path.stem for path in GOLDEN_DESCRIBE_DIR.glob("*.txt")}

    assert on_disk == set(GOLDEN_SCENARIOS)


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
    Test the limitation stated in the docstring of describe(): the script
    of `backtest_code()` is described as the one of the plan in prediction
    mode, as in the context of ask(). The test pins it, so a fix shows up
    here.
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

    description = result.describe()

    assert "backtesting_forecaster(" in result.code
    assert (
        "- Mode: prediction: trains on all the data and forecasts the next 5 "
        "steps\n"
    ) in description
    assert description == _without_ask_instructions(
        result.to_llm_context(send_data=False).text
    )
