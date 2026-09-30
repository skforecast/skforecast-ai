# Changelog

All significant changes to this project are documented in this release file.

| Legend                                                     |                                       |
|:-----------------------------------------------------------|:--------------------------------------|
| <span class="badge text-bg-feature">Feature</span>         | New feature                           |
| <span class="badge text-bg-enhancement">Enhancement</span> | Improvement in existing functionality |
| <span class="badge text-bg-api-change">API Change</span>   | Changes in the API                    |
| <span class="badge text-bg-danger">Fix</span>              | Bug fix                               |
| <span class="badge text-bg-docs">Docs</span>               | Documentation improvement             |


## 0.4.0 <small>In development</small> { id="0.4.0" }


**Added**

+ <span class="badge text-bg-feature">Feature</span> [<code>ForecastingAssistant.compare()</code>][assistant] adds a baseline to the leaderboard: a seasonal naive `ForecasterEquivalentDate` that repeats the value observed one seasonal period earlier (the period `ForecasterStats` also uses: 7 steps for daily data, 24 for hourly, 96 for 15-minute data, 12 for monthly), or the last observed value (`offset=1`) when the frequency has no seasonal period or one period spans more than a third of the series. It is backtested with the same cross-validation and metrics as the other candidates and ranked like any other row, and the explanation says whether the best configuration beats it and by how much, how many configurations do not, or that none does. A configuration beats the baseline only when its ranking metric is strictly lower: on a tie the baseline ranks first, so a configuration ranked above it always beats it, and a baseline with a NaN or infinite metric is reported as not comparable. The row is named `'Baseline (seasonal naive)'` or `'Baseline (naive)'`, and `ComparisonResult.baseline_name` identifies it. The configuration is fixed rather than searched: a tuned baseline selected on the same folds would stop being a neutral reference. Pass `baseline=False` (`--no-baseline` in the CLI) to leave it out. No baseline is added for multi-series data, which `ForecasterEquivalentDate` cannot forecast, nor when the target has missing values or missing timestamps, which it would repeat as missing predictions; the explanation says why. A `ForecasterEquivalentDate` passed in `candidates` is used as the baseline instead of adding a second one.

+ <span class="badge text-bg-feature">Feature</span> `'ForecasterEquivalentDate'` is accepted as `forecaster` in [<code>ForecastingAssistant.plan()</code>][assistant] and everywhere a forecaster can be chosen (`refine_plan()`, `forecast()`, `forecast_code()`, `backtest()`, `backtest_code()`, `compare()` candidates and the CLI `--forecaster`), without an `UnrecommendedForecasterWarning`. The plan has the new task type `'baseline'`, an integer `offset` chosen as above, no estimator and no lag, window or exogenous features, and conformal prediction intervals when an interval is requested. Passing `estimator`, `estimator_kwargs`, `lags` or `window_features` for it raises `ValueError`, and a target with missing values or missing timestamps emits a `UserWarning` and a preprocessing step that advises imputing it. In prediction mode `forecast()` needs no future `exog` for it even when the data has exogenous columns, and passing one raises `ValueError`. The generated scripts use `ForecasterEquivalentDate` and `backtesting_forecaster(..., interval_method='conformal')`.

+ <span class="badge text-bg-feature">Feature</span> `ForecasterFoundation` forecasts several series. It is a forecaster candidate for multi-series data, in wide and long format, and [<code>ForecastingAssistant.plan()</code>][assistant] no longer raises `ValueError` when it is chosen for more than one series. The generated scripts pass the series as a dict with one entry per series (`reshape_series_long_to_dict` for long data) and, in long format, one exogenous frame per series (`reshape_exog_long_to_dict`, also for the future values in prediction mode); every series is forecast and scored. `backtest()` reports the metrics per series plus the `average`, `weighted_average` and `pooling` rows, like `ForecasterRecursiveMultiSeries`, so [<code>ForecastingAssistant.compare()</code>][assistant] ranks the two together on the average across series. `ForecasterFoundation` is ranked with the single-series forecasters on one series and with `ForecasterRecursiveMultiSeries` on several; it is never mixed with `ForecasterDirectMultiVariate`. Chronos-2 can share information across series with `estimator_kwargs={'cross_learning': True}`.

+ <span class="badge text-bg-feature">Feature</span> New `foundation` extra (`pip install "skforecast-ai[foundation]"`) with the backend of Chronos-2, the default foundation model. [<code>ForecastingAssistant.compare()</code>][assistant] without `candidates` leaves `ForecasterFoundation` out when that backend is not installed, instead of running a candidate that fails on every call: it emits the new `MissingBackendWarning` and the explanation names the package to install. When that leaves a single forecaster (multi-series data), its estimators are compared instead.

