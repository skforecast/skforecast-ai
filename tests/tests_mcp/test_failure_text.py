# Unit test failure_text

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.exceptions import (
    AllCandidatesFailedError,
    CandidateFailedWarning,
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

from ..fixtures_datasets import df_h2o


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
    quote a value of the data), and keep the message of one it raised. The
    comparison is a real one whose candidates fail with an error of
    LightGBM inside the script and with an `InvalidInputError` of the plan,
    which a candidate failure names by its own class (V32: it was named
    `ValueError` and its message was left out).
    """
    script = ForecastExecutionError(
        original_error=ValueError("could not convert string to float: 'SECRET'"),
        generated_code="x",
        execution_traceback="tb",
    )
    assistant = ForecastingAssistant()
    profile = assistant.profile(df_h2o, target="x")
    cv = assistant.create_cv(profile, assistant.plan(profile, steps=12))
    candidates = [
        ("lgbm", {"estimator": "LGBMRegressor", "estimator_kwargs": {"num_leaves": 1}}),
        ("ridge", {"estimator": "Ridge", "estimator_kwargs": {"alpha": -1}}),
    ]
    # The plan of the strategy (Ridge) is none of the candidates.
    with pytest.raises(AllCandidatesFailedError) as exc_info:
        with pytest.warns(UserWarning, match="so it was not compared"):
            with pytest.warns(CandidateFailedWarning):
                assistant.compare(
                    df_h2o, target="x", cv=cv, candidates=candidates,
                    baseline=False,
                )

    script_message = error_payload(script)["message"]
    comparison_message = error_payload(exc_info.value)["message"]

    assert script_message == (
        "The generated script failed with ValueError. Its message, the "
        "traceback and the code that ran are in `get_failure`, with the "
        "`failure_id` of `details`."
    )
    assert exc_info.value.failures["ridge"].error_type == "InvalidInputError"
    assert "Check failed" not in comparison_message
    assert comparison_message.endswith(
        "  - lgbm: LightGBMError\n"
        "  - ridge: InvalidInputError: `estimator_kwargs` is not valid for Ridge: "
        "The 'alpha' parameter of Ridge must be a float in the range [0.0, inf) "
        "or an array-like. Got -1 instead."
    )
