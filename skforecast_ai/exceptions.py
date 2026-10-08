################################################################################
#                               Exceptions                                     #
#                                                                              #
# Custom exceptions for skforecast-ai                                          #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import TYPE_CHECKING, Literal, get_args

if TYPE_CHECKING:
    from .schemas.results import CandidateFailure


ErrorCode = Literal[
    "invalid_argument",
    "insufficient_data",
    "data_not_found",
    "data_unreadable",
    "missing_dependency",
    "execution_failed",
    "all_candidates_failed",
    "llm_required",
    "llm_call_failed",
    "internal_error",
]
"""Closed set of codes carried by `SkforecastAIError.code`."""

ERROR_CODES: tuple[str, ...] = get_args(ErrorCode)


class SkforecastAIError(Exception):
    """
    Base class of the errors raised by skforecast-ai.

    Every error carries a stable `code` from a closed set and, when one
    argument is at fault, its name in `field`, so a program (an agent, the
    CLI) can react to the kind of error without parsing the message. The
    message is the text of the exception; `hint` is an optional remedy kept
    out of it, so `str(exc)` is the message alone.

    Each subclass also derives from the built-in exception that was raised
    before the hierarchy existed (`ValueError`, `TypeError`,
    `FileNotFoundError`), so existing `except` clauses keep catching it.

    Parameters
    ----------
    message : str, default ''
        Error message, returned by `str(exc)`.
    code : str, default None
        One of `ERROR_CODES`. None uses the default code of the class.
    field : str, default None
        Name of the argument (or the field of a plan, profile or CV) at
        fault. None when the error is not tied to a single argument.
    hint : str, default None
        Optional remedy, not part of `str(exc)`.

    Attributes
    ----------
    code : str
        One of `ERROR_CODES`.
    field : str, None
        Name of the argument at fault.
    hint : str, None
        Optional remedy.
    """

    default_code: ErrorCode = "internal_error"

    def __init__(
        self,
        message: str = "",
        *,
        code: ErrorCode | None = None,
        field: str | None = None,
        hint: str | None = None,
    ) -> None:
        if code is not None and code not in ERROR_CODES:
            raise ValueError(
                f"Unknown error code {code!r}. Valid codes: {list(ERROR_CODES)}."
            )
        super().__init__(message)
        self.code = code if code is not None else self.default_code
        self.field = field
        self.hint = hint


class InvalidInputError(SkforecastAIError, ValueError):
    """
    Raised when an argument, or the plan, profile or CV passed in, is not
    valid.

    A subclass of `ValueError`, the class raised for these errors before
    skforecast-ai had its own hierarchy. The default code is
    `'invalid_argument'`; errors caused by too little data use
    `'insufficient_data'`, and a missing optional package
    `'missing_dependency'`.
    """

    default_code: ErrorCode = "invalid_argument"


class InvalidInputTypeError(InvalidInputError, TypeError):
    """
    Raised when an argument has a type that is not accepted.

    A subclass of `TypeError`, the class raised for these errors before
    skforecast-ai had its own hierarchy, and of `InvalidInputError`, so
    catching `InvalidInputError` covers every invalid input.
    """


class DataContentError(InvalidInputError):
    """
    Raised when the content of the data, or of the future exogenous
    variables, cannot be used for what was asked, although every argument
    is valid: a missing value of the target that a prediction or a metric
    reads, final rows without a target value, or future exogenous variables
    whose columns, dates or values do not fit the data and the plan.

    A subclass of `InvalidInputError`, with its code and its `field`
    (`'data'`, `'exog'` or `'test_size'`), so catching `InvalidInputError`
    or `ValueError` still covers it. Catch it to tell a problem of the
    values, which is solved in the data, from an argument to correct.
    """


class DataNotFoundError(SkforecastAIError, FileNotFoundError):
    """
    Raised when a file to read cannot be found: the data (a CSV path or
    URL), or a JSON or CSV input of the CLI.

    A subclass of `FileNotFoundError`, the class raised for these errors
    before skforecast-ai had its own hierarchy. The code is
    `'data_not_found'`.
    """

    default_code: ErrorCode = "data_not_found"