+ <span class="badge text-bg-enhancement">Enhancement</span> `forecast()` with a `ForecasterFoundation` plan and an `interval` returns the `pred`, `lower_bound` and `upper_bound` columns of every other forecaster (the generated script calls `predict_interval`, with the median as `pred`) instead of one `q_*` column per quantile. `backtest()` keeps the quantile columns, the only output of `backtesting_foundation`.

+ <span class="badge text-bg-enhancement">Enhancement</span> The explanations of foundation plans say how much history the model reads: the last `context_length` observations of each series, or the whole history when it is shorter. The cross-validation explanation of `create_cv()` and `backtest()` for a foundation plan describes where the first fold forecasts from, not a training window and refits that do not apply to a model that is not trained, and the explanation of `compare()` says so when a foundation candidate shares the strategy of trained ones. For the same reason, the context that `ask()` receives for a foundation result leaves `refit` and `fixed_train_size` out of the cross-validation parameters.

+ <span class="badge text-bg-enhancement">Enhancement</span> The section of the [<code>ForecastingAssistant.ask()</code>][assistant] context that holds the cross-validation parameters is named `<backtesting_strategy>` instead of `<cross_validation>`, the term skforecast uses (`backtesting_forecaster`, `backtesting_foundation`). Plain "cross-validation" suggests shuffled k-fold splits, which time series validation does not use.

+ <span class="badge text-bg-enhancement">Enhancement</span> A `ForecasterFoundation` plan with missing values gets a preprocessing step based on what the model accepts (all the current skforecast adapters take missing values in the series used as context), instead of the advice for trained models about `dropna_from_series` or a NaN-tolerant estimator. The context sent by [<code>ForecastingAssistant.ask()</code>][assistant] breaks the median `q_0.5` down by series when the predictions are quantiles without a `pred` column, as `backtest()` returns them for a foundation model with an interval.

+ <span class="badge text-bg-enhancement">Enhancement</span> `ForecasterFoundation` plans follow the capabilities that skforecast declares for the chosen model, read with `skforecast.foundation.get_model_info()` instead of assuming Chronos-2. The generated script writes the default `context_length` of the model's adapter (8192 for Chronos-2, 2048 for TimesFM 3.0, ...) instead of 8192 for every model, and `estimator_kwargs` still overrides it. A model without covariate support (TimesFM 2.5, Moirai) gets a plan with `use_exog=False` whose explanation says the exogenous variables are not used, instead of a script that passes them and has skforecast ignore them with a warning. A model that only accepts numeric covariates gets the categorical exogenous variables excluded, with a preprocessing step and a comment in the script, as `ForecasterStats` does. An `interval` whose bounds are not quantile levels the model predicts (TimesFM and Moirai only predict 0.1, 0.2, ..., 0.9) raises `ValueError` when the plan is built, also through `forecast()` and `backtest()` with a pre-built plan, instead of failing inside the script. The plan explanation states when the weights are released under a license that restricts commercial use, which skforecast only reports when they are loaded, and when they are gated on the Hugging Face Hub.

+ <span class="badge text-bg-enhancement">Enhancement</span> Skills and `llms-base.txt` synced from skforecast 0.26.x. [<code>ForecastingAssistant.ask()</code>][assistant] also loads `foundation-forecasting` for questions about cold-start series or TabPFN-TS, in line with the updated description of the skill.

+ <span class="badge text-bg-enhancement">Enhancement</span> [<code>ForecastingAssistant.ask()</code>][assistant] also routes the skills by the task type of the plan in the context, not only by the profile's, so a plan built for `ForecasterStats` or `ForecasterEquivalentDate` loads `statistical-models` or `baseline-forecasting`. A `ComparisonResult` with a baseline row loads `baseline-forecasting` too.

+ <span class="badge text-bg-docs">Docs</span> New documentation home page: an animation of the four steps of the assistant (profile, plan, run, ask) and examples of what `ask()`, `refine_plan()` and `create_cv()` return.

+ <span class="badge text-bg-docs">Docs</span> New animation "Deterministic first, LLM second" in the [Agentic forecasting][agentic-guide] user guide: what stays on your machine, what reaches the LLM, and how an invalid LLM suggestion is rejected before it enters the plan.

