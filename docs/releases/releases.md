# Changelog

All significant changes to this project are documented in this release file.

| Legend                                                     |                                       |
|:-----------------------------------------------------------|:--------------------------------------|
| <span class="badge text-bg-feature">Feature</span>         | New feature                           |
| <span class="badge text-bg-enhancement">Enhancement</span> | Improvement in existing functionality |
| <span class="badge text-bg-api-change">API Change</span>   | Changes in the API                    |
| <span class="badge text-bg-danger">Fix</span>              | Bug fix                               |


## 0.3.0 <small>Unreleased</small> { id="0.3.0" }


**Added**

+ <span class="badge text-bg-feature">Feature</span> [<code>ForecastingAssistant.ask()</code>][assistant] can explain a generated script (`CodeGenerationResult`, from `forecast_code()` and `backtest_code()`) and a cross-validation strategy (`CVResult`) before anything is executed. Neither carries data values, so they never trigger `DataSentToLLMWarning`.

+ <span class="badge text-bg-feature">Feature</span> Every result (`ForecastResult`, `BacktestResult`, `ComparisonResult`, `CodeGenerationResult`, `CVResult`) serializes to JSON with `model_dump(mode="json")` and `model_dump_json()`; DataFrames become lists of row records. The JSON output of the CLI commands is exactly this dump.

+ <span class="badge text-bg-enhancement">Enhancement</span> [<code>ForecastingAssistant.ask()</code>][assistant] sends a richer context to the LLM: date range and target statistics, missing values, significant lags, the suggested features, a summary of the generated script, and per-series statistics of the predictions for multi-series results. Answers are better grounded and questions about one series can be answered. Checked against a real model with `tools/ask_context_check.py`.


**Changed**

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.create_cv()</code>][assistant] returns a [`CVResult`][results] instead of a `(TimeSeriesFold, str)` tuple: the splitter is `result.cv`, the explanation `result.explanation`, and the result also carries `cv_config` (with `n_folds`), a `code` snippet and the `profile` and `plan` it came from. `backtest()`, `backtest_code()` and `compare()` accept it directly as `cv`. Unpacking it as before raises a `TypeError` that points to the new attributes.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.ask()</code>][assistant] takes the object to explain as a single `context` argument (a `ForecastingProfile`, optionally with `plan=`, or any result). It no longer profiles or plans on its own, so the `data`, `target`, `date_column`, `series_id_column`, `profile` and `steps` arguments are removed: call `profile()` or `plan()` first and pass the object. `result=` keeps working as a deprecated alias until 0.4.0. The `ask` CLI command gains `--from-profile`.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.ask()</code>][assistant] raises `LLMCallError` when the call to the LLM fails, with the provider exception available as `original_error`. Previously it returned an answer starting with `[LLM unavailable]`, which a pipeline could mistake for a real one. `refine_plan()` and `create_cv()` keep falling back to their deterministic output with a warning.

+ <span class="badge text-bg-api-change">API Change</span> Arguments already recorded in a `profile` or `plan` become optional: with `profile`, `target`, `date_column` and `series_id_column` default to the profile's values in `forecast()`, `forecast_code()`, `backtest()`, `backtest_code()` and `compare()`; with `plan`, `steps` defaults to `plan.steps` in `forecast()` and `forecast_code()`. A value that conflicts with the profile or plan raises `ValueError` instead of being silently ignored. The same rule applies to `forecaster`, `estimator`, `estimator_kwargs`, `lags` and `window_features` passed alongside a `plan`, which previously only emitted `IgnoredArgumentWarning`. `interval` is the exception: as a prediction-time option, it replaces the interval of a pre-built plan (`forecast(plan=best_plan, interval=[0.1, 0.9])` now produces the bounds), and None keeps the plan's intervals.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.compare()</code>][assistant] no longer ranks multi-series forecasters (scored on the average across all series) against multivariate forecasters (scored on the single series they predict): mixing them in `candidates` raises `ValueError`. For multi-series data the automatic candidates compare the estimators of `ForecasterRecursiveMultiSeries` instead (rows named `ForecasterRecursiveMultiSeries+<estimator>`).

+ <span class="badge text-bg-enhancement">Enhancement</span> The overrides of `refine_plan()` and the candidate configurations of `compare()` are typed (`RefinePlanOverrides` and `CandidateConfig` in `skforecast_ai.schemas`), so editors autocomplete the accepted keys. Behaviour is unchanged.


**Fixed**

+ <span class="badge text-bg-danger">Fix</span> The script produced by [<code>ForecastingAssistant.backtest_code()</code>][assistant] loads the data from the CSV path it was given, as `forecast_code()` already did. Previously it always read `data.csv`. `backtest_code()` also accepts `data=None` when `profile` and `plan` are given, so the CLI command `backtest-code --from-plan` renders the script without `DATA`, as `forecast-code` does.

+ <span class="badge text-bg-danger">Fix</span> CLI: `forecast-code` and `backtest-code` apply the modeling flags given alongside `--from-plan` (`--estimator`, `--interval`, `--lags`, ...) on top of the saved plan, as `forecast` and `backtest` already did, instead of ignoring them. The confirmation messages of `--output-code` and `--output-predictions` go to stderr, so `--format json` output stays parseable when both are combined.

+ <span class="badge text-bg-danger">Fix</span> `BacktestResult.explanation` for a multi-series backtest reported a value matching no row of the metrics table (a mean over the per-series and aggregate rows). It now reports the `average` row and says so.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.refine_plan()</code>][assistant] keeps the `llm_refined_fields` marks of the fields it does not override, so LLM-suggested lags stay flagged after refining another field.


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
