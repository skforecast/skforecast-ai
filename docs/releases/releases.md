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

+ <span class="badge text-bg-feature">Feature</span> [<code>ForecastingAssistant.ask()</code>][assistant] accepts a `CodeGenerationResult` (the output of `forecast_code()` and `backtest_code()`) and a `CVResult` as `result`, so a generated script or a cross-validation strategy can be explained before anything is executed.
+ <span class="badge text-bg-feature">Feature</span> Every result (`ForecastResult`, `BacktestResult`, `ComparisonResult`, `CodeGenerationResult`, `CVResult`) now serializes to JSON with `model_dump(mode="json")` and `model_dump_json()`: DataFrame fields become lists of row records with the index as a leading column, and the `TimeSeriesFold` of a `CVResult` becomes its constructor parameters. `model_dump()` in Python mode is unchanged and keeps the live DataFrames. `ComparisonResult.best_name` is a computed field, so it is part of the dump. The JSON output of the `forecast`, `backtest`, `compare` and `ask` CLI commands is now exactly this dump: same keys as before, in model field order, with `null` for absent values (`ask` also reports `skills`).
+ <span class="badge text-bg-feature">Feature</span> New public helpers `skforecast_ai.recommendation.resolve_cv_config()` (resolved `TimeSeriesFold` parameters plus fold count) and `DataProfile.n_observations_display`.


**Changed**

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.create_cv()</code>][assistant] returns a [`CVResult`][results] instead of a `(TimeSeriesFold, str)` tuple. The splitter is available as `result.cv` and the explanation as `result.explanation`; the result also carries `cv_config` (including `n_folds`), a `code` snippet that rebuilds the splitter, and the `profile` and `plan` it was derived from. Unpacking the result as before raises a `TypeError` that points to the new attributes. `backtest()`, `backtest_code()` and `compare()` accept a `CVResult` as `cv`, so `cv=result` works without unpacking.
+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.ask()</code>][assistant] takes the object to explain as a single `context` argument: a `ForecastingProfile` (optionally with `plan=`), a `CodeGenerationResult`, a `CVResult`, or a `ForecastResult`, `BacktestResult` or `ComparisonResult`. The former `data`, `target`, `date_column`, `series_id_column`, `profile` and `steps` arguments are removed: `ask()` no longer profiles or plans on its own, so call `profile()` (and `plan()` or `forecast_code()`) first and pass the object. `result=` keeps working as a deprecated alias of `context` and will be removed in 0.4.0. The `ask` CLI command gains `--from-profile` and `--from-plan`, and `--steps` becomes optional with `--data` (without it, the profile alone is explained).
+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.ask()</code>][assistant] raises the new `LLMCallError` when the call to the LLM fails (network, credentials, provider error, or a local Ollama model that is not reachable), with the provider exception chained and available as `original_error`. Previously it emitted a `UserWarning` and returned an `AskResult` whose explanation started with `[LLM unavailable]`, which a pipeline could mistake for an answer; the `ask` CLI command now exits with code 1 in that case. `refine_plan()` and `create_cv()` keep falling back to their deterministic output with a warning, since that output is valid on its own.
+ <span class="badge text-bg-api-change">API Change</span> When `profile` is provided, `target`, `date_column` and `series_id_column` are optional in `forecast()`, `forecast_code()`, `backtest()`, `backtest_code()` and `compare()`: they default to the values recorded in the profile. A value that differs from the profile, or a `data` that lacks the columns the profile was built from, raises `ValueError` (previously the argument was ignored or the failure surfaced inside the executed script).
+ <span class="badge text-bg-api-change">API Change</span> When `plan` is provided, `steps` is optional in [<code>ForecastingAssistant.forecast()</code>][assistant] and `forecast_code()`: it defaults to `plan.steps`, and a different value raises `ValueError`, mirroring the `cv.steps` check of `backtest()`. Previously a mismatching `steps` was silently ignored and the script predicted `plan.steps`.
+ <span class="badge text-bg-api-change">API Change</span> `BacktestResult.cv_config` and `ComparisonResult.cv_config` include `skip_folds` and `allow_incomplete_fold`, which affect the reported `n_folds`.
+ <span class="badge text-bg-api-change">API Change</span> `LLMContext` gains `sends_result_values` (default `True`). `DataSentToLLMWarning` is only emitted for results that ship values of their own; a `CodeGenerationResult` or a `CVResult` does not trigger it.
+ <span class="badge text-bg-enhancement">Enhancement</span> The overrides of [<code>ForecastingAssistant.refine_plan()</code>][assistant] and the candidate configurations of `compare()` are typed through the new `RefinePlanOverrides` and `CandidateConfig` dictionaries (`skforecast_ai.schemas`), so editors autocomplete the accepted keys and type checkers reject unknown ones. Behaviour is unchanged: omitting a key keeps the plan's value, and passing a key as None asks for the deterministic default.
+ <span class="badge text-bg-enhancement">Enhancement</span> [<code>ForecastingAssistant.forecast()</code>][assistant] and `forecast_code()` emit `IgnoredArgumentWarning` also for `lags` and `window_features` when a pre-built `plan` is supplied.
+ <span class="badge text-bg-enhancement">Enhancement</span> [<code>ForecastingAssistant.refine_plan()</code>][assistant] keeps the `llm_refined_fields` marks of the fields whose value is carried over unchanged, so LLM-suggested lags stay flagged as such after a deterministic refinement of another field.
+ <span class="badge text-bg-enhancement">Enhancement</span> The generated `ForecasterFoundation` script no longer uses an em dash in its fit comment (`# Fit (stores context only, no training)`).


**Fixed**

+ <span class="badge text-bg-danger">Fix</span> The script produced by [<code>ForecastingAssistant.backtest_code()</code>][assistant] loads the data from the CSV path it was given, as `forecast_code()` already did. Previously it always read `data.csv`, so the standalone script failed unless run next to a file of that name.


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
