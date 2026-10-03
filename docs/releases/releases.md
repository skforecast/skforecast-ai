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

+ <span class="badge text-bg-feature">Feature</span> New MCP server, so coding agents (Claude Code, Cursor and other MCP clients) can run the deterministic workflow as tools: profile a CSV file, plan, backtest, compare and forecast, each result with the script that produced it. In Claude Code, install it with its skill as a plugin (`/plugin marketplace add skforecast/skforecast-ai`, then `/plugin install skforecast-ai@skforecast-ai`); with other agents, start `skforecast-ai mcp --allow-dir DIR` from the new `mcp` extra (`pip install "skforecast-ai[mcp]"`, also in `all`) or run it with `uvx` without installing it. Responses never carry rows of your data or of the predictions, which go to CSV files. The server only reads CSV files inside `--allow-dir`, of at most `--max-file-mb` (256 MB by default), and only runs the foundation models whose license was reviewed for it (Chronos-2, TimesFM 2.5, TabICL, Nori); any other needs `--allow-model`. The package ships a skill (`SKILL.md`) that teaches the agent the workflow; see [MCP server for coding agents][mcp-guide] and the [reference][mcp] ([#35](https://github.com/skforecast/skforecast-ai/pull/35), [#36](https://github.com/skforecast/skforecast-ai/pull/36)).

+ <span class="badge text-bg-enhancement">Enhancement</span> The cross-validation explanation of [<code>ForecastingAssistant.create_cv()</code>][assistant], `backtest()` and `compare()` states how many times the forecaster is trained (`cv_config['n_fits']`, once per fold for `ForecasterStats`) and, for a direct forecaster, how many estimators that fits. `backtest()` and `compare()` warn with skforecast's `LongTrainingWarning` before running a backtest with more than 50 estimator fits, and `compare()` without `candidates` leaves out the alternatives above 500 fits (the recommended forecaster is always kept), saying so in the warning and the explanation. Pass them in `candidates` to run them anyway.

+ <span class="badge text-bg-feature">Feature</span> [<code>ForecastingAssistant.compare()</code>][assistant] adds a baseline to the leaderboard: a seasonal naive `ForecasterEquivalentDate` that repeats the value observed one seasonal period earlier, or the last observed value when the data has no usable seasonality. It is backtested and ranked like any other candidate, its row is identified by `ComparisonResult.baseline_name`, and the explanation says whether the best configuration beats it. Pass `baseline=False` (`--no-baseline` in the CLI) to leave it out. It is not added for multi-series data, when the target has missing values or missing timestamps, or with an asymmetric `interval`, which it cannot predict, and a `ForecasterEquivalentDate` passed in `candidates` is used as the baseline instead.

+ <span class="badge text-bg-feature">Feature</span> `'ForecasterEquivalentDate'` can be chosen as `forecaster` in [<code>ForecastingAssistant.plan()</code>][assistant], every method that builds a plan and the CLI `--forecaster`. Its plan has the task type `'baseline'`, an `offset` chosen as for the baseline of `compare()`, no estimator or features, and conformal prediction intervals. A target with missing values emits a `UserWarning` that advises imputing it; a datetime index without a regular frequency raises, and so does `forecast()` when the predictions would read an infinite value.

+ <span class="badge text-bg-feature">Feature</span> `ForecasterFoundation` forecasts several series, in wide and long format, and [<code>ForecastingAssistant.plan()</code>][assistant] no longer raises `ValueError` when it is chosen for more than one series. `backtest()` reports the metrics per series and aggregated, like `ForecasterRecursiveMultiSeries`, and [<code>ForecastingAssistant.compare()</code>][assistant] ranks the two together on the average across series. Chronos-2 can share information across series with `estimator_kwargs={'cross_learning': True}`.

+ <span class="badge text-bg-feature">Feature</span> New `foundation` extra (`pip install "skforecast-ai[foundation]"`) with the backend of Chronos-2, the default foundation model. When it is not installed, [<code>ForecastingAssistant.compare()</code>][assistant] without `candidates` leaves `ForecasterFoundation` out with the new `MissingBackendWarning` instead of running a candidate that fails.

+ <span class="badge text-bg-enhancement">Enhancement</span> `ForecasterFoundation` plans follow what skforecast declares for the chosen model instead of assuming Chronos-2. The generated script uses the default `context_length` of the model (8192 for Chronos-2, 2048 for TimesFM 3.0, ...), which `estimator_kwargs` still overrides. A model without covariate support (TimesFM 2.5, Moirai) gets a plan with `use_exog=False`, and a model that only accepts numeric covariates gets the categorical exogenous variables excluded.

+ <span class="badge text-bg-enhancement">Enhancement</span> An `interval` with quantiles that the foundation model does not predict (TimesFM and Moirai only predict 0.1, 0.2, ..., 0.9) raises `ValueError` when the plan is built, instead of failing inside the script. The plan explanation says when the weights have a license that restricts commercial use or are gated on the Hugging Face Hub.

+ <span class="badge text-bg-enhancement">Enhancement</span> `forecast()` with a `ForecasterFoundation` plan and an `interval` returns the `pred`, `lower_bound` and `upper_bound` columns of the other forecasters instead of one `q_*` column per quantile. `backtest()` keeps the quantile columns.

+ <span class="badge text-bg-enhancement">Enhancement</span> The explanations of `ForecasterFoundation` plans say how much history the model reads (the last `context_length` observations of each series). A plan with missing values gets a preprocessing step based on what the model accepts, instead of the advice for trained models.

+ <span class="badge text-bg-enhancement">Enhancement</span> Better answers from [<code>ForecastingAssistant.ask()</code>][assistant]. Skills and `llms-base.txt` are synced from skforecast 0.26.x, and the skills are chosen by the plan being asked about, so `ForecasterStats`, `ForecasterEquivalentDate` and a `compare()` baseline get `statistical-models` or `baseline-forecasting`, and questions about cold-start series or TabPFN-TS get `foundation-forecasting`. To measure accuracy or choose between models it points to `assistant.backtest()` and `assistant.compare()` instead of the lower-level skforecast functions, and it no longer suggests reasons why one `compare()` candidate beat another.

+ <span class="badge text-bg-feature">Feature</span> New `describe()` method on every result that `ask()` accepts, `ForecastingProfile` included: it returns, without an LLM, a plain-text description of the result (the context `ask()` sends, with the predictions summarized instead of listed and without the instructions addressed to the LLM), never row by row and with a length that does not grow with the number of series. A plan is described with `assistant.forecast_code(profile=profile, plan=plan).describe()` (see [Results][results]).

+ <span class="badge text-bg-feature">Feature</span> [<code>ForecastingAssistant.compare()</code>][assistant] accepts a `progress_callback`, called with a `CompareProgress` when each candidate starts and ends, to report progress outside a notebook. An exception it raises stops the comparison before the next candidate, so it can also cancel a long comparison.

+ <span class="badge text-bg-enhancement">Enhancement</span> `ForecastPlan.warnings`, empty until now, holds the text of the warnings that [<code>ForecastingAssistant.plan()</code>][assistant] emits, so they travel with the plan, its JSON and the results built from it. The warnings are still emitted, and the plan display shows them in a "Plan Warnings" panel.

+ <span class="badge text-bg-feature">Feature</span> Every error of skforecast-ai derives from the new `SkforecastAIError`, with a stable `code` and the argument at fault in `field`, so a program can react to it without parsing the message, some carry a remedy in `hint`, and `ErrorInfo.from_exception()` in `skforecast_ai.schemas` turns any error into plain data. Invalid inputs raise `InvalidInputError`, `InvalidInputTypeError` or `DataNotFoundError`, still a `ValueError`, a `TypeError` (now also a `ValueError`) and a `FileNotFoundError` with the same messages (see [Exceptions and warnings][exceptions]).

+ <span class="badge text-bg-enhancement">Enhancement</span> `python -m skforecast_ai` runs the CLI, like the `skforecast-ai` command (and `python -m skforecast_ai.cli` no longer exits without doing anything).

+ <span class="badge text-bg-docs">Docs</span> New documentation home page, and new animations in the [Agentic forecasting][agentic-guide] user guide: what reaches the LLM and how its suggestions are validated, how `create_cv()` and `backtest()` [validate the way you deploy][agentic-guide-backtesting], and how `compare()` [picks the model by measured performance][agentic-guide-compare].

**Changed**

+ <span class="badge text-bg-api-change">API Change</span> `lightgbm` is now a dependency of skforecast-ai. `LGBMRegressor` is the recommended estimator from 250 observations, so a clean install failed on the default plan with an `ImportError` inside the script.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.forecast()</code>][assistant] and `forecast_code()` in evaluation mode raise `ValueError` unless the test set holds exactly `steps` observations. A longer test set was scored on its first `steps` rows without saying so, and a shorter one failed inside the script. Use `backtest()` to evaluate over a longer period.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.plan()</code>][assistant] and every method that builds a plan raise `ValueError` before rendering the script, saying what to pass instead, for an unsupported estimator (or one other than `Arima` for `ForecasterStats`), an `estimator_kwargs` name the estimator does not accept (LightGBM and XGBoost, which take extra parameters, warn instead), an `interval` that is not `[lower, upper]` quantiles or is asymmetric where the method needs it, and a datetime index without an inferable frequency (for example day-first dates read month-first). A `date_column` that does not hold dates also raises, instead of being used as an exogenous variable.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.create_cv()</code>][assistant] trains the forecaster once by default (`refit=False`, the skforecast default) instead of refitting it in every fold, whose cost grows with the number of folds: on two years of hourly data a `ForecasterDirect` backtest took about an hour instead of seconds. The metrics of `backtest()` and `compare()` with the default strategy change; pass `refit=True` (or `--refit` in the CLI) to keep the previous behavior. `ForecasterStats`, which skforecast refits in every fold anyway, now trains on a window of fixed size by default instead of a growing one, so its metrics change too; `refit=True` keeps the growing window.

