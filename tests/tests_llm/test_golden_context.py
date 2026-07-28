# Unit test golden LLM contexts skforecast_ai.llm.context

from pathlib import Path

import pytest

from skforecast_ai.llm.context import build_context_message

from tests.fixtures_llm import GOLDEN_SCENARIOS

GOLDEN_DIR = Path(__file__).parent / "golden"


# =============================================================================
# Tests: rendered context matches its golden file
# =============================================================================
@pytest.mark.parametrize(
    "scenario",
    sorted(GOLDEN_SCENARIOS),
    ids=lambda dt: f"golden context: {dt}"
)
def test_llm_context_matches_golden(scenario):
    """
    Test that the context rendered for each result scenario matches the
    stored golden file byte for byte.

    The rendered string is the whole contract between the deterministic
    code and the LLM, so it is asserted as a unit rather than by
    substring. A substring assertion cannot catch a section that silently
    stopped being rendered, which is the defect class these files exist
    to prevent. Regenerate with
    `python tools/update_golden_llm_contexts.py` and review the diff
    whenever the change is intentional.
    """
    path = GOLDEN_DIR / f"{scenario}.txt"
    assert path.exists(), (
        f"Missing golden file for '{scenario}'. "
        f"Run 'python tools/update_golden_llm_contexts.py' to create it."
    )

    context = GOLDEN_SCENARIOS[scenario]().to_llm_context(send_data=True)

    assert context.text + "\n" == path.read_text(encoding="utf-8")


def test_golden_directory_has_no_orphan_files():
    """
    Test that every golden file on disk still belongs to a scenario, so
    renaming or deleting a scenario cannot leave a stale file behind that
    silently stops being asserted.
    """
    on_disk = {path.stem for path in GOLDEN_DIR.glob("*.txt")}

    assert on_disk == set(GOLDEN_SCENARIOS)


def test_llm_context_output_when_no_result_is_available():
    """
    Test that the question-only path renders nothing. `ask()` without a
    result must not emit an empty `<forecast_context>` wrapper, since an
    empty block invites the model to treat missing context as an assertion
    that there is no data.
    """
    assert build_context_message() == ""
