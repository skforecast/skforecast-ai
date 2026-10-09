# Unit test failure_text

from skforecast_ai.exceptions import (
    AllCandidatesFailedError,
    ForecastExecutionError,
    InvalidInputError,
)
from skforecast_ai.mcp._errors import (
    candidate_failure_text,
    error_payload,
    failure_text,
    without_install_paths,
)
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


def test_without_install_paths_output():
    """
    Test that the file paths of a traceback are cut to what identifies the
    module (after `site-packages`, from `skforecast_ai/`, or the file name),
    so the home directory and the name of the user never reach the agent,
    while the generated script and the line numbers are kept.
    """
    text = (
        "Traceback (most recent call last):\n"
        '  File "/Users/jane/envs/x/lib/python3.13/site-packages/sklearn/base.py", '
        "line 10, in fit\n"
        '  File "/Users/jane/code/skforecast-ai/skforecast_ai/execution/_exec.py", '
        "line 5, in run\n"
        '  File "C:\\Users\\jane\\run.py", line 2, in <module>\n'
        '  File "<forecast>", line 31, in <module>\n'
        "ValueError: bad"
    )

    assert without_install_paths(text) == (
        "Traceback (most recent call last):\n"
        '  File "sklearn/base.py", line 10, in fit\n'
        '  File "skforecast_ai/execution/_exec.py", line 5, in run\n'
        '  File "run.py", line 2, in <module>\n'
        '  File "<forecast>", line 31, in <module>\n'
        "ValueError: bad"
    )
    assert without_install_paths(None) is None


def test_error_payload_names_only_the_type_of_a_failure_not_of_skforecast_ai():
    """
    Test that `execution_failed` and `all_candidates_failed` send the type
    of an error that skforecast-ai did not raise, not its message (which can
    quote a value of the data), and keep the message of one it raised.
    """
    script = ForecastExecutionError(
        original_error=ValueError("could not convert string to float: 'SECRET'"),
        generated_code="x",
        execution_traceback="tb",
    )
    comparison = AllCandidatesFailedError(
        {
            "a": CandidateFailure(
                error_type="ValueError", message="bad 'SECRET'", traceback="tb",
                generated_code=None,
            ),
            "b": CandidateFailure(
                error_type="InvalidInputError", message="`lags` must be positive.",
                traceback="tb", generated_code=None,
            ),
        }
    )

    script_message = error_payload(script)["message"]
    comparison_message = error_payload(comparison)["message"]

    assert script_message == (
        "The generated script failed with ValueError. Its message, the "
        "traceback and the code that ran are in `get_failure`, with the "
        "`failure_id` of `details`."
    )
    assert "SECRET" not in comparison_message
    assert comparison_message.endswith(
        "  - a: ValueError\n  - b: InvalidInputError: `lags` must be positive."
    )
