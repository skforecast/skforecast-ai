# Results

What the methods that generate code, run it or call the LLM return:

| Returned by | Result |
|:--|:--|
| `forecast_code()`, `backtest_code()` | [`CodeGenerationResult`][skforecast_ai.schemas.results.CodeGenerationResult] |
| `forecast()` | [`ForecastResult`][skforecast_ai.schemas.results.ForecastResult] |
| `create_cv()` | [`CVResult`][skforecast_ai.schemas.results.CVResult] |
| `backtest()` | [`BacktestResult`][skforecast_ai.schemas.results.BacktestResult] |
| `compare()` | [`ComparisonResult`][skforecast_ai.schemas.results.ComparisonResult] |
| `ask()` | [`AskResult`][skforecast_ai.schemas.results.AskResult] |
| `check_llm()` | [`LLMCheckResult`][skforecast_ai.schemas.results.LLMCheckResult] |

Every result renders itself in a notebook and serializes to JSON, and all of them except `AskResult` and `LLMCheckResult` can be the `context` of `ask()`. Every result that `ask()` accepts, plus `ForecastingProfile`, also describes itself in plain text with [`describe()`][skforecast_ai.schemas.explainable.ExplainableResult.describe], without an LLM: the text is the context `ask()` sends about it, with the predictions summarized instead of listed row by row, without the instructions addressed to the LLM and with its lists cut when there are many series.

`compare()` also sends a [`CompareProgress`][skforecast_ai.schemas.results.CompareProgress] to its `progress_callback` when each candidate starts and ends.

::: skforecast_ai.schemas.results

::: skforecast_ai.schemas.explainable.ExplainableResult.describe