def _reported_type_name(exc: BaseException) -> str:
    """
    Class name under which an exception is reported in failure summaries.

    The input errors of skforecast-ai are reported under the built-in class
    they derive from (`ValueError`, `TypeError`, `FileNotFoundError`), the
    one raised for them before the hierarchy existed, so the summaries of
    `compare()` (and the message of `AllCandidatesFailedError` built from
    them) keep their text. Any other exception keeps its own name.

    Parameters
    ----------
    exc : BaseException
        Exception to name.

    Returns
    -------
    name : str
        Class name to report.
    """

    # InvalidInputTypeError first: it is also an InvalidInputError.
    for error_class, name in (
        (InvalidInputTypeError, "TypeError"),
        (InvalidInputError, "ValueError"),
        (DataNotFoundError, "FileNotFoundError"),
    ):
        if isinstance(exc, error_class):
            return name

    return type(exc).__name__


class LLMRequiredError(SkforecastAIError):
    """
    Raised when a method that requires an LLM is called without one.

    The code is `'llm_required'`.

    Parameters
    ----------
    method_name : str
        Name of the method that requires an LLM.
    """

    default_code: ErrorCode = "llm_required"

    def __init__(self, method_name: str) -> None:
        super().__init__(
            f"`{method_name}()` requires an LLM. "
            "Pass `llm=...` when creating ForecastingAssistant."
        )


class LLMCallError(SkforecastAIError):
    """
    Raised by `ask()` when the call to the LLM fails.

    `ask()` has no deterministic answer to fall back on, so a failed call
    (network, authentication, provider error, or a local model that is
    not reachable) is reported as an error instead of a result whose
    explanation is not an answer. The original exception is chained and
    kept as an attribute. The code is `'llm_call_failed'`.

    Parameters
    ----------
    llm : str
        LLM provider string in format `'provider:model_name'`.
    original_error : Exception
        The exception raised by the provider or the agent.

    Attributes
    ----------
    llm : str
        LLM provider string in format `'provider:model_name'`.
    original_error : Exception
        The exception raised by the provider or the agent.
    """

    default_code: ErrorCode = "llm_call_failed"

    def __init__(self, llm: str, original_error: Exception) -> None:
        self.llm = llm
        self.original_error = original_error

        error_type = type(original_error).__name__
        super().__init__(
            f"The call to the LLM '{llm}' failed.\n\n"
            f"  {error_type}: {original_error}\n\n"
            f"Check the provider, the model name and the credentials, then "
            f"retry. The original exception is available as `original_error`."
        )


class ForecastExecutionError(SkforecastAIError):
    """
    Raised when the generated forecasting code fails to compile or fails
    during exec().

    The short message surfaces the original error. The full generated
    code and traceback are available as attributes for debugging, together
    with the line and the statement of the generated code that failed. The
    code is `'execution_failed'`.

    Parameters
    ----------
    original_error : Exception
        The exception raised while compiling or executing the code.
    generated_code : str
        The generated Python code that was executed.
    execution_traceback : str
        The full formatted traceback from execution.
    failed_line : int, default None
        Line of `generated_code` (1-based) where the error was raised. None
        when it cannot be located. `generated_code` is the code that ran,
        without the CSV loading of the script that `forecast_code()` and
        `backtest_code()` return, so the numbering differs from that script.
    failed_statement : str, default None
        Source of the statement of `generated_code` that failed, all its
        lines included (only the header of a `for`, `if` or `with`
        statement, and only the line when the code does not compile). None
        when it cannot be located.

    Attributes
    ----------
    original_error : Exception
        The exception raised while compiling or executing the code.
    generated_code : str
        The generated Python code that was executed.
    execution_traceback : str
        The full formatted traceback from execution.
    failed_line : int, None
        Line of `generated_code` (1-based) where the error was raised.
    failed_statement : str, None
        Source of the statement of `generated_code` that failed.
    """

    default_code: ErrorCode = "execution_failed"

    def __init__(
        self,
        original_error: Exception,
        generated_code: str,
        execution_traceback: str,
        failed_line: int | None = None,
        failed_statement: str | None = None,
    ) -> None:
        self.original_error = original_error
        self.generated_code = generated_code
        self.execution_traceback = execution_traceback
        self.failed_line = failed_line
        self.failed_statement = failed_statement

        error_type = type(original_error).__name__
        error_msg = str(original_error)
        message = (
            f"Error executing generated forecasting code.\n\n"
            f"  {error_type}: {error_msg}"
        )
        super().__init__(message)