+ <span class="badge text-bg-api-change">API Change</span> skforecast-ai now requires `skforecast>=0.26.0`.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.compare()</code>][assistant] returns one more row by default (the baseline) and its explanation gains a sentence about it. Code that relies on the number of rows or on the exact explanation text passes `baseline=False` to keep the previous output.

+ <span class="badge text-bg-api-change">API Change</span> With several series, [<code>ForecastingAssistant.compare()</code>][assistant] without `candidates` compares `ForecasterRecursiveMultiSeries` against `ForecasterFoundation` (Chronos-2), as it does on a single series, instead of the estimators of `ForecasterRecursiveMultiSeries`. Pass `candidates` to compare the estimators as before.

+ <span class="badge text-bg-api-change">API Change</span> The `estimator` of a `ForecasterFoundation` plan is the Hugging Face model ID (default `'autogluon/chronos-2-small'`) instead of the `'Chronos-2'` label, e.g. `estimator='google/timesfm-3.0-pytorch'`. An ID that no skforecast adapter serves, `'Chronos-2'` included, raises `ValueError`, and so do an ID that is not of the form `'owner/name'` (letters, digits, `-`, `_` and `.`), such as a supported prefix followed by other text, and a `model_id` in `estimator_kwargs`.

+ <span class="badge text-bg-api-change">API Change</span> A `ForecastPlan` built by hand or loaded from JSON raises `ValidationError` when its `forecaster` is not supported or does not match `task_type`, when `forecaster_kwargs` holds an argument that [<code>ForecastingAssistant.plan()</code>][assistant] does not build for that forecaster (`differentiation` aside) or a value the generated scripts do not support (for example `categorical_features` other than `'auto'` or None, a `dropna_from_series` that is not a bool), when a blocking preprocessing step differs from the ones `plan()` generates (those of 0.3.1 load unchanged), or when it has an `interval` without an `interval_method`. `forecast()`, `backtest()`, `forecast_code()`, `backtest_code()` and `ask()` validate a received plan again before using it, so a plan edited with `model_copy(update=...)` or by assignment raises `ValidationError` before anything runs, and a `--from-plan` bundle edited by hand makes the CLI exit with code 1 and "Invalid input data".

