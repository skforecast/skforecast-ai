# `ForecastingAssistant`

`ForecastingAssistant` is the whole public API of skforecast-ai. Each step of the pipeline is one of its methods, and each method returns a Pydantic object that renders itself in a notebook, serializes to JSON and can be passed to the next step or to `ask()`.

All methods work without an LLM except `ask()`. `refine_plan()` and `create_cv()` use one only when you pass a `prompt`, so nothing is sent to an LLM unless you ask for it.

| Method | What it does | Returns | LLM |
|:--|:--|:--|:--:|
| [`profile()`][skforecast_ai.assistant.ForecastingAssistant.profile] | Inspects the data and recommends a forecaster and an estimator | [`ForecastingProfile`][skforecast_ai.schemas.profiles.ForecastingProfile] | no |
| [`plan()`][skforecast_ai.assistant.ForecastingAssistant.plan] | Builds the plan: lags, window and calendar features, interval, metric | [`ForecastPlan`][skforecast_ai.schemas.plans.ForecastPlan] | no |
| [`refine_plan()`][skforecast_ai.assistant.ForecastingAssistant.refine_plan] | Changes a plan with explicit overrides, or with a `prompt` | [`ForecastPlan`][skforecast_ai.schemas.plans.ForecastPlan] | optional |
| [`create_cv()`][skforecast_ai.assistant.ForecastingAssistant.create_cv] | Builds the cross-validation strategy, or translates a `prompt` into one | [`CVResult`][skforecast_ai.schemas.results.CVResult] | optional |
| [`forecast_code()`][skforecast_ai.assistant.ForecastingAssistant.forecast_code] | Returns the forecasting script without running it | [`CodeGenerationResult`][skforecast_ai.schemas.results.CodeGenerationResult] | no |
| [`forecast()`][skforecast_ai.assistant.ForecastingAssistant.forecast] | Runs that script: predictions, and metrics when evaluating | [`ForecastResult`][skforecast_ai.schemas.results.ForecastResult] | no |
| [`backtest_code()`][skforecast_ai.assistant.ForecastingAssistant.backtest_code] | Returns the backtesting script without running it | [`CodeGenerationResult`][skforecast_ai.schemas.results.CodeGenerationResult] | no |
| [`backtest()`][skforecast_ai.assistant.ForecastingAssistant.backtest] | Runs that script over the folds of a cross-validation | [`BacktestResult`][skforecast_ai.schemas.results.BacktestResult] | no |
| [`compare()`][skforecast_ai.assistant.ForecastingAssistant.compare] | Backtests several configurations and ranks them | [`ComparisonResult`][skforecast_ai.schemas.results.ComparisonResult] | no |
| [`ask()`][skforecast_ai.assistant.ForecastingAssistant.ask] | Explains a profile, plan, script or result, or answers a question | [`AskResult`][skforecast_ai.schemas.results.AskResult] | required |
| [`check_llm()`][skforecast_ai.assistant.ForecastingAssistant.check_llm] | Reports how the LLM configuration resolves; with `test_call=True`, also calls the model | [`LLMCheckResult`][skforecast_ai.schemas.results.LLMCheckResult] | optional |

The same pipeline runs from the terminal: see the [CLI reference](cli.md).

::: skforecast_ai.assistant.ForecastingAssistant
