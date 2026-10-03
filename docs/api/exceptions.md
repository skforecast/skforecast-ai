# Exceptions and warnings

Errors and warnings raised by `skforecast_ai`. All of them are importable from the package root, for example `from skforecast_ai import LLMCallError`.

Every error derives from `SkforecastAIError`, which carries a `code` from a closed set, the argument at fault in `field` (None when the error is not tied to one) and an optional remedy in `hint`, which is not part of `str(exc)`. A program can react to `code` and `field` without parsing the message. The errors for invalid inputs also derive from the built-in exception raised before 0.4.0 (`ValueError`, `TypeError` or `FileNotFoundError`), so existing `except` clauses keep catching them with the same message.

| Name | Raised or warned by | When |
|---|---|---|
| `SkforecastAIError` | every method | Base class of the errors below. Catch it to handle any error of skforecast-ai. |
| `InvalidInputError` | every method | An argument, or the plan, profile or CV passed in, is not valid. A `ValueError`. |
| `InvalidInputTypeError` | every method | An argument has a type that is not accepted, such as a bool `test_size` or a `compare()` candidate config that is not a dict, or a `CVResult` is unpacked as a tuple. A `TypeError`, and also an `InvalidInputError` and therefore a `ValueError`. |
| `DataNotFoundError` | every method that takes `data`, and the CLI | The CSV path does not exist or the URL cannot be read, or a JSON or CSV input of the CLI does not exist. A `FileNotFoundError`. |
| `LLMRequiredError` | `ask()`, `refine_plan()` and `create_cv()` with a prompt | The method needs an LLM and none was configured at init time. |
| `LLMCallError` | `ask()` | The call to the LLM fails. There is no deterministic answer to fall back on, so the provider error is raised (chained as `original_error`) instead of returned as text. |
| `ForecastExecutionError` | `forecast()`, `backtest()` | The generated script does not compile or fails while running. The script and the full traceback are available as `generated_code` and `execution_traceback`, and the line and the statement that failed as `failed_line` and `failed_statement`. |
| `AllCandidatesFailedError` | `compare()` | Every candidate configuration fails, so there is no leaderboard to return. The per-candidate reasons are in `failures`. |
| `CandidateFailedWarning` | `compare()` | One candidate fails; the comparison continues with the rest and the failure is recorded in `ComparisonResult.failures`. |
| `MissingBackendWarning` | `compare()` without `candidates` | The backend of the default foundation model (`chronos-forecasting` for Chronos-2) is not installed, so `ForecasterFoundation` is left out of the comparison instead of failing. Install it with `pip install skforecast-ai[foundation]`. |
| `DataSentToLLMWarning` | `ask()` | A result with values of its own (predictions, metrics) is sent to the LLM while `send_data_to_llm=False`. Pass `send_data_to_llm=True` to acknowledge it. |
| `UnrecommendedForecasterWarning` | `plan()` | The requested forecaster is supported but was not among the profile's candidates for this dataset (for example, Auto-ARIMA on high-frequency data). |

`refine_plan()` and `create_cv()` do not raise when the LLM fails: they emit a `UserWarning` and return their deterministic result, which is valid on its own.

The warnings that skforecast emits while `forecast()`, `backtest()` and `compare()` run the generated script (for example `MissingValuesWarning`) are shown when the script ends, after its printed output is discarded. Your warning filters apply as usual: `warnings.simplefilter('ignore', category=...)` hides them, and an `error` filter makes the script fail.

## Error codes

| `code` | Raised as | When |
|---|---|---|
| `invalid_argument` | `InvalidInputError`, `InvalidInputTypeError` | An argument or a received object is not valid. |
| `insufficient_data` | `InvalidInputError` | The data is too short for what was asked: fewer than two folds for the cross-validation, lags and window features longer than the data allows, or a target column without any value. |
| `data_not_found` | `DataNotFoundError` | A file to read (the CSV path or URL, or an input of the CLI) cannot be found. |
| `data_unreadable` | `DataNotFoundError`, `InvalidInputError` | An input exists but cannot be parsed: a CSV file that pandas cannot read (empty, binary, not UTF-8, or rows with more fields than the header), a URL whose content is not a CSV (`DataNotFoundError`, as before), or the JSON of `--from-plan` or `--from-profile` in the CLI. |
| `missing_dependency` | `InvalidInputError` | The package of the chosen estimator, or the backend package of the foundation model, is not installed. Checked before `forecast()` and `backtest()` run the script. |
| `execution_failed` | `ForecastExecutionError` | The generated script fails. |
| `all_candidates_failed` | `AllCandidatesFailedError` | Every candidate of `compare()` fails. |
| `llm_required` | `LLMRequiredError` | The method needs an LLM and none is configured. |
| `llm_call_failed` | `LLMCallError` | The call to the LLM fails. |
| `internal_error` | | Not raised by skforecast-ai: `ErrorInfo` uses it for any exception that skforecast-ai did not raise itself (it is also the default code of a bare `SkforecastAIError`). |

Some errors carry a remedy in `hint` that does not depend on Python, for a program or an agent that passes paths (the CLI prints it as a tip): for example how to write the dates, or what a CSV file that cannot be read must look like. Messages that suggest a pandas call keep it, and `hint` gives the remedy without it.

`ErrorInfo.from_exception()`, in `skforecast_ai.schemas`, turns an exception into plain data (`code`, `message`, `field`, `hint`) for a reader outside Python: it never holds a traceback or generated code, takes the field of a pydantic `ValidationError` from the location of its first error, and describes any other exception by its type and the first line of its message.

::: skforecast_ai.exceptions

::: skforecast_ai.schemas.errors.ErrorInfo