+ <span class="badge text-bg-api-change">API Change</span> `steps` must be an integer of at least 1 in [<code>ForecastingAssistant.plan()</code>][assistant], every method that builds a plan and `ForecastPlan`. An integral float such as `12.0` is stored as `12`, while `True`, `'12'` and `12.5` raise `ValueError` before the plan is derived (`steps=True` gave a one-step plan).

+ <span class="badge text-bg-api-change">API Change</span> A `DataProfile` whose `frequency` contains anything other than letters, digits and hyphens (pandas aliases such as `'D'`, `'15min'` or `'W-SUN'` pass) raises `ValidationError`, for example a profile loaded from JSON with `--from-profile` or inside a `--from-plan` bundle in the CLI, which exits with code 1.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.plan()</code>][assistant], every method that builds a plan and the CLI raise `ValueError` when `lags` or `window_features` are passed for `ForecasterStats`, `ForecasterFoundation` or `ForecasterEquivalentDate`, which do not use them, and when `estimator` or `estimator_kwargs` are passed for `ForecasterEquivalentDate`. `ForecasterStats` and `ForecasterFoundation` ignored them silently, so the plan differed from what was asked.

+ <span class="badge text-bg-api-change">API Change</span> The CLI (`forecast`, `backtest`, the `*-code` commands and `ask`) exits with code 1 when `--steps` is passed with `--from-plan` and differs from the steps of the plan, which it ignored, as the Python API does (use `refine-plan --steps` to change the horizon), and `--format` only accepts the values of each command (`table`, `code` or `text`, and `json`), where any other value printed the default output; it now exits with code 2.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.create_cv()</code>][assistant] raises `ValueError` when `fixed_train_size` is passed for a forecaster that is trained once (`refit=False`, the default), where it had no effect (`ForecasterStats` still only warns), and when `skip_folds` names folds that do not exist, which were ignored. Pass `refit=True` (`--refit` in the CLI) with `fixed_train_size`.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.backtest()</code>][assistant] and `backtest_code()` given the `CVResult` of `create_cv()` without a `plan` or model arguments run the plan of that `CVResult` instead of a new default one. A `CVResult` created for data of another structure raises `ValueError` in them and in `compare()`.