class AllCandidatesFailedError(SkforecastAIError):
    """
    Raised by `compare()` when every candidate configuration fails.

    A comparison with zero successful candidates has no leaderboard and
    no winner, so it is reported as a failure instead of returning a
    winner-less result. The code is `'all_candidates_failed'`.

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

    default_code: ErrorCode = "all_candidates_failed"

    def __init__(self, failures: dict[str, CandidateFailure]) -> None:
        self.failures = failures

        message = (
            f"{_all_candidates_failed_summary(failures)}\n\n"
            f"Inspect a failure with `exc.failures['<name>'].traceback` or "
            f"`exc.failures['<name>'].generated_code`."
        )
        super().__init__(message)


def _all_candidates_failed_summary(failures: dict[str, CandidateFailure]) -> str:
    """
    Describe a comparison in which every candidate failed, one line per
    candidate, without the Python attributes to inspect.

    `AllCandidatesFailedError` adds to it how to inspect a failure in
    Python; `ErrorInfo` uses it alone, since a reader outside Python cannot
    reach `exc.failures`.

    Parameters
    ----------
    failures : dict
        Mapping of candidate name to its `CandidateFailure`.

    Returns
    -------
    summary : str
        Count of failed candidates and one summary line per candidate.
    """

    details = "\n".join(
        f"  - {name}: {failure.summary()}" for name, failure in failures.items()
    )

    return (
        f"All {len(failures)} candidate configuration(s) failed to run, "
        f"so there is no ranking to report.\n\n"
        f"{details}"
    )


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

    `ask(context=...)` always sends the predicted values a result carries,
    because a question about a result cannot be answered from summary
    statistics alone. That override is silent otherwise, so a user who set
    `send_data_to_llm=False` for privacy reasons would still ship values
    off the machine without being told. A result that carries no such
    values (for example a `CodeGenerationResult`) does not trigger it.

    The input data is not sent: a result holds only the model's output,
    never the data it was fitted on.
    """


class MissingBackendWarning(UserWarning):
    """
    Warned by `compare()` when a foundation model candidate is left out.

    `compare()` without `candidates` includes `ForecasterFoundation`, whose
    default model needs a backend package (for Chronos-2,
    `chronos-forecasting`) that skforecast-ai does not install by default.
    When that package is missing, the candidate is dropped instead of
    failing on every call, and this warning says which package to install.
    The comparison explanation records it as well.
    """


class PlanEditsDiscardedWarning(UserWarning):
    """
    Warned by `refine_plan()` when edits made to the plan are discarded.

    `refine_plan()` builds the refined plan with `plan()`, from the
    decisions it carries over (the overrides of `RefinePlanOverrides` and
    the fields in `ForecastPlan.overridden_fields`). A value changed by
    hand in the plan (in `forecaster_kwargs`, the metric, the
    preprocessing steps...) that `plan()` would not build is therefore
    lost. The warning names those fields; its text is also kept in the
    `warnings` of the refined plan.
    """


class UnrecommendedForecasterWarning(UserWarning):
    """
    Warned by `plan()` when the requested forecaster is not recommended.

    The forecaster is supported and is used as requested, but it was left
    out of `ForecastingProfile.forecaster_candidates` for this dataset,
    typically because it is expected to be very slow or to perform poorly
    (for example, Auto-ARIMA on high-frequency data).
    """
