# Unit test failure_text

from skforecast_ai.exceptions import (
    AllCandidatesFailedError,
    ForecastExecutionError,
    InvalidInputError,
)
from skforecast_ai.mcp._errors import candidate_failure_text, failure_text
from skforecast_ai.schemas import CandidateFailure


def test_failure_text_of_a_script_and_of_a_comparison():
    """
    Test the full text of a failed script (error, line, statement, traceback
    and code) and of a comparison whose candidates all failed, and that any
    other error has none.
    """
    script = ForecastExecutionError(
        original_error=KeyError("x"),
        generated_code="y = data['x']",
        execution_traceback="Traceback (most recent call last): ...",
        failed_line=1,
        failed_statement="y = data['x']",
    )
    comparison = AllCandidatesFailedError(
        {
            "a": CandidateFailure(
                error_type="ValueError",
                message="Bad.",
                traceback="tb",
                generated_code=None,
            ),
        }
    )

    assert failure_text(script) == (
        "Error executing generated forecasting code.\n\n  KeyError: 'x'\n\n"
        "Failed line of the code that ran: 1\n\n"
        "Failed statement:\ny = data['x']\n\n"
        "Traceback:\nTraceback (most recent call last): ...\n\n"
        "Code that ran:\ny = data['x']"
    )
    assert (
        failure_text(comparison)
        == "Candidate 'a' failed: ValueError: Bad.\n\nTraceback:\ntb"
    )
    assert failure_text(InvalidInputError("Bad.")) is None


def test_candidate_failure_text_with_and_without_code():
    """
    Test the text of the failure of a candidate, with the code that ran when
    there is one.
    """
    failure = CandidateFailure(
        error_type="KeyError",
        message="'x'",
        traceback="tb",
        generated_code="y = 1",
    )

    assert candidate_failure_text("a", failure) == (
        "Candidate 'a' failed: KeyError: 'x'\n\nTraceback:\ntb\n\nCode that ran:\ny = 1"
    )