+ <span class="badge text-bg-api-change">API Change</span> A `plan` passed to [<code>ForecastingAssistant.forecast()</code>][assistant], `forecast_code()`, `backtest()` or `backtest_code()` that was built for data of another frequency or shape, or that uses exogenous variables the data does not have, raises `ValueError` instead of running with lags and features that do not fit.

+ <span class="badge text-bg-api-change">API Change</span> A `profile` passed with `data` to [<code>ForecastingAssistant.forecast()</code>][assistant], `forecast_code()`, `backtest()`, `backtest_code()` or `compare()` is checked against those data, which are profiled again. Data of another structure (frequency, series, target or exogenous columns) raise `ValueError`, where daily data with a monthly profile were resampled to months without an error; data that only differ in their values (new rows, for example) run with the new profile, which says so in `DataProfile.warnings`, so the split dates, the folds and the explanation describe the data that ran.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.forecast()</code>][assistant] without `test_size`, given a plan that carries the `end_train` of an evaluation, raises `ValueError` instead of evaluating the same dates again: pass `test_size`, or `plan.model_copy(update={'end_train': None})` to forecast the future. `forecast_code()` still renders the split of the plan.

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.profile()</code>][assistant] raises `ValueError` when `series_id_column` is also the target or the date column.

+ <span class="badge text-bg-enhancement">Enhancement</span> The reason of the categorical preprocessing step of a plan names at most 15 columns, followed by "(first 15 of N)", instead of all of them, so `describe()` of a plan stays short with hundreds of categorical columns.

+ <span class="badge text-bg-docs">Docs</span> The Quick start section is reorganized into [Installation](../quick-start/how-to-install.md), [Your first forecast](../quick-start/first-forecast.ipynb), now a notebook with its outputs, and the new [Ask the assistant](../quick-start/ask-the-assistant.md), on what the LLM layer adds. The [API reference][assistant] opens with a table of the methods of `ForecastingAssistant`, what each one returns and whether it uses the LLM.

+ <span class="badge text-bg-docs">Docs</span> [Using the CLI][cli-guide] is rewritten as a shorter guide organized by task, with an example for every command. The options of each command are listed in the [CLI reference][cli], generated from the code.

+ <span class="badge text-bg-enhancement">Enhancement</span> Clearer `--help` texts in the CLI: `--interval` takes quantiles, what `--base-url` means for each provider, the fields a `--candidates` config accepts, and the data argument of `forecast`, `backtest` and `compare` accepts a URL. The help of `ask --send-data-to-llm` no longer describes it as permission to send raw data, which the CLI never sends.


**Fixed**

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.forecast()</code>][assistant], `backtest()` and `compare()` given a CSV path returned a script that loaded `'data.csv'` instead of that file. The script now loads the CSV path or URL passed, in these methods and in `forecast_code()` and `backtest_code()` (and in the CLI, also with `--from-plan`), also when the `profile` passed was built from another file; with a DataFrame and such a profile, the script loads `'data.csv'`, where data passed in memory is saved, instead of the file of the profile.

