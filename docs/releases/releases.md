# Changelog

All significant changes to this project are documented in this release file.

| Legend                                                     |                                       |
|:-----------------------------------------------------------|:--------------------------------------|
| <span class="badge text-bg-feature">Feature</span>         | New feature                           |
| <span class="badge text-bg-enhancement">Enhancement</span> | Improvement in existing functionality |
| <span class="badge text-bg-api-change">API Change</span>   | Changes in the API                    |
| <span class="badge text-bg-danger">Fix</span>              | Bug fix                               |


## 0.1.0 <small>In development</small> { id="0.1.0" }

First public release. `skforecast-ai` wraps the [`skforecast`][assistant] engine in a deterministic, rule-based assistant that profiles data, selects a model, evaluates it, and returns the forecast together with the exact, runnable script that produced it. An optional LLM layer explains the decisions without ever changing them.

**Added**

+ [`ForecastingAssistant`][assistant]: the main entry point, with the full workflow: `profile()`, `plan()`, `refine_plan()`, `forecast()` / `forecast_code()`, `create_cv()`, `backtest()` / `backtest_code()`, and `ask()`.
+ Deterministic recommendation engine ([forecaster selection][forecaster_selection], [estimator/metric selection][metric_selection], [autoregressive lag derivation][autoregressive], [preprocessing][preprocessing]) covering single-series, multi-series, multivariate, statistical, and foundation (zero-shot Chronos-2) tasks.
+ [Data profiling][data_profile]: frequency detection, gaps, missing values, duplicate timestamps, exogenous columns, and per-series metrics.
+ Code [rendering][single_series] for [single-series][single_series], [multi-series][multi_series], [statistical][statistical], and [foundation][foundation] pipelines, plus a [backtesting renderer][rendering_backtesting], with the `exec()` fidelity guarantee (the code shown is the code that ran).
+ Optional LLM layer: provider abstraction ([OpenAI, Google, Anthropic, Groq, Ollama, and OpenAI-compatible endpoints][provider]), a Q&A [agent][agent], rule-based [skill][skills] grounding ("Knowledge as Code"), and a [CV-configuration agent][recommendation_backtesting]. Enabled with `pip install "skforecast-ai[llm]"`.
+ [Typer-based CLI][cli] mirroring the programmatic API, with persistent [configuration][config].
+ [Exceptions][exceptions]: `ForecastExecutionError` (carries the generated code and traceback) and `LLMRequiredError`.

!!! note "Maturity"
    The forecasting *engine* underneath ([`skforecast`](https://github.com/JoaquinAmatRodrigo/skforecast)) is mature and production-grade. The `skforecast-ai` assistant layer is at `0.1.0`: the public API may still change before `1.0`.


<!-- Links to API Reference -->
[assistant]: ../api/assistant.md
[cli]: ../api/cli.md
[config]: ../api/config.md
[exceptions]: ../api/exceptions.md

<!-- execution -->
[backtesting_runner]: ../api/execution/backtesting_runner.md
[forecast_runner]: ../api/execution/forecast_runner.md

<!-- llm -->
[agent]: ../api/llm/agent.md
[context]: ../api/llm/context.md
[prompts]: ../api/llm/prompts.md
[provider]: ../api/llm/provider.md
[skills]: ../api/llm/skills.md

<!-- profiling -->
[data_profile]: ../api/profiling/data_profile.md

<!-- recommendation -->
[autoregressive]: ../api/recommendation/autoregressive.md
[recommendation_backtesting]: ../api/recommendation/backtesting.md
[explanation]: ../api/recommendation/explanation.md
[forecaster_selection]: ../api/recommendation/forecaster_selection.md
[metric_selection]: ../api/recommendation/metric_selection.md
[preprocessing]: ../api/recommendation/preprocessing.md

<!-- rendering -->
[rendering_backtesting]: ../api/rendering/backtesting.md
[foundation]: ../api/rendering/foundation.md
[multi_series]: ../api/rendering/multi_series.md
[single_series]: ../api/rendering/single_series.md
[statistical]: ../api/rendering/statistical.md

<!-- schemas -->
[plans]: ../api/schemas/plans.md
[profiles]: ../api/schemas/profiles.md
[results]: ../api/schemas/results.md