+ <span class="badge text-bg-docs">Docs</span> New animation "Validate the way you deploy" in the Backtesting section of the [Agentic forecasting][agentic-guide-backtesting] user guide: how `create_cv()` turns a deployment scenario in plain words into `TimeSeriesFold` parameters, and how `backtest()` evaluates the model fold by fold.

+ <span class="badge text-bg-docs">Docs</span> New animation "Let measured performance pick the model" in the comparison section of the [Agentic forecasting][agentic-guide-compare] user guide: `compare()` backtests the candidates on the same folds and ranks them by the metric, with no LLM involved.


**Changed**

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.compare()</code>][assistant] returns one more row by default (the baseline) and its explanation gains a sentence about it. Code that relies on the number of rows or on the exact explanation text passes `baseline=False` to keep the previous output. A candidate named like the baseline it would add raises `ValueError`.

+ <span class="badge text-bg-api-change">API Change</span> With several series, [<code>ForecastingAssistant.compare()</code>][assistant] without `candidates` compares `ForecasterRecursiveMultiSeries` against `ForecasterFoundation` (Chronos-2), as it compares forecasters on a single series, instead of `ForecasterRecursiveMultiSeries` with each estimator candidate. The foundation candidate loads and runs Chronos-2, so its backend must be installed; pass `candidates` to compare the estimators as before. The profile of multi-series data lists `ForecasterFoundation` among the forecaster candidates.

+ <span class="badge text-bg-api-change">API Change</span> The `estimator` of a `ForecasterFoundation` plan is the Hugging Face model ID of the foundation model (default `'autogluon/chronos-2-small'`) instead of the `'Chronos-2'` label, which the generated code ignored. Pass the ID as `estimator` in [<code>ForecastingAssistant.plan()</code>][assistant] and everywhere an estimator can be chosen (`refine_plan()`, `forecast()`, `forecast_code()`, `backtest()`, `backtest_code()`, `compare()` candidates and the CLI `--estimator`), e.g. `estimator='google/timesfm-3.0-pytorch'`. An ID that no skforecast adapter serves, `'Chronos-2'` included, raises `ValueError` with the supported prefixes when the plan is built, and so does a `model_id` in `estimator_kwargs`, the former way to choose another model. A `ForecastPlan` built by hand or loaded from JSON is validated the same way. skforecast-ai now requires `skforecast>=0.26.0`.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.plan()</code>][assistant] raises `ValueError` when `lags` or `window_features` are passed for `ForecasterStats` or `ForecasterFoundation`, which model the past values themselves. They were silently ignored, so the plan differed from what was asked. The same applies to every method that forwards them to `plan()` (`refine_plan()`, `forecast()`, `forecast_code()`, `backtest()`, `backtest_code()`, `compare()` candidates and the CLI `--lags` and `--window-features`).

+ <span class="badge text-bg-docs">Docs</span> The Quick start section is reorganized into [Installation](../quick-start/how-to-install.md), [Your first forecast](../quick-start/first-forecast.ipynb), now a notebook with its outputs, and the new [Ask the assistant](../quick-start/ask-the-assistant.md), on what the LLM layer adds. Links to the old Quick start page redirect to Installation.

+ <span class="badge text-bg-docs">Docs</span> The [API reference][assistant] opens with a table of the methods of `ForecastingAssistant`, what each one returns and whether it uses the LLM.

+ <span class="badge text-bg-docs">Docs</span> To cite skforecast-ai, use the concept DOI in `CITATION.cff`, which always resolves to the latest release.

+ <span class="badge text-bg-docs">Docs</span> [Using the CLI][cli-guide] is rewritten as a shorter guide organized by task, with an example for every command. The options of each command are listed in the [CLI reference][cli], generated from the code, instead of tables maintained by hand.

+ <span class="badge text-bg-enhancement">Enhancement</span> Clearer `--help` texts in the CLI: `--interval` takes quantiles, what `--base-url` means for each provider, the fields a `--candidates` config accepts, and the data argument of `forecast`, `backtest` and `compare` accepts a URL.


**Fixed**

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.refine_plan()</code>][assistant] carried the estimator of the previous plan over when switching forecaster family, so an ML plan refined with `forecaster="ForecasterStats"` kept `Ridge` as its estimator. The estimator and its kwargs are now kept only within the ML forecasters or the same family, and the lags and window features only for the ML forecasters; any other value is re-derived. Whether the LLM is called with `prompt` is decided by the forecaster of the refined plan, so switching to `ForecasterStats`, `ForecasterFoundation` or `ForecasterEquivalentDate` ignores the prompt with a `UserWarning` instead of calling the LLM.