+ <span class="badge text-bg-danger">Fix</span> `estimator_kwargs` with numpy values (for example taken from `np.logspace`) made `forecast()`, `backtest()` and `compare()` fail with `NameError: name 'np' is not defined`, and the plan could not be saved as JSON. They are now stored as the Python values they hold.

+ <span class="badge text-bg-danger">Fix</span> The script generated for data without dates failed when run as a file: a CSV read by path had its first column turned into the index, and data passed in memory (and its `exog_future.csv`) was read with an integer index that skforecast rejects. It now reads them as `forecast()` does.

+ <span class="badge text-bg-danger">Fix</span> For long-format data with exogenous variables, the prediction script read the dates of `exog_future.csv` as text, so run as a file it predicted with missing exogenous values and gave other predictions than `forecast()`. It now parses them as it parses the data.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.profile()</code>][assistant] reads rows that are not in date order as the generated script does, sorted, and says so in `DataProfile.warnings`: descending dates gave a script that failed, and shuffled rows gave other lags and predictions without any warning. Repeated identical rows and rows without a date no longer count for the lags, which can change them.

+ <span class="badge text-bg-danger">Fix</span> Text dates, in a CSV or in a `date_column`, are read as the generated script reads them, so for day-first dates such as `13/01/2012` the profile, the lags and `forecast()` now match the script instead of reading `01/02/2012` as the second of January.

+ <span class="badge text-bg-danger">Fix</span> A CSV whose date column has empty cells or mixes UTC offsets raises `InvalidInputError` naming the column and the rows, where its dates silently became an exogenous variable; when a later column holds complete dates, it is used with a warning.

+ <span class="badge text-bg-danger">Fix</span> For long-format data, [<code>ForecastingAssistant.profile()</code>][assistant] reads the frequency and the missing timestamps of every series, not only of the first one: series of different frequencies or with timestamps off the grid of the others raise `InvalidInputError`, where the generated script resampled them or dropped those timestamps without an error. `DataProfile.warnings` notes the series that end before the last date, which `ForecasterRecursiveMultiSeries` does not predict, in long and wide format.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.forecast()</code>][assistant] checks the future `exog` against the data and the plan before running, where missing or misdated rows, new categories or missing values gave missing or wrong predictions without an error, or failed inside the script. What would make the forecast wrong raises `InvalidInputError`; missing values and new categories that LightGBM and the other tolerant estimators can read, and categories the estimator was never trained on, give a warning. The CLI reads the dates of `--exog` as it reads those of the data.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.forecast()</code>][assistant] checks the end of the target before running in prediction mode, where the forecast was moved or missing without an error. Final rows without a target value raise `InvalidInputError` (`ForecasterRecursiveMultiSeries`, which ignores them, warns instead), and a missing value that the predictions read raises with an estimator that cannot use it and warns with LightGBM and the others that can.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.plan()</code>][assistant] and every method that builds a plan raise `InvalidInputError` for plans whose generated script always failed: `ForecasterDirectMultiVariate` on long-format data with several series, long-format data with several series dated by its index, a multi-series forecaster on a single series, and an exogenous column named like a lag or a window feature (such as `lag_1`). `ForecastingProfile.forecaster_candidates` no longer lists `ForecasterDirectMultiVariate` for long-format data with several series, and `plan()` no longer warns that a forecaster is used as requested when it then rejects it, for the data or for an argument it cannot use.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.backtest()</code>][assistant] and `compare()` with an `interval` on several series computed conformal prediction intervals for `ForecasterRecursiveMultiSeries` and `ForecasterDirectMultiVariate`, while the plan and `forecast()` use bootstrapping. The generated backtesting script now passes `interval_method='bootstrapping'`, so the bounds of these backtests change; the point predictions and the metrics do not.

+ <span class="badge text-bg-danger">Fix</span> With `refit=False` or an integer `refit`, the backtesting script, `cv_config` and explanation of a `ForecasterStats` plan said that it was trained once (or every n folds) on a growing window, while skforecast refits ARIMA models in every fold, on a fixed window after `refit=False`. They now state what runs, also in what `ask()` and `describe()` say about a `compare()` that ran it, and [<code>ForecastingAssistant.create_cv()</code>][assistant] warns with skforecast's `IgnoredArgumentWarning` when a `refit` or `fixed_train_size` passed for it does not run; the metrics do not change.

