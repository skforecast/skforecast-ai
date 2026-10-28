################################################################################
#                               Exceptions                                     #
#                                                                              #
# Custom exceptions for skforecast-ai                                          #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import TYPE_CHECKING, Literal, get_args

if TYPE_CHECKING:
    from .schemas.results import CandidateFailure, ComparisonCost


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


class CostNotConfirmedError(InvalidInputError):
    """
    Raised by `backtest()` and `compare()` before anything runs when the
    run is above the thresholds of an expensive run (50 estimator fits or
    2000 inference windows of a foundation model; for a comparison, all
    its candidates together) and `confirm_cost` does not confirm it.

    The message states the cost, what makes it and the changes that lower
    it; `hint` says how to run it as it is. A subclass of
    `InvalidInputError`, with the code `'invalid_argument'` and the field
    `'confirm_cost'`.

    Parameters
    ----------
    message : str
        Error message, returned by `str(exc)`.
    figure : int
        Number that confirms the run, see the attribute.
    cost : dict
        Cost of the run, see the attribute.
    description : str
        Sentence stating the cost, see the attribute.
    comparison_cost : ComparisonCost, default None
        Cost of each candidate of a comparison.
    hint : str, default None
        How to run it as it is.

    Attributes
    ----------
    figure : int
        Number that confirms the run as `confirm_cost`: its estimator
        fits, or its inference windows when only those are above their
        threshold.
    cost : dict
        `n_folds`, `n_fits` (trainings), `estimator_fits` and
        `inference_windows` of the run; for a comparison, the folds of
        the shared strategy and the totals of its candidates.
    description : str
        Sentence stating the cost and what makes it, without how to lower
        it or how to confirm it.
    comparison_cost : ComparisonCost, None
        Cost of each candidate of a comparison, None for a backtest.
    """

    def __init__(
        self,
        message: str,
        *,
        figure: int,
        cost: dict[str, int],
        description: str,
        comparison_cost: ComparisonCost | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message, field="confirm_cost", hint=hint)
        self.figure = figure
        self.cost = cost
        self.description = description
        self.comparison_cost = comparison_cost


class DataNotFoundError(SkforecastAIError, FileNotFoundError):
    """
    Raised when a file to read cannot be found: the data (a CSV path or
    URL), or a JSON or CSV input of the CLI.

    A subclass of `FileNotFoundError`, the class raised for these errors
    before skforecast-ai had its own hierarchy. The code is
    `'data_not_found'`.
    """

    default_code: ErrorCode = "data_not_found"


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


class FoldsLeftOutWarning(UserWarning):
    """
    Warned by `backtest()` and `compare()` when the backtest of several
    series did not forecast a series in some test folds where it has
    values to evaluate.

    `ForecasterRecursiveMultiSeries` and a `ForecasterFoundation` model
    leave a series out of a fold they cannot forecast (one that starts
    late, say) without a warning of skforecast. The folds that forecast
    each series are read from the `level` and `fold` of the predictions:
    the metrics of a series left out of some folds, and the average across
    series, are computed on fewer folds than those of the others. The
    warning names the series (in `compare()`, the candidates) with those
    folds, as the explanation does. A series that no fold forecasts raises
    before running instead.
    """


class IntervalCoverageWarning(UserWarning):
    """
    Warned by `backtest()` and `compare()` when the prediction interval
    covers clearly less than its nominal level.

    The backtesting of skforecast measures the share of the actual values
    that fall inside the interval (`coverage` in the metrics). The warning
    is emitted when, in any series, that share is below the nominal coverage
    (`upper - lower` of `interval`) by more than two binomial standard
    errors for the number of predictions, and by at least 5 percentage
    points. It names the series (or, in `compare()`, the candidates) and
    their coverage: such an interval must not be read at its nominal level.
    """


class MissingBackendWarning(UserWarning):
    """
    Warned when a model needs a package that is not installed: by
    `compare()` when it leaves a candidate out, and by `plan()` when the
    estimator of the plan is one of them.

    `compare()` without `candidates` includes `ForecasterFoundation`, whose
    default model needs a backend package (for Chronos-2,
    `chronos-forecasting`) that skforecast-ai does not install by default,
    and, with several series, `XGBRegressor`, whose package no extra of
    skforecast-ai installs. When that package is missing, the candidate is
    dropped instead of failing on every call, and this warning says which
    package to install. The comparison explanation records it as well.
    `plan()` still makes a plan whose estimator is not installed (XGBoost,
    CatBoost), since its script may run on another machine, and warns that
    running it here fails.
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

    It is warned too when the refined plan leaves out decisions of the plan
    that its forecaster or its estimator cannot take: the `estimator_kwargs`
    written for another estimator, or the differentiation, the calendar
    features, the target transformer, the lags refined by the LLM and the
    `transformer_exog` and `categorical_features` of an autoregressive plan
    switched to `ForecasterStats`, `ForecasterFoundation` or the baseline.
    The warning names each value and whether the user, the LLM or the rules
    chose it. Edits by hand and decisions left out are named in a single
    warning.

    `compare()` without `candidates` warns it too when the plan of its
    `CVResult` runs as the row `'Strategy plan'`, which `plan()` rebuilds
    in the same way: the edits it would not build do not run.
    """


class UnrecommendedForecasterWarning(UserWarning):
    """
    Warned by `plan()` when the requested forecaster is not recommended.

    The forecaster is supported and is used as requested, but it was left
    out of `ForecastingProfile.forecaster_candidates` for this dataset,
    typically because it is expected to be very slow or to perform poorly
    (for example, Auto-ARIMA on high-frequency data).
    """