+ <span class="badge text-bg-danger">Fix</span> The explanation of [<code>ForecastingAssistant.compare()</code>][assistant] said that multi-series candidates were ranked by the metric "pooled across series", but the ranking uses the skforecast `average` row (the mean of the per-series values), not the `pooling` row. It now says "averaged across series", so `ask()` no longer repeats the wrong aggregation.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.refine_plan()</code>][assistant] kept the `estimator_kwargs` of the plan when a new `estimator` was passed, so the kwargs written for one estimator reached another: refining a Chronos-2 plan with `cross_learning=True` to `estimator='google/timesfm-3.0-pytorch'` produced a script that failed with `TypeError`, and a Ridge `alpha` was passed to `LGBMRegressor`. Changing the estimator now drops the previous kwargs unless `estimator_kwargs` is passed too; refining any other field keeps them.

+ <span class="badge text-bg-danger">Fix</span> In prediction mode [<code>ForecastingAssistant.forecast()</code>][assistant] required a future `exog` whenever the data had exogenous columns, even for a plan with `use_exog=False`. It is now validated against `plan.use_exog`: such a plan needs no future `exog`, and passing one raises `ValueError`.

+ <span class="badge text-bg-danger">Fix</span> The plan explanation said "NaN rows kept (NaN-tolerant estimator)" whenever `dropna_from_series` was False, which also happens when no value is missing, so a `Ridge` plan on complete data claimed a NaN-tolerant estimator and `ask()` repeated it. The sentence now appears only when the data has missing values.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.ask()</code>][assistant] could explain why one `compare()` candidate beat another by describing, with hedged wording, how their strategies differ. The prompt now forbids suggesting any reason for a ranking, hedged or not, and judging whether a margin is meaningful (the per-fold spread is not available), and the comparison context states that the MASE or RMSSE reference is a one-step naive forecast on the training data, not the baseline row, which can itself score below 1.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.profile()</code>][assistant] left the frequency unknown when the series had missing timestamps, because `pd.infer_freq` needs a gap-free index. Without a frequency the gaps went undetected, the scripts skipped `asfreq()` and every forecaster failed with "`y` has a pandas DatetimeIndex without a frequency". The frequency is now inferred on the stretches between gaps and accepted when every timestamp lies on its grid and at least half of the grid is observed; the profile warns with the number of missing timestamps. Truly irregular spacing still leaves the frequency unknown.

+ <span class="badge text-bg-danger">Fix</span> The missing timestamps that `asfreq()` restores as missing values now count as missing values when choosing `dropna_from_series`, so a plan with an estimator that does not tolerate NaN (such as `Ridge`) drops those rows instead of failing with "Input X contains NaN".

+ <span class="badge text-bg-danger">Fix</span> `RandomForestRegressor` is treated as NaN-tolerant, as it is since scikit-learn 1.4 (the minimum skforecast requires), so a plan with missing values keeps its rows instead of setting `dropna_from_series=True`. Among the supported estimators, only `Ridge` now drops them.

+ <span class="badge text-bg-enhancement">Enhancement</span> For a single series, [<code>ForecastingAssistant.backtest()</code>][assistant], [<code>ForecastingAssistant.compare()</code>][assistant] and the evaluation mode of [<code>ForecastingAssistant.forecast()</code>][assistant] raise `ValueError` before running when a test fold (or the test split) has a missing target value, including the missing timestamps that `asfreq()` restores, and name the dates. skforecast computes single-series metrics without dropping missing values, so these runs failed anyway with "Input contains NaN", in `compare()` once per candidate and whatever the estimator.

+ <span class="badge text-bg-danger">Fix</span> The "How it works" diagram of the README and the [Agentic forecasting][agentic-guide] guides showed `create_cv()` in the fast path, where it needs a profile and a plan. It now shows a `TimeSeriesFold` passed to `backtest(data, cv)`.

+ <span class="badge text-bg-danger">Fix</span> The `--help` of `ask --send-data-to-llm` described it as permission to send raw data. The CLI never sends observations to the LLM, whatever its value; the help now says so.

+ <span class="badge text-bg-danger">Fix</span> The quick start of the CLI guide forecast the future of a dataset with exogenous variables without their future values, which fails. It now evaluates on a held-out test set, and the guide explains when `--exog` is needed.