+ <span class="badge text-bg-danger">Fix</span> `forecast()` in evaluation mode left out, without saying so, any metric other than MAE, MSE, MASE and MAPE. It now computes the same eight regression metrics as backtesting, and `compare(metric=...)` rejects any other name (such as classification scores, which it would have ranked in reverse) with `ValueError` instead of failing every candidate. An invalid `interval` in `compare()` also raises `ValueError` instead of `AllCandidatesFailedError`.

+ <span class="badge text-bg-danger">Fix</span> A crafted value could inject code into the generated script, which `forecast()` and `backtest()` execute and `forecast_code()` and `backtest_code()` return: a field of a plan loaded from JSON (the estimator, the keys of `estimator_kwargs`, the forecaster, a preprocessing snippet, a transformer or another forecaster argument), the frequency of a saved profile, a foundation model ID, or a column name read from a CSV (a quote in the series or date column of long-format data with repeated rows, a newline in a categorical exogenous variable). No value can run as code any longer: a name that must come from a fixed set (the forecaster, the estimator, a transformer, the interval method, a blocking preprocessing step other than the ones `plan()` generates, a key of `estimator_kwargs`) or a size that must be an integer raises `ValueError` when the script is rendered, and any other value is written as a quoted literal, or escaped inside the comments of the script. The estimator name and the keys of `estimator_kwargs` are also checked when a plan is built or loaded from JSON. As a result, a long-format CSV with a quote in a column name (`store's id`) no longer gives a script that fails with `SyntaxError`, and `backtest_code()` with a `TimeSeriesFold` whose `initial_train_size` is a `pd.Timestamp` writes it as `pd.Timestamp('...')` instead of a line that does not compile.

+ <span class="badge text-bg-danger">Fix</span> A generated script that does not compile raises `ForecastExecutionError` in `forecast()` and `backtest()`, like a script that fails while it runs, instead of a bare `SyntaxError`. `ForecastExecutionError` has two new attributes, `failed_line` and `failed_statement`: the line of `generated_code` where the error was raised and the statement that holds it (for an error inside skforecast, the statement of the script that called it; only the line when the script does not compile).

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.profile()</code>][assistant] raises `ValueError` when a timestamp has several rows with different values, instead of silently keeping the first one: long-format data profiled without `series_id_column` lost every series but one. The message suggests the column to pass as `series_id_column`. Identical repeated rows are still removed, now with a note in the profile warnings, and long-format data with a repeated date no longer produces a script that fails.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.plan()</code>][assistant] leaves out the calendar features whose columns already exist among the exogenous variables (for example `month` or `hour`), which made `forecast()` and `backtest()` fail with "Duplicated feature names detected". The data column is used instead, and the plan explanation names the skipped features.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.refine_plan()</code>][assistant] no longer carries over values that do not apply to the refined plan: switching forecaster family re-derives the estimator, lags and window features (an ML plan refined with `forecaster="ForecasterStats"` kept `Ridge`), and a new `estimator` drops the previous `estimator_kwargs` unless they are passed too. A `prompt` is ignored with a `UserWarning` when the new forecaster does not use the LLM.

+ <span class="badge text-bg-danger">Fix</span> In prediction mode [<code>ForecastingAssistant.forecast()</code>][assistant] required a future `exog` whenever the data had exogenous columns, even for a plan with `use_exog=False`. Such a plan now needs no future `exog`, and passing one raises `ValueError`.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.profile()</code>][assistant] left the frequency unknown when the series had missing timestamps, so every forecaster failed with "`y` has a pandas DatetimeIndex without a frequency". The frequency is now inferred despite the gaps, and the profile warns with the number of missing timestamps.

+ <span class="badge text-bg-danger">Fix</span> Plans with missing values drop rows only when the estimator cannot handle them. The missing timestamps restored by `asfreq()` now count as missing values, so a `Ridge` plan drops those rows instead of failing with "Input X contains NaN", and `RandomForestRegressor` is treated as NaN-tolerant, as it is since scikit-learn 1.4. Among the supported estimators, only `Ridge` now drops them.

