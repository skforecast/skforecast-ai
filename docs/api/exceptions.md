# Exceptions and warnings

Errors and warnings raised by `skforecast_ai`. All of them are importable from the package root, for example `from skforecast_ai import LLMCallError`.

| Name | Raised or warned by | When |
|---|---|---|
| `LLMRequiredError` | `ask()`, `refine_plan()` and `create_cv()` with a prompt | The method needs an LLM and none was configured at init time. |
| `LLMCallError` | `ask()` | The call to the LLM fails. There is no deterministic answer to fall back on, so the provider error is raised (chained as `original_error`) instead of returned as text. |
| `ForecastExecutionError` | `forecast()`, `backtest()` | The generated script fails while running. The script and the full traceback are available as `generated_code` and `execution_traceback`. |
| `AllCandidatesFailedError` | `compare()` | Every candidate configuration fails, so there is no leaderboard to return. The per-candidate reasons are in `failures`. |
| `CandidateFailedWarning` | `compare()` | One candidate fails; the comparison continues with the rest and the failure is recorded in `ComparisonResult.failures`. |
| `DataSentToLLMWarning` | `ask()` | A result with values of its own (predictions, metrics) is sent to the LLM while `send_data_to_llm=False`. Pass `send_data_to_llm=True` to acknowledge it. |
| `UnrecommendedForecasterWarning` | `plan()` | The requested forecaster is supported but was not among the profile's candidates for this dataset (for example, Auto-ARIMA on high-frequency data). |

`refine_plan()` and `create_cv()` do not raise when the LLM fails: they emit a `UserWarning` and return their deterministic result, which is valid on its own.

::: skforecast_ai.exceptions
