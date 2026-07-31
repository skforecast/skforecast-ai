################################################################################
#                               Exceptions                                     #
#                                                                              #
# Custom exceptions for skforecast-ai                                          #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schemas.results import CandidateFailure


class LLMRequiredError(Exception):
    """
    Raised when a method that requires an LLM is called without one.

    Parameters
    ----------
    method_name : str
        Name of the method that requires an LLM.
    """

    def __init__(self, method_name: str) -> None:
        super().__init__(
            f"`{method_name}()` requires an LLM. "
            "Pass `llm=...` when creating ForecastingAssistant."
        )


class ForecastExecutionError(Exception):
    """
    Raised when the generated forecasting code fails during exec().

    The short message surfaces the original error. The full generated
    code and traceback are available as attributes for debugging.

    Parameters
    ----------
    original_error : Exception
        The exception raised during code execution.
    generated_code : str
        The generated Python code that was executed.
    execution_traceback : str
        The full formatted traceback from execution.

    Attributes
    ----------
    original_error : Exception
        The exception raised during code execution.
    generated_code : str
        The generated Python code that was executed.
    execution_traceback : str
        The full formatted traceback from execution.
    """

    def __init__(
        self,
        original_error: Exception,
        generated_code: str,
        execution_traceback: str,
    ) -> None:
        self.original_error = original_error
        self.generated_code = generated_code
        self.execution_traceback = execution_traceback

        error_type = type(original_error).__name__
        error_msg = str(original_error)
        message = (
            f"Error executing generated forecasting code.\n\n"
            f"  {error_type}: {error_msg}"
        )
        super().__init__(message)


class AllCandidatesFailedError(Exception):
    """
    Raised by `compare()` when every candidate configuration fails.

    A comparison with zero successful candidates has no leaderboard and
    no winner, so it is reported as a failure instead of returning a
    winner-less result.

    Parameters
    ----------
    failures : dict
        Mapping of candidate name to the `CandidateFailure` describing
        why it failed, in the order the candidates were evaluated.

    Attributes
    ----------
    failures : dict
        Mapping of candidate name to its `CandidateFailure`.
    """

    def __init__(self, failures: dict[str, CandidateFailure]) -> None:
        self.failures = failures

        details = "\n".join(
            f"  - {name}: {failure.summary()}"
            for name, failure in failures.items()
        )
        message = (
            f"All {len(failures)} candidate configuration(s) failed to run, "
            f"so there is no ranking to report.\n\n"
            f"{details}\n\n"
            f"Inspect a failure with `exc.failures['<name>'].traceback` or "
            f"`exc.failures['<name>'].generated_code`."
        )
        super().__init__(message)


class CandidateFailedWarning(UserWarning):
    """
    Warned by `compare()` when an individual candidate fails.

    The comparison continues with the remaining candidates; the failure
    is recorded in the `'error'` column of the results table and a
    `CandidateFailure` is kept in `ComparisonResult.failures`.
    """


class DataSentToLLMWarning(UserWarning):
    """
    Warned when data values are sent to the LLM against `send_data_to_llm`.

    `ask(result=...)` always sends the predicted values a result carries,
    because a question about a result cannot be answered from summary
    statistics alone. That override is silent otherwise, so a user who set
    `send_data_to_llm=False` for privacy reasons would still ship values
    off the machine without being told.

    The input data is not sent: a result holds only the model's output,
    never the data it was fitted on.
    """


class UnrecommendedForecasterWarning(UserWarning):
    """
    Warned by `plan()` when the requested forecaster is not recommended.

    The forecaster is supported and is used as requested, but it was left
    out of `ForecastingProfile.forecaster_candidates` for this dataset,
    typically because it is expected to be very slow or to perform poorly
    (for example, Auto-ARIMA on high-frequency data).
    """