+ <span class="badge text-bg-danger">Fix</span> For a single series, [<code>ForecastingAssistant.backtest()</code>][assistant], [<code>ForecastingAssistant.compare()</code>][assistant] and the evaluation mode of [<code>ForecastingAssistant.forecast()</code>][assistant] raise `ValueError` before running when a test fold has a missing target value, and name the dates. These runs failed anyway with "Input contains NaN".

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.ask()</code>][assistant] about the result of `backtest_code()` was told that the script trains on all the data and forecasts the future, without metrics. It now receives it as a backtest, with its cross-validation strategy, number of folds and trainings, like the result of `backtest()`. `describe()` gives the same text.

+ <span class="badge text-bg-danger">Fix</span> Two explanations were wrong, and `ask()` repeated them. The explanation of [<code>ForecastingAssistant.compare()</code>][assistant] said that multi-series candidates were ranked by the metric "pooled across series", but the ranking uses the `average` row; it now says "averaged across series". The plan explanation said "NaN rows kept (NaN-tolerant estimator)" even when no value was missing; it now appears only when the data has missing values.

+ <span class="badge text-bg-danger">Fix</span> The "How it works" diagram of the README and the [Agentic forecasting][agentic-guide] guides showed `create_cv()` in the fast path, where it needs a profile and a plan. It now shows a `TimeSeriesFold` passed to `backtest(data, cv)`.

+ <span class="badge text-bg-danger">Fix</span> Invalid inputs that raised an error of pandas, skforecast or Python (`KeyError`, `AttributeError`, "could not convert string to float", a `ParserError` of a CSV file) now raise `InvalidInputError`, still a `ValueError`, naming the argument at fault: for example a `series_id_column` that does not exist, a target with text values, a CSV file that cannot be read or a strategy that `TimeSeriesFold` rejects in `create_cv()` (see [Exceptions and warnings][exceptions]).

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.forecast()</code>][assistant] and `backtest()` raise `InvalidInputError` before running, instead of failing inside the generated script, when a series of `ForecasterRecursiveMultiSeries` has no values or fewer values than its lags and window features read, and when a direct forecaster is backtested with a `gap`, which it cannot predict.

+ <span class="badge text-bg-danger">Fix</span> In evaluation mode (`test_size`), [<code>ForecastingAssistant.forecast()</code>][assistant] checks the training partition before running, as in prediction mode: a missing value that the lags read raises with an estimator that cannot use it (it failed in the script) and warns with the estimators that tolerate missing values; with `ForecasterRecursiveMultiSeries`, a series without a value on the last training date or on a test date raises, where the predictions were shifted one date without an error or the metrics failed. A `test_size` on data with a time zone no longer raises a bare `TypeError`.

+ <span class="badge text-bg-danger">Fix</span> For data recorded within the day, an evaluation whose training set ended at midnight trained on that whole day and scored the predictions of the following hours against the test set, without an error: `plan.end_train` (and the script) now keep the time, such as `'2023-06-02 00:00:00'`.

+ <span class="badge text-bg-danger">Fix</span> Infinite values of the target, an `estimator_kwargs` name that the ARIMA model of `ForecasterStats` does not accept, and a foundation model whose backend package is not installed now raise before the generated script runs, where it failed inside it or, for `ForecasterStats` with infinite values, predicted missing values.

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.forecast()</code>][assistant], `backtest()` and `compare()` did not show the warnings that skforecast emits while the generated script runs (such as `MissingValuesWarning` when the estimator is trained with missing values): skforecast prints them on standard output, which is discarded while the script runs. They are now shown once it ends, and your warning filters still decide which ones.

+ <span class="badge text-bg-danger">Fix</span> CLI errors were printed on standard output, where a program reading the JSON of `--format json` got text instead, lost any text in brackets (such as the `[lower, upper]` of an `--interval` error), and a failed script pointed to `--output-code`, which is only written on success. Errors now go to standard error, as a JSON object `{"error": {"code", "message", "field", "hint"}}` with `--format json`, and a failed script points to `forecast-code` and `backtest-code` (see [Using the CLI][cli-guide]).

+ <span class="badge text-bg-danger">Fix</span> With `--format json`, the CLI printed skforecast's warnings (such as `LongTrainingWarning`) on standard output, before the JSON document, so it could not be parsed or piped. Every warning now goes to standard error, with the same format.

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
[exceptions]: ../api/exceptions.md
[mcp]: ../api/mcp.md
[mcp-guide]: ../user-guides/mcp-server.md
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
