# Changelog

All significant changes to this project are documented in this release file.

| Legend                                                     |                                       |
|:-----------------------------------------------------------|:--------------------------------------|
| <span class="badge text-bg-feature">Feature</span>         | New feature                           |
| <span class="badge text-bg-enhancement">Enhancement</span> | Improvement in existing functionality |
| <span class="badge text-bg-api-change">API Change</span>   | Changes in the API                    |
| <span class="badge text-bg-danger">Fix</span>              | Bug fix                               |


## 0.2.0 <small>Aug 3, 2026</small> { id="0.2.0" }


**Added**

+ <span class="badge text-bg-feature">Feature</span> [<code>ForecastingAssistant.compare()</code>][assistant] backtests several forecaster/estimator configurations with the same cross-validation strategy and returns a metric-ranked `ComparisonResult` leaderboard. Each successful candidate is available in `candidates`, a name-keyed mapping of `BacktestResult` ordered best to worst, and the winning configuration is exposed as `best_name` / `best_candidate` for direct reuse. A matching `compare` CLI command reports the leaderboard and supports `--candidates`, `--metric`, `--from-profile`, and `--output-code`.


**Changed**

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.ask()</code>][assistant] now accepts a single `result` parameter in place of the previous `forecast_result` and `backtest_result` parameters. Update calls from `ask(forecast_result=...)` / `ask(backtest_result=...)` to `ask(result=...)`. Any `ExplainableResult` is accepted, including `ForecastResult`, `BacktestResult`, and `ComparisonResult`.


**Fixed**

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.ask()</code>][assistant] now treats a supplied `result` as the single source of truth. Previously an explicit `profile` or `plan` took precedence over the result's own while the context and code still came from the result, so the returned artifacts could describe different states. `data`, `target`, `date_column`, `series_id_column`, `profile`, `plan`, and `steps` are now ignored with an `IgnoredArgumentWarning` when `result` is provided.



## 0.1.0 <small>Jul 13, 2026</small> { id="0.1.0" }

First public release. `skforecast-ai` wraps the [`skforecast`](https://skforecast.org/) engine in a deterministic, rule-based assistant that profiles the data, selects a model, evaluates it, and returns the forecast together with the exact, runnable script that produced it. An optional LLM layer explains the decisions without ever changing them.

!!! note "Maturity"
    The underlying forecasting *engine* ([`skforecast`](https://github.com/skforecast/skforecast)) is mature and production-grade. The `skforecast-ai` assistant layer is at `0.1.0`, so its public API may still change.

**Added**

+ [`ForecastingAssistant`][assistant]: the main entry point, covering the full workflow: `profile()`, `plan()`, `refine_plan()`, `forecast()` / `forecast_code()`, `create_cv()`, `backtest()` / `backtest_code()`, and `ask()`.
+ [Typer-based CLI][cli] mirroring the programmatic API, with persistent [configuration][config].


<!-- Links to API Reference -->
[assistant]: ../api/assistant.md
[cli]: ../api/cli.md
[config]: ../user-guides/cli-usage.md#configuration

<!-- schemas -->
[results]: ../api/schemas/results.md
[plans]: ../api/schemas/plans.md
[profiles]: ../api/schemas/profiles.md