+ <span class="badge text-bg-danger">Fix</span> `skforecast-ai config set` no longer accepts `output.format`. No command read it, so the setting had no effect. `config show` lists it, and any other unknown key found in the file, as ignored.


## 0.3.1 <small>Sep 11, 2026</small> { id="0.3.1" }


**Added**

+ <span class="badge text-bg-feature">Feature</span> [<code>ForecastingAssistant.check_llm()</code>][assistant] and the `check-llm` CLI command report how the LLM configuration resolves before any workflow runs: provider and model, where the credentials come from and whether the environment variable is set, what `base_url` means for the provider, whether the extras are installed and, for Ollama, whether the server answers. With `test_call=True` (`--test-call`) a one-line prompt is sent to the model. The result is an [`LLMCheckResult`][results] with an `ok` field; the CLI exits with code 1 when a check fails. Credential values are never shown.

+ <span class="badge text-bg-enhancement">Enhancement</span> New user guide [Configuring the LLM][llm-config]: model strings, credentials per provider, the meaning of `base_url`, local models with Ollama, OpenAI-compatible endpoints, what is sent to the LLM, and troubleshooting. The quick start, the installation page, the CLI reference and the notebooks link to it, and the examples use the same set of model names throughout.

+ <span class="badge text-bg-docs">Docs</span> New API page for the exceptions and warnings the package exports, a user guide on the skills `ask()` sends to the LLM (which exist, how they are selected, how to pick them with `skills=` and `--skills`, and how they follow the Agent Skills standard), and an "Under the hood" section in the first forecast guide showing `profile()`, `plan()`, `forecast_code()` and `forecast()` chained step by step.


**Fixed**

+ <span class="badge text-bg-danger">Fix</span> `base_url` is honoured for `openai:` and for any prefix that is not built in when no `api_key` is given: the assistant builds an OpenAI-compatible client at that endpoint (local servers accept the placeholder key pydantic-ai sends when `OPENAI_API_KEY` is unset). Previously the endpoint was silently dropped and the bare provider string went to pydantic-ai.

+ <span class="badge text-bg-danger">Fix</span> The docstring of `send_data_to_llm` described the flag as permission to send raw input data. Input data is never sent; the flag acknowledges that the predictions and metrics of a result passed to `ask()` are sent, and silences `DataSentToLLMWarning`. The docstring now says so.


## 0.3.0 <small>Sep 11, 2026</small> { id="0.3.0" }


**Added**

+ <span class="badge text-bg-feature">Feature</span> [<code>ForecastingAssistant.ask()</code>][assistant] can explain a generated script (`CodeGenerationResult`, from `forecast_code()` and `backtest_code()`) and a cross-validation strategy (`CVResult`) before anything is executed. Neither carries data values, so they never trigger `DataSentToLLMWarning`.

+ <span class="badge text-bg-feature">Feature</span> Every result (`ForecastResult`, `BacktestResult`, `ComparisonResult`, `CodeGenerationResult`, `CVResult`) serializes to JSON with `model_dump(mode="json")` and `model_dump_json()`; DataFrames become lists of row records. The JSON output of the CLI commands is exactly this dump.

+ <span class="badge text-bg-enhancement">Enhancement</span> [<code>ForecastingAssistant.ask()</code>][assistant] sends a richer context to the LLM: date range and target statistics, missing values, significant lags, the suggested features, a summary of the generated script, and per-series statistics of the predictions for multi-series results. Answers are better grounded and questions about one series can be answered.


**Changed**

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.create_cv()</code>][assistant] returns a [`CVResult`][results] instead of a `(TimeSeriesFold, str)` tuple: the splitter is `result.cv`, the explanation `result.explanation`, and the result also carries `cv_config` (with `n_folds`), a `code` snippet and the `profile` and `plan` it came from. `backtest()`, `backtest_code()` and `compare()` accept it directly as `cv`. Unpacking it as before raises a `TypeError` that points to the new attributes.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.ask()</code>][assistant] takes the object to explain as a single `context` argument (a `ForecastingProfile`, optionally with `plan=`, or any result). It no longer profiles or plans on its own, so the `data`, `target`, `date_column`, `series_id_column`, `profile` and `steps` arguments are removed: call `profile()` or `plan()` first and pass the object. `result=` keeps working as a deprecated alias until 0.4.0. The `ask` CLI command gains `--from-profile`.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.ask()</code>][assistant] raises `LLMCallError` when the call to the LLM fails, with the provider exception available as `original_error`. Previously it returned an answer starting with `[LLM unavailable]`, which a pipeline could mistake for a real one. `refine_plan()` and `create_cv()` keep falling back to their deterministic output with a warning.

+ <span class="badge text-bg-api-change">API Change</span> Arguments already recorded in a `profile` or `plan` become optional: with `profile`, `target`, `date_column` and `series_id_column` default to the profile's values in `forecast()`, `forecast_code()`, `backtest()`, `backtest_code()` and `compare()`; with `plan`, `steps` defaults to `plan.steps` in `forecast()` and `forecast_code()`. A value that conflicts with the profile or plan raises `ValueError` instead of being silently ignored. The same rule applies to `forecaster`, `estimator`, `estimator_kwargs`, `lags` and `window_features` passed alongside a `plan`, which previously only emitted `IgnoredArgumentWarning`. `interval` is the exception: as a prediction-time option, it replaces the interval of a pre-built plan (`forecast(plan=best_plan, interval=[0.1, 0.9])` now produces the bounds), and None keeps the plan's intervals.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.compare()</code>][assistant] no longer ranks multi-series forecasters (scored on the average across all series) against multivariate forecasters (scored on the single series they predict): mixing them in `candidates` raises `ValueError`. For multi-series data the automatic candidates compare the estimators of `ForecasterRecursiveMultiSeries` instead (rows named `ForecasterRecursiveMultiSeries+<estimator>`).

+ <span class="badge text-bg-enhancement">Enhancement</span> The overrides of `refine_plan()` and the candidate configurations of `compare()` are typed (`RefinePlanOverrides` and `CandidateConfig` in `skforecast_ai.schemas`), so editors autocomplete the accepted keys. Behaviour is unchanged.

+ <span class="badge text-bg-enhancement">Enhancement</span> The LLM suggestions of [<code>ForecastingAssistant.refine_plan()</code>][assistant] (lags, window features) and [<code>ForecastingAssistant.create_cv()</code>][assistant] (fold parameters) are validated by the Pydantic output schema and by the same checks the explicit arguments go through. An invalid suggestion is sent back to the model with the concrete error and, if it persists, the deterministic result is used with a `UserWarning`; previously a malformed suggestion could crash `refine_plan()` or surface a pandas error from `create_cv()`. The agents' instructions state the constraints (positive unique lags, ISO dates within the dataset range) and the CV agent receives the first and last date of the series.

+ <span class="badge text-bg-enhancement">Enhancement</span> CLI: `--initial-train-size` accepts an ISO date marking the end of the initial training set, and `--lags auto` / `--window-features auto` re-run the deterministic selection when refining a saved plan (`refine-plan`, `backtest-code --from-plan`, `forecast-code --from-plan`).


**Fixed**

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.plan()</code>][assistant], `refine_plan()`, `compare()` and the CLI `--lags` option reject invalid lag specifications with a `ValueError` (`0`, an empty list, non-positive or non-integer values, booleans, duplicates) instead of passing them to skforecast, where an empty list silently trained without lag features and duplicates produced repeated features. `window_features` entries that repeat the same statistic with the same window size are rejected for the same reason.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.create_cv()</code>][assistant] accepts a `pandas Timestamp` as `initial_train_size` (documented but previously failing) and raises a clear `ValueError` naming `initial_train_size` when a date string cannot be parsed or when the dataset has no datetime index with a known frequency. Previously the date was located on a fabricated daily index or a raw pandas error surfaced. The same check protects `backtest()` and `compare()` when given a date-based `TimeSeriesFold`.

+ <span class="badge text-bg-danger">Fix</span> CLI: `--no-refit`, `--fixed-train-size` and `--gap 0` had no effect in `backtest`, `backtest-code` and `compare` because they matched the declared default and were dropped. The six cross-validation options are now forwarded to `create_cv()` only when passed, and the assistant decides the rest.

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
[cli-guide]: ../user-guides/cli-usage.md
[config]: ../user-guides/cli-usage.md#configuration
[llm-config]: ../user-guides/llm-configuration.md
[agentic-guide]: ../user-guides/agentic-forecasting.ipynb#what-is-skforecast-ai
[agentic-guide-backtesting]: ../user-guides/agentic-forecasting.ipynb#backtesting
[agentic-guide-compare]: ../user-guides/agentic-forecasting.ipynb#comparing-forecaster-configurations

<!-- schemas -->
[results]: ../api/schemas/results.md
[plans]: ../api/schemas/plans.md
[profiles]: ../api/schemas/profiles.md
