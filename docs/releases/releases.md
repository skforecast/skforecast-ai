# Changelog

All significant changes to this project are documented in this release file.

| Legend                                                     |                                       |
|:-----------------------------------------------------------|:--------------------------------------|
| <span class="badge text-bg-feature">Feature</span>         | New feature                           |
| <span class="badge text-bg-enhancement">Enhancement</span> | Improvement in existing functionality |
| <span class="badge text-bg-api-change">API Change</span>   | Changes in the API                    |
| <span class="badge text-bg-danger">Fix</span>              | Bug fix                               |
| <span class="badge text-bg-docs">Docs</span>               | Documentation improvement             |


## 0.5.0 <small>In development</small> { id="0.5.0" }

The main changes in this release are:

!!! warning "Before upgrading"

    Some results change with this version, without any change in your code:

    + The scripts of long-format data read the series ids as text and turn them into text before the reshape: one more line (two with future exogenous variables), with the same predictions. See **Changed**.
    + The scripts of a forecast with future exogenous values read from a file (`exog_path` of the MCP server, `--exog` of the CLI) read that file by its path, with its own separator, decimal mark and encoding, instead of `exog_future.csv` in the working directory. See **Fixed**.
    + The scripts of dates that write the day and the month as numbers read them with their format (`format='%d/%m/%Y'`, or `'%m/%d/%Y'` month first), also when the first date already said so, and those of files with `.` between thousands read the date column as text: the same predictions. See **Changed**.
    + `plan()` and `refine_plan()` with `ForecasterDirectMultiVariate`: the estimator is chosen for the dates the series share, so it can be `Ridge` where it was `LGBMRegressor`. Pass `estimator="LGBMRegressor"` to keep the previous one. See **Fixed**.

    + `plan()` of wide-format data whose series start or end with missing values may choose another estimator: `DataProfile.n_total_observations` no longer counts those values. See **Changed**.
    + [<code>ForecastingAssistant.backtest()</code>][assistant] of ForecasterRecursiveMultiSeries raises `insufficient_data` for a series that no fold forecasts, which it left out before, and `invalid_argument` when its missing values are the cause. See **Fixed**.
    + `plan()` of a target that takes values at or around zero, also one that crosses it with negative values, leaves MAPE out of the default metrics and so of the generated script. Pass it in `metric` to compute it anyway. See **Fixed**.
    + The `compare` tool of the MCP server reports in `cost.n_fits` the trainings of all its candidates instead of those of the shared strategy, and its `cost` counts the candidates that fail too. See **Fixed**.

    And some code needs to be updated:

    + [<code>ForecastingAssistant.profile()</code>][assistant] of a file separated by `;` or tabulators raises `data_unreadable` instead of reading `.` as decimal mark when its only numbers with a `.` have three decimals (`1.870`), or when a column mixes them with whole numbers (`3`, `1.375`) next to other decimals (`0.75`). Pass `decimal='.'` to read them as before. See **Fixed**.
    + `profile()` of a DataFrame indexed by a MultiIndex with a level without a name raises `InvalidInputError` instead of naming it (`'datetime'`), a column the generated script did not have. Name the levels: `data.rename_axis(['series_id', 'date'])`. See **Fixed**.
    + `profile()` of dates that read both day first and month first and whose regularity does not tell the order either (a year or less of monthly data on the first of each month, or dates without a regular frequency) raises `data_unreadable` instead of reading them month first. Pass `dayfirst=False` to read them as before. See **Fixed**.


**Added**

+ New argument `thousands` of [<code>ForecastingAssistant.profile()</code>][assistant] (`--thousands` in the CLI, `thousands` in the `profile` tool of the MCP server), recorded as `DataProfile.csv_thousands` and passed to `pd.read_csv` by the generated script. See the [CLI guide][cli-guide] ([#86](https://github.com/skforecast/skforecast-ai/pull/86)).

+ New argument `dayfirst` of [<code>ForecastingAssistant.profile()</code>][assistant] (`--dayfirst` or `--monthfirst` in the CLI, `dayfirst` in the `profile` tool of the MCP server) for text dates that read both day first and month first, in a CSV file or the `date_column` of a DataFrame; with dates already parsed, an `IgnoredArgumentWarning` says it does not apply. The profile records the format of the dates as `DataProfile.date_format`. See the [CLI guide][cli-guide] ([#96](https://github.com/skforecast/skforecast-ai/pull/96)).

+ New attribute `cost` of the [<code>ComparisonResult</code>][results] of [<code>ForecastingAssistant.compare()</code>][assistant]: the trainings, estimator fits and inference windows of each candidate and of all of them together, the baseline included, counted before any candidate runs ([#108](https://github.com/skforecast/skforecast-ai/pull/108)).

+ The `backtest` and `forecast` tools of the MCP server carry an `EstimatorNotRecommendedNotice` when the estimator of the plan was chosen instead of the one the rules recommend for its forecaster (after a `MissingValuesNotice`, say). It names both and asks the agent to tell the user. See [MCP server][mcp] ([#110](https://github.com/skforecast/skforecast-ai/pull/110)).

+ New option `--exog` of the `forecast-code` command of the [CLI][cli], so the script reads the future exogenous values from that file, as `forecast --exog` does, instead of `exog_future.csv`. See the [CLI guide][cli-guide] ([#99](https://github.com/skforecast/skforecast-ai/pull/99)).


**Changed**

+ skforecast-ai now requires `skforecast>=0.27.0`, whose fixes it relies on instead of working around them ([#106](https://github.com/skforecast/skforecast-ai/pull/106)).

+ A target whose values are numbers written with a thousands separator or with `%` (`10,025.1`, `12.5%`) raises a `DataContentError` that names that format, as an error of the data and not of `target`, instead of the hint about missing value markers ([#86](https://github.com/skforecast/skforecast-ai/pull/86)).

+ The scripts of long-format data read the column of series ids as text (`dtype={'store': str}` in `pd.read_csv`) and turn the ids into text before the reshape, also those of the future exogenous variables. The predictions are the same; future exogenous variables with integer ids now match the same ids of the data written as text ([#90](https://github.com/skforecast/skforecast-ai/pull/90)).

+ The methods that take a saved profile read the file it was built from with its separator, decimal mark and thousands separator, so what was given to [<code>ForecastingAssistant.profile()</code>][assistant] holds for them; another file is still read as it is written ([#86](https://github.com/skforecast/skforecast-ai/pull/86)).

+ The generated scripts read the dates with their format when they write the day and the month as numbers or are whole numbers such as `20200131` (`format='%d/%m/%Y'`), and the future values with their own, none for ISO 8601 as `to_csv()` writes it; future values whose dates read both ways take the order of the data, or warn or raise as the data do. With `.` between thousands, the date column is read as text. The predictions are the same ([#96](https://github.com/skforecast/skforecast-ai/pull/96)).

+ The error of [<code>ForecastingAssistant.plan()</code>][assistant] for dates without a regular frequency describes their spacing instead of asking for ISO 8601 dates that may already be, and the description of the profile that the LLM and the MCP server read lists the irregular spacing instead of "none detected" ([#96](https://github.com/skforecast/skforecast-ai/pull/96)).

+ The errors and warnings about missing values name the estimator that the rules choose for the data (`RandomForestRegressor` below 250 observations, `LGBMRegressor` from 250) instead of always `LGBMRegressor`, put first the advice of a business closed on the missing weekdays, and, in [<code>ForecastingAssistant.backtest()</code>][assistant], name the test folds that hold a missing value ([#105](https://github.com/skforecast/skforecast-ai/pull/105)).

+ In wide-format data, each series of `DataProfile.series_lengths` spans the dates from its first to its last value, as in long format, instead of the whole frame, so its `start`, `end` and `length` say where it starts. `n_total_observations`, which sizes the estimator, follows them, and the note on short series names the series in wide and long data ([#103](https://github.com/skforecast/skforecast-ai/pull/103)).

+ The `MetricUnitNotice` of the MCP server gives the unit of sMAPE, already a percentage from 0 to 200, as it does for MAPE, a fraction, and [<code>ForecastingAssistant.ask()</code>][assistant] no longer describes MAPE as a percentage ([#104](https://github.com/skforecast/skforecast-ai/pull/104)).

+ The `forecast` tool of the MCP server adds an `UnmeasuredPlanNotice` to a forecast of the future when no `backtest`, `compare` or `forecast` with `test_size` of the server measured its plan (the same plan with another interval or metric counts as measured), so an agent does not present it as reliable or give it the accuracy of another plan ([#109](https://github.com/skforecast/skforecast-ai/pull/109)).

+ The description of a forecast run with `test_size`, in `describe()` and in the context of [<code>ForecastingAssistant.ask()</code>][assistant], says that its metrics come from a hold-out evaluation on dates already in the data, not from a forecast of the future ([#109](https://github.com/skforecast/skforecast-ai/pull/109)).


**Fixed**

+ Fixed an issue in [<code>ForecastingAssistant.profile()</code>][assistant] and the MCP server where a CSV file whose first row has more fields than its header (a separator at the end of every row, a field too many in the first row) gave a target without values or a profile with the dates as an exogenous variable. It now raises `data_unreadable`, as does a column without name and values, also in the file of future exogenous variables ([#85](https://github.com/skforecast/skforecast-ai/pull/85)).

+ In CSV files separated by `;` or tabulators, `.` between thousands was read as a decimal mark without a warning (`1.020` as 1.02), and `1.705,11` failed as a target that is not numeric. It is now read as thousands separator when the file says so; otherwise `profile()` raises `data_unreadable` and asks for `thousands` or `decimal`. A file whose other values also hold a `.` (`0.5`) raises `data_unreadable` too ([#86](https://github.com/skforecast/skforecast-ai/pull/86)).

+ Dates written day first (`31/01/2024`, the Excel of most of Europe) were read month first or rejected, so monthly data on the first of each month had no frequency. [<code>ForecastingAssistant.profile()</code>][assistant] now reads them day first when a day after the 12th says so (also `15.01.2020` and years of two digits) or, when no date tells, in the only order with a regular frequency, with a note in `DataProfile.warnings`; otherwise it asks for `dayfirst` ([#96](https://github.com/skforecast/skforecast-ai/pull/96)).

+ CSV files that are not UTF-8, as Excel saves them on Windows, raised `data_unreadable` when a header or a category held an `ñ` or an accent. [<code>ForecastingAssistant.profile()</code>][assistant] now reads them as cp1252, recorded as `DataProfile.csv_encoding` with a note in `DataProfile.warnings`, and the generated script passes `encoding='cp1252'`, also for the future exogenous values. UTF-16 files still raise `data_unreadable`, asking for UTF-8 ([#97](https://github.com/skforecast/skforecast-ai/pull/97)).

+ [<code>ForecastingAssistant.profile()</code>][assistant] found no frequency in daily data with regular or frequent gaps (a shop closed on Sundays, a day in four missing at random), so `plan()` rejected them. It now infers `'D'` (`'B'` for business days), also in long-format data, and warns about the missing dates. When they always fall on the same weekdays, the warning and the errors of `backtest()` and `forecast(test_size=...)` name them and suggest filling them with 0 if the business is closed ([#98](https://github.com/skforecast/skforecast-ai/pull/98)).

+ Fixed an issue in [<code>ForecastingAssistant.profile()</code>][assistant] where a CSV column of dates written as whole numbers (`20200131`) was taken for an exogenous variable, and rejected as `date_column`. It is now the date column, as is the `date_column` of a DataFrame with such numbers ([#96](https://github.com/skforecast/skforecast-ai/pull/96)).

+ Fixed an issue with long-format data whose series ids are numbers (`001`, `1`, `10`), where every backtest, forecast and comparison failed with `KeyError: 1` and [<code>ForecastingAssistant.profile()</code>][assistant] dropped the leading zeros. The ids are now kept as written; integer ids of a DataFrame become text, so its series are ordered as text (`1`, `10`, `2`). A DataFrame whose series columns are named with integers raises `InvalidInputError` with a hint instead of a validation error ([#90](https://github.com/skforecast/skforecast-ai/pull/90)).

+ Fixed an issue with long-format data indexed by a `(series_id, date)` MultiIndex, where [<code>ForecastingAssistant.forecast()</code>][assistant], `backtest()` and `compare()` raised `ForecastExecutionError` (`KeyError` on the date column), and `profile()` raised `KeyError` when the levels had no names. A MultiIndex that is not two levels named with text, also in the future `exog`, now raises `InvalidInputError` in every method, with a hint ([#91](https://github.com/skforecast/skforecast-ai/pull/91), [#94](https://github.com/skforecast/skforecast-ai/pull/94)).

+ [<code>ForecastingAssistant.profile()</code>][assistant] gave no warning for numbers written as text in an exogenous column (`12%`, `-` for a missing value), used then as a categorical variable, nor for its missing values below a rate of 20 %. Both now add a warning naming the column (a `DataProfileWarning` notice in the MCP server); the data are not changed ([#95](https://github.com/skforecast/skforecast-ai/pull/95)).

+ The script of a forecast with future exogenous values read from a file (`exog_path` of the MCP server, `--exog` of the CLI) read `exog_future.csv` from its working directory as `to_csv()` writes it, so it failed, also when copied there from a file of the Excel in Spanish (`;`, `,` as decimal mark). It now reads that file by its path with its separator, decimal mark, thousands separator, encoding and date format. See the [MCP server guide][mcp-guide] ([#99](https://github.com/skforecast/skforecast-ai/pull/99)).

+ Fixed an issue in [<code>ForecastingAssistant.profile()</code>][assistant] (and the `profile` command and MCP tool) where `target` as a list was accepted with `series_id_column`, which was ignored on wide data and gave a misleading error about repeated timestamps on long data (also with a `(series_id, date)` MultiIndex), or with a repeated column, profiled as two series. Both now raise `InvalidInputError` naming the argument ([#100](https://github.com/skforecast/skforecast-ai/pull/100)).

+ [<code>ForecastingAssistant.create_cv()</code>][assistant] gave no warning of prediction intervals estimated from too few residuals with ForecasterRecursiveMultiSeries or ForecasterDirectMultiVariate, as it does with a single series. It now counts the rows of each series in the first training window, also when a series starts later (in long or wide format), and names the series with fewer than 100 ([#101](https://github.com/skforecast/skforecast-ai/pull/101), [#103](https://github.com/skforecast/skforecast-ai/pull/103)).

+ Fixed an issue in [<code>ForecastingAssistant.backtest()</code>][assistant] with ForecasterRecursiveMultiSeries, where a series that no fold could forecast (too short for the lags and window features, starting after the training window without refit, ending before the folds, or with a missing value before every fold that its estimator or the differentiation cannot use) was left out of the predictions and of the average across series without a warning. It now raises `InvalidInputError` naming those series ([#103](https://github.com/skforecast/skforecast-ai/pull/103), [#105](https://github.com/skforecast/skforecast-ai/pull/105)).

+ The advice on missing values was wrong in places: [<code>ForecastingAssistant.create_cv()</code>][assistant] and the MCP server promised that an estimator that accepts them let every fold of `backtest()` run, though a missing value inside a test fold fails with any estimator, and `plan()` proposed `dropna_from_series` for missing exogenous values. They now say only what works, and `create_cv()` also warns with that estimator, with the differentiation and for exogenous values ([#105](https://github.com/skforecast/skforecast-ai/pull/105)).

+ [<code>ForecastingAssistant.backtest()</code>][assistant] of a single series failed inside the script with "All samples have been removed due to NaNs" when every training row of a fold read a missing value. It now raises `DataContentError` before running, with what avoids it ([#105](https://github.com/skforecast/skforecast-ai/pull/105)).

+ [<code>ForecastingAssistant.compare()</code>][assistant] applied the threshold of a long training (50 estimator fits) to each candidate, so candidates cheap one by one ran 78 fits without a warning. It now applies it to all the candidates together and warns once, before running, with the total and what each candidate adds ([#108](https://github.com/skforecast/skforecast-ai/pull/108)).

+ In the MCP server, `cost.n_fits` of `compare` was the trainings of the shared strategy, not of the comparison; it is now the total, like `estimator_fits`. The `CostNotice` of `create_cv` offered `refit` also where it lowers nothing (ForecasterStats, foundation models, a strategy that trains once); it now names only the changes that lower the cost. See the [MCP server reference][mcp] ([#108](https://github.com/skforecast/skforecast-ai/pull/108)).

+ Fixed an issue in [<code>ForecastingAssistant.plan()</code>][assistant] and `refine_plan()` where `ForecasterDirectMultiVariate` got the estimator chosen for the series pooled (`LGBMRegressor` from 250 observations), which on few dates per step predicted a constant. The rule now counts the dates the series share, and the explanation says so ([#102](https://github.com/skforecast/skforecast-ai/pull/102)).

+ Fixed an issue in [<code>ForecastingAssistant.plan()</code>][assistant] where the default metrics of a target that crosses zero with negative values (profits, temperatures) included MAPE, which reached values such as 3e13. MAPE is now left out when any series touches or crosses zero; asked for in `metric`, it comes with a warning, and the MCP server says it has no meaning instead of asking to multiply it by 100 ([#104](https://github.com/skforecast/skforecast-ai/pull/104)).

+ Fixed an issue in [<code>ForecastingAssistant.refine_plan()</code>][assistant] where switching to `ForecasterStats`, `ForecasterFoundation` or the baseline dropped the differentiation, calendar features and target transformer without a warning, as a new `estimator` did with the `estimator_kwargs` of the previous one. A `PlanEditsDiscardedWarning` (a notice in the MCP server) now names what is left out and whether you or the rules chose it ([#107](https://github.com/skforecast/skforecast-ai/pull/107)).


## 0.4.2 <small>Oct 12, 2026</small> { id="0.4.2" }

The main changes in this release are:

+ <span class="badge text-bg-danger">Fix</span> [<code>ForecastingAssistant.compare()</code>][assistant] without `candidates`, on the strategy of a refined plan, ranks that plan as the row `'Strategy plan'`, and its summary says how many configurations beat the baseline ([#71](https://github.com/skforecast/skforecast-ai/pull/71)).

!!! warning "Before upgrading"

    Some results change with this version, without any change in your code:

    + `compare()` without `candidates`, on a `CVResult` created for a plan that is none of the candidates of the profile, has one more row, `'Strategy plan'`, which runs that plan. Pass `candidates` to choose the rows.
    + `compare()`: the sentence of `explanation` about the baseline counts the configurations that beat it instead of those that do not, so code that parses that text must be updated.


**Added**

+ New field `strategy_plan_name` of [`ComparisonResult`][results]: the row of the comparison that runs the plan the strategy of `create_cv()` was created for, or None ([#71](https://github.com/skforecast/skforecast-ai/pull/71)).


**Changed**

+ The first start of the MCP server fits in the 30 seconds Claude Code waits: the server connects before loading pandas, scikit-learn and skforecast, which it loads in the background (7 seconds instead of 39 on macOS with an empty `uvx` cache; the first tool waits for that loading, about 30 seconds the first time). `import skforecast_ai` no longer loads them either. See [MCP server for coding agents][mcp-guide] ([#72](https://github.com/skforecast/skforecast-ai/pull/72)).

+ The MCP server is listed in the MCP gallery of VS Code, and its install button opens that entry, with logo and README, and installs the latest version pinned in `args`. Where the gallery is turned off, it installs the server as before. See [MCP server for coding agents][mcp-guide] ([#87](https://github.com/skforecast/skforecast-ai/pull/87), [#88](https://github.com/skforecast/skforecast-ai/pull/88)).

+ Dependencies: statsmodels 0.15 is allowed (`statsmodels>=0.13.2,<0.16`, as in skforecast), the minimum pandas is 2.2, the one skforecast 0.26 already required, and numpy, scikit-learn and scipy are declared as direct dependencies, with the minimum versions of skforecast.


**Fixed**

+ CSV files separated by `;` or tabulators, with `,` as decimal mark (what a spreadsheet exports in most of Europe), failed with a target column not found. The Python API, the CLI and the MCP server now detect the separator and the decimal mark (or take them as `sep` and `decimal` of [<code>ForecastingAssistant.profile()</code>][assistant]), the generated script reads the file with them, and the MCP server also accepts `.tsv` and `.csv.gz` files. See the [CLI guide][cli-guide] ([#74](https://github.com/skforecast/skforecast-ai/pull/74)).

+ [<code>ForecastingAssistant.compare()</code>][assistant] without `candidates`, on the strategy of a plan refined with another estimator, lags or window features, did not run that plan. It now runs as the row `'Strategy plan'`, and the summary names that row and counts the configurations that beat the baseline, not those that do not ([#71](https://github.com/skforecast/skforecast-ai/pull/71)).

+ [<code>ForecastingAssistant.compare()</code>][assistant]: when the two best configurations have the same value of the ranking metric, the summary says they are tied instead of "0.0% ahead" ([#71](https://github.com/skforecast/skforecast-ai/pull/71)).

+ The `cost` of `create_cv` in the MCP server, for a `compare` without `candidates`, counted forecasters that `compare` does not run (the multivariate one with several series) and only one of the estimators it compares when a single forecaster is left. It now counts the candidates that `compare` runs, the plan of the strategy included. See [MCP server for coding agents][mcp-guide] ([#71](https://github.com/skforecast/skforecast-ai/pull/71)).

+ `pip install "skforecast-ai[llm]"` did not install the Groq client, so a `groq:` model failed with an `ImportError` unless the `groq` extra was installed too. The `llm` extra now includes it, as the installation guide says.


## 0.4.1 <small>Oct 9, 2026</small> { id="0.4.1" }

The main changes in this release are:

+ <span class="badge text-bg-enhancement">Enhancement</span> New option `--allow-project-dir` of `skforecast-ai mcp`, which the plugin of Claude Code now uses: the server reads the project of the session from the environment and does not start in the home directory. See [MCP server for coding agents][mcp-guide].


**Added**

+ New option `--allow-project-dir` of `skforecast-ai mcp`, in place of `--allow-dir`: the allowed directory is the project of the session, read from the environment variable `CLAUDE_PROJECT_DIR` that Claude Code sets. The server stops if it is not set, or if it is the home directory or the root of a disk. See [MCP server for coding agents][mcp-guide] ([#61](https://github.com/skforecast/skforecast-ai/pull/61)).


**Changed**

+ The plugin of Claude Code starts the server with `uvx skforecast-ai-mcp==<version> --allow-project-dir`. It reads the same project as before, but no longer starts when Claude Code is opened in the home directory or in the root of a disk: open it in the folder of the project ([#61](https://github.com/skforecast/skforecast-ai/pull/61)).


**Fixed**


## 0.4.0 <small>Oct 9, 2026</small> { id="0.4.0" }

The main changes in this release are:

+ <span class="badge text-bg-feature">Feature</span> New MCP server, so coding agents (Claude Code, Cursor and other MCP clients) can run the deterministic workflow as tools: profile a CSV file, plan, backtest, compare and forecast, each result with the script that produced it. It installs as a Claude Code plugin or with the new `mcp` extra. See [MCP server for coding agents][mcp-guide] ([#35](https://github.com/skforecast/skforecast-ai/pull/35), [#36](https://github.com/skforecast/skforecast-ai/pull/36))

+ <span class="badge text-bg-feature">Feature</span> New keyword-only arguments in [<code>ForecastingAssistant.plan()</code>][assistant] and the methods that build a plan choose a decision instead of the rules (`metric`, `use_exog`, `differentiation`, `calendar_features`, `target_transformer`, `dropna_from_series`), and `exog_columns` in `profile()` chooses the exogenous columns. The CLI takes the same options. ([#41](https://github.com/skforecast/skforecast-ai/pull/41))

+ <span class="badge text-bg-feature">Feature</span> [<code>ForecastingAssistant.compare()</code>][assistant] adds a seasonal naive baseline (`ForecasterEquivalentDate`) to the leaderboard and says whether the best configuration beats it. `'ForecasterEquivalentDate'` can also be chosen as `forecaster`. ([#27](https://github.com/skforecast/skforecast-ai/pull/27))

+ <span class="badge text-bg-feature">Feature</span> `ForecasterFoundation` forecasts several series and follows what skforecast declares for the chosen model (context length, exogenous variables, quantiles) instead of assuming Chronos-2. The new `foundation` extra installs the backend of Chronos-2. ([#29](https://github.com/skforecast/skforecast-ai/pull/29))

+ <span class="badge text-bg-feature">Feature</span> Every error derives from the new `SkforecastAIError`, with a stable `code`, the argument at fault in `field` and, for some, a remedy in `hint`, so a program can react to it without parsing the message. See [Exceptions and warnings][exceptions] ([#32](https://github.com/skforecast/skforecast-ai/pull/32))

+ <span class="badge text-bg-api-change">API Change</span> [<code>ForecastingAssistant.create_cv()</code>][assistant] trains the forecaster once by default (`refit=False`) instead of refitting it in every fold, so the metrics of `backtest()` and `compare()` with the default strategy change. Pass `refit=True` to keep the previous behavior. ([#33](https://github.com/skforecast/skforecast-ai/pull/33))

+ <span class="badge text-bg-api-change">API Change</span> Arguments and plans that were ignored, or that failed inside the generated script, now raise before anything runs: invalid arguments of `plan()`, a `ForecastPlan` edited by hand or loaded from JSON that the scripts do not support, and a plan or a profile that does not match the data. ([#31](https://github.com/skforecast/skforecast-ai/pull/31), [#33](https://github.com/skforecast/skforecast-ai/pull/33), [#37](https://github.com/skforecast/skforecast-ai/pull/37))

+ <span class="badge text-bg-api-change">API Change</span> skforecast-ai now requires `skforecast>=0.26.0`, and `lightgbm` is a dependency.

+ <span class="badge text-bg-danger">Fix</span> `forecast()` and `backtest()` check the data before running (dates, missing values, future exogenous variables) and raise `InvalidInputError` naming the rows, where they failed inside the script or returned missing or shifted predictions without an error. ([#32](https://github.com/skforecast/skforecast-ai/pull/32), [#37](https://github.com/skforecast/skforecast-ai/pull/37), [#43](https://github.com/skforecast/skforecast-ai/pull/43), [#47](https://github.com/skforecast/skforecast-ai/pull/47))

+ <span class="badge text-bg-danger">Fix</span> A crafted value in a plan or a profile loaded from JSON, or in a column name of a CSV, could inject code into the generated script that `forecast()` and `backtest()` execute. No value can run as code any longer. ([#31](https://github.com/skforecast/skforecast-ai/pull/31))

!!! warning "Before upgrading"

    Some results change with this version, without any change in your code:

    + `create_cv()`, `backtest()` and `compare()`: the default strategy trains the forecaster once instead of refitting it in every fold, so the metrics change. Pass `refit=True` to keep the previous behavior.
    + `compare()`: the leaderboard has one more row, the baseline (`baseline=False` leaves it out), and with several series it compares `ForecasterRecursiveMultiSeries` against `ForecasterFoundation` by default (pass `candidates` to compare the estimators as before).
    + `ForecasterStats` (Auto-ARIMA): predictions and metrics change for quarterly data and for multiplied frequencies such as `'2MS'` or `'3h'`, which now get a seasonal period.
    + `backtest()` and `compare()` with an `interval` on several series: the bounds change, because they are now estimated by bootstrapping, as in `forecast()`.
    + `forecast()` with a `ForecasterFoundation` plan and an `interval` returns the `pred`, `lower_bound` and `upper_bound` columns instead of one `q_*` column per quantile.
    + `ForecasterDirectMultiVariate` plans that do not use the exogenous columns: predictions change, because those columns are no longer fitted as series.
    + `profile()`: rows that are not in date order and day-first text dates are read as the generated script reads them, which can change the lags and the predictions.

    And some code needs to be updated: arguments that were ignored now raise, the `estimator` of a `ForecasterFoundation` plan is the Hugging Face model ID, `forecast()` in evaluation mode needs a test set of exactly `steps` observations, the `result` keyword of `ask()` is removed and the minimum version of skforecast is 0.26.0. See **Changed**.


**Added**

*Plans and overrides*

+ New keyword-only arguments `metric`, `use_exog`, `differentiation`, `calendar_features`, `target_transformer` and `dropna_from_series` in [<code>ForecastingAssistant.plan()</code>][assistant], `refine_plan()`, `forecast()`, `backtest()` and their `*_code()` methods choose a decision instead of the rules; all but `metric` are also keys of the candidates of `compare()`. A value the data or the forecaster cannot apply raises `ValueError`. `backtest()` and `backtest_code()` also take `lags` and `window_features`. ([#41](https://github.com/skforecast/skforecast-ai/pull/41))

+ New keyword-only `exog_columns` argument in [<code>ForecastingAssistant.profile()</code>][assistant] chooses the exogenous columns (an empty list for none) instead of using every column that is not the target, the date or the series id. The others are listed in the new `DataProfile.unused_columns`, and neither the plan nor the script uses them. ([#41](https://github.com/skforecast/skforecast-ai/pull/41))

+ `ForecastPlan.overridden_fields` names the decisions you made instead of the rules, and `ForecastPlan.warnings` holds the text of the warnings that [<code>ForecastingAssistant.plan()</code>][assistant] emits, so both travel with the plan, its JSON and the results built from it. `refine_plan()` warns with the new `PlanEditsDiscardedWarning` when it does not keep values edited by hand in the plan. ([#34](https://github.com/skforecast/skforecast-ai/pull/34), [#41](https://github.com/skforecast/skforecast-ai/pull/41))

+ `'ForecasterEquivalentDate'` can be chosen as `forecaster` in [<code>ForecastingAssistant.plan()</code>][assistant], every method that builds a plan and the CLI `--forecaster`. Its plan has the task type `'baseline'`, an `offset` chosen as for the baseline of `compare()`, no estimator or features, and conformal prediction intervals. ([#27](https://github.com/skforecast/skforecast-ai/pull/27), [#37](https://github.com/skforecast/skforecast-ai/pull/37))

*Backtesting and comparison*

+ [<code>ForecastingAssistant.compare()</code>][assistant] adds a baseline to the leaderboard: a seasonal naive `ForecasterEquivalentDate` that repeats the value observed one seasonal period earlier, or the last observed value when the data has no usable seasonality. Its row is identified by `ComparisonResult.baseline_name`, and the explanation says whether the best configuration beats it. It is not added in some cases, such as multi-series data or a target with missing values. Pass `baseline=False` (`--no-baseline` in the CLI) to keep the previous output. ([#27](https://github.com/skforecast/skforecast-ai/pull/27))

+ The cross-validation explanation of [<code>ForecastingAssistant.create_cv()</code>][assistant], `backtest()` and `compare()` states the cost of the backtest: how many times the forecaster is trained (`cv_config['n_fits']`) or, for `ForecasterFoundation`, how many inference windows it runs (`cv_config['inference_windows']`). `backtest()` and `compare()` warn with skforecast's `LongTrainingWarning` above 50 estimator fits or 2000 windows, and `compare()` without `candidates` leaves out the alternatives above 500 fits; pass them in `candidates` to run them anyway. ([#33](https://github.com/skforecast/skforecast-ai/pull/33), [#43](https://github.com/skforecast/skforecast-ai/pull/43))

+ The result of [<code>ForecastingAssistant.create_cv()</code>][assistant] says where each value of the strategy comes from: `overridden_fields`, `fields_without_effect`, `llm_configured` and `defaults_explanation`. `backtest()` and `compare()` carry the same under `cv_` names when they receive that result. ([#45](https://github.com/skforecast/skforecast-ai/pull/45))

+ [<code>ForecastingAssistant.create_cv()</code>][assistant] warns when a plan with prediction intervals estimated from residuals gets a strategy whose first training window leaves fewer than 100 rows to train on, which makes the intervals too narrow. Its error for a strategy with fewer than 2 folds carries a `hint` with the ways out. ([#47](https://github.com/skforecast/skforecast-ai/pull/47))

+ [<code>ForecastingAssistant.compare()</code>][assistant] accepts a `progress_callback`, called with a `CompareProgress` when each candidate starts and ends, to report progress outside a notebook. An exception it raises stops the comparison before the next candidate, so it can also cancel a long comparison. ([#34](https://github.com/skforecast/skforecast-ai/pull/34))

*Foundation models*

+ `ForecasterFoundation` forecasts several series, in wide and long format. `backtest()` reports the metrics per series and aggregated, [<code>ForecastingAssistant.compare()</code>][assistant] ranks it together with `ForecasterRecursiveMultiSeries` on the average across series, and Chronos-2 can share information across series with `estimator_kwargs={'cross_learning': True}`. ([#29](https://github.com/skforecast/skforecast-ai/pull/29))

+ New `foundation` extra (`pip install "skforecast-ai[foundation]"`) with the backend of Chronos-2, the default foundation model. When it is not installed, [<code>ForecastingAssistant.compare()</code>][assistant] without `candidates` leaves `ForecasterFoundation` out with the new `MissingBackendWarning` instead of running a candidate that fails. ([#29](https://github.com/skforecast/skforecast-ai/pull/29))

+ `ForecasterFoundation` plans follow what skforecast declares for the chosen model instead of assuming Chronos-2: its default `context_length`, whether it accepts exogenous variables (and categorical ones) and the quantiles it predicts. An `interval` the model cannot predict raises `ValueError` when the plan is built, and the explanation says how much history the model reads and when its weights have a restrictive license, are gated or need an account with their provider. ([#29](https://github.com/skforecast/skforecast-ai/pull/29), [#41](https://github.com/skforecast/skforecast-ai/pull/41))

*Results and explanations*

+ New `describe()` method on every result that `ask()` accepts, `ForecastingProfile` included. It returns, without an LLM, a plain-text description of the result, with the predictions summarized instead of listed and a length that does not grow with the number of series. See [Results][results] ([#33](https://github.com/skforecast/skforecast-ai/pull/33), [#34](https://github.com/skforecast/skforecast-ai/pull/34))

+ The explanation of a `ForecasterDirectMultiVariate` plan names the series it predicts, the first one of `target`. ([#41](https://github.com/skforecast/skforecast-ai/pull/41))

*Errors and warnings*

+ Every error of skforecast-ai derives from the new `SkforecastAIError`, with a stable `code`, the argument at fault in `field` and, for some, a remedy in `hint`, so a program can react to it without parsing the message. Invalid inputs raise `InvalidInputError`, `InvalidInputTypeError`, `DataNotFoundError` or `DataContentError`, which are still a `ValueError`, a `TypeError` or a `FileNotFoundError` with the same messages. See [Exceptions and warnings][exceptions] ([#32](https://github.com/skforecast/skforecast-ai/pull/32), [#37](https://github.com/skforecast/skforecast-ai/pull/37), [#47](https://github.com/skforecast/skforecast-ai/pull/47))

*LLM layer*

+ Better answers from [<code>ForecastingAssistant.ask()</code>][assistant]. The skills and `llms-base.txt` are synced from skforecast 0.26.x, and the skills are chosen by the plan being asked about (statistical models, baselines, foundation models). What the LLM receives lists the decisions you made instead of the rules and the warnings of the plan, so the answers no longer present a chosen value as a recommendation, and it points to `backtest()` and `compare()` to measure accuracy or choose between models. ([#28](https://github.com/skforecast/skforecast-ai/pull/28), [#41](https://github.com/skforecast/skforecast-ai/pull/41), [#46](https://github.com/skforecast/skforecast-ai/pull/46))

*MCP server*

+ New MCP server (`skforecast-ai mcp`, extra `mcp`), so coding agents can profile a CSV file, plan, backtest, compare and forecast as tools, each result with the script that produced it. In Claude Code it installs as a plugin. It never returns rows of your data, only reads CSV files inside `--allow-dir` and, unless `--allow-model` names another, only runs the foundation models whose license does not restrict commercial use. See [MCP server for coding agents][mcp-guide] and the [reference][mcp] ([#35](https://github.com/skforecast/skforecast-ai/pull/35), [#36](https://github.com/skforecast/skforecast-ai/pull/36))

*CLI*

+ The commands `plan`, `refine-plan`, `forecast`, `backtest`, `forecast-code` and `backtest-code` take the new overrides (`--metric`, `--use-exog`, `--differentiation`, `--calendar-features`, `--target-transformer`, `--dropna-from-series`), with `auto` to go back to the rule when refining a saved plan, and `profile` and `plan` take `--exog-columns`. `forecast` and `backtest` also take `--lags` and `--window-features`. See the [CLI guide][cli-guide] ([#41](https://github.com/skforecast/skforecast-ai/pull/41))

+ `python -m skforecast_ai` runs the CLI, like the `skforecast-ai` command. ([#36](https://github.com/skforecast/skforecast-ai/pull/36))


**Changed**

*Plans and overrides*

+ [<code>ForecastingAssistant.plan()</code>][assistant] and every method that builds a plan raise `ValueError` before rendering the script: an unsupported estimator, an `estimator_kwargs` name the estimator does not accept, an `interval` that is not `[lower, upper]` quantiles, a `steps` that is not an integer of at least 1, and dates without an inferable frequency. So do `lags` or `window_features` passed for `ForecasterStats`, `ForecasterFoundation` or `ForecasterEquivalentDate`, which do not use them (the first two ignored them silently). ([#27](https://github.com/skforecast/skforecast-ai/pull/27), [#31](https://github.com/skforecast/skforecast-ai/pull/31))

+ A `ForecastPlan` built by hand or loaded from JSON raises `ValidationError` for what the generated scripts do not support: a `forecaster` that is not supported or does not match `task_type`, a forecaster argument or a blocking preprocessing step that `plan()` does not generate, or an `interval` without an `interval_method`. `forecast()`, `backtest()`, their `*_code()` methods and `ask()` validate a received plan, and a `DataProfile` whose `frequency` is not a pandas alias raises too. Plans saved with 0.3.1 load unchanged. ([#31](https://github.com/skforecast/skforecast-ai/pull/31), [#33](https://github.com/skforecast/skforecast-ai/pull/33))

+ A `plan` passed to [<code>ForecastingAssistant.forecast()</code>][assistant], `backtest()` or their `*_code()` methods, and a `profile` passed with `data` to them or to `compare()`, are checked against the data: another frequency or shape, or exogenous variables the data does not have, raise `ValueError` instead of running with lags and features that do not fit. Data with new rows or series run with a refreshed profile, noted in `DataProfile.warnings`; call `profile()` and `plan()` again for data of another structure. ([#37](https://github.com/skforecast/skforecast-ai/pull/37), [#41](https://github.com/skforecast/skforecast-ai/pull/41))

*Forecasting*

+ [<code>ForecastingAssistant.forecast()</code>][assistant] and `forecast_code()` in evaluation mode raise `ValueError` unless the test set holds exactly `steps` observations. A longer test set was scored on its first `steps` rows without saying so, and a shorter one failed inside the script. Use `backtest()` to evaluate over a longer period.

+ [<code>ForecastingAssistant.forecast()</code>][assistant] without `test_size`, given a plan that carries the `end_train` of an evaluation, raises `ValueError` instead of evaluating the same dates again: pass `test_size`, or `plan.model_copy(update={'end_train': None})` to forecast the future. ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

*Backtesting and comparison*

+ [<code>ForecastingAssistant.create_cv()</code>][assistant] trains the forecaster once by default (`refit=False`, the skforecast default) instead of refitting it in every fold, which could take an hour instead of seconds on two years of hourly data. The metrics of `backtest()` and `compare()` with the default strategy change; pass `refit=True` (`--refit` in the CLI) to keep the previous behavior. `ForecasterStats`, which skforecast refits in every fold anyway, now trains on a window of fixed size by default, so its metrics change too. ([#33](https://github.com/skforecast/skforecast-ai/pull/33))

+ With several series, [<code>ForecastingAssistant.compare()</code>][assistant] without `candidates` compares `ForecasterRecursiveMultiSeries` against `ForecasterFoundation` (Chronos-2), as it does on a single series, instead of the estimators of `ForecasterRecursiveMultiSeries`. Pass `candidates` to compare the estimators as before. ([#29](https://github.com/skforecast/skforecast-ai/pull/29))

+ [<code>ForecastingAssistant.backtest()</code>][assistant] and `backtest_code()` given the `CVResult` of `create_cv()` without a `plan` or model arguments run the plan of that `CVResult` instead of a new default one. A `CVResult` created for data of another structure raises `ValueError`. Pass `cv=cv_result.cv` to backtest a new default plan as before. ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

+ [<code>ForecastingAssistant.create_cv()</code>][assistant] raises `ValueError` when `skip_folds` names folds that do not exist, which were ignored. ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

*Foundation models*

+ The `estimator` of a `ForecasterFoundation` plan is the Hugging Face model ID (default `'autogluon/chronos-2-small'`) instead of the `'Chronos-2'` label, for example `estimator='google/timesfm-3.0-pytorch'`. An ID that no skforecast adapter serves, `'Chronos-2'` included, raises `ValueError`. ([#29](https://github.com/skforecast/skforecast-ai/pull/29), [#31](https://github.com/skforecast/skforecast-ai/pull/31))

+ [<code>ForecastingAssistant.forecast()</code>][assistant] with a `ForecasterFoundation` plan and an `interval` returns the `pred`, `lower_bound` and `upper_bound` columns of the other forecasters instead of one `q_*` column per quantile. `backtest()` keeps the quantile columns. ([#29](https://github.com/skforecast/skforecast-ai/pull/29))

*Statistical models*

+ Auto-ARIMA (`ForecasterStats`) now gets a seasonal period for more frequencies: the anchored ones pandas infers for quarterly data (`'QS-OCT'`, `'QE-DEC'`: 4) and the multiplied ones whose cycle is a whole number of steps from 2 to 12 (`'2MS'`: 6, `'3h'`: 8). Its predictions, its metrics and the winner of [<code>ForecastingAssistant.compare()</code>][assistant] can change on such data. For a longer cycle, ask for it with `estimator_kwargs={'m': 26}` in `plan()`. ([#37](https://github.com/skforecast/skforecast-ai/pull/37), [#43](https://github.com/skforecast/skforecast-ai/pull/43))

*Data and profiles*

+ A `date_column` that does not hold dates raises `ValueError` instead of being used as an exogenous variable, and so does a `series_id_column` that is also the target or the date column in [<code>ForecastingAssistant.profile()</code>][assistant]. ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

*LLM layer*

+ The `result` keyword of [<code>ForecastingAssistant.ask()</code>][assistant], deprecated in 0.3.0, is removed and raises `TypeError`: pass the object to explain as `context` (`ask(prompt, context=result)`). ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

*CLI*

+ The commands that take `--from-plan` exit with code 1 when `--steps` differs from the steps of the plan, which was ignored: omit it, or change the horizon with `refine-plan --steps`. `--format` exits with code 2 for a value the command does not accept, which printed the default output. ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

+ Clearer `--help` texts: `--interval` takes quantiles, what `--base-url` means for each provider, the fields a `--candidates` config accepts, and the help of `ask --send-data-to-llm` no longer describes it as permission to send raw data, which the CLI never sends. ([#28](https://github.com/skforecast/skforecast-ai/pull/28))

*Performance*

+ Faster on large long-format data, with the same results: [<code>ForecastingAssistant.profile()</code>][assistant] takes about 15 % less on 913,000 rows of 500 series, and the methods that receive data with a saved profile profile the same data once per assistant instead of on every call (`backtest_code()` from 1.7 s to 0.15 s). ([#42](https://github.com/skforecast/skforecast-ai/pull/42))

*Dependencies*

+ skforecast-ai now requires `skforecast>=0.26.0`, and `lightgbm` is a dependency: `LGBMRegressor` is the recommended estimator from 250 observations, so a clean install failed on the default plan with an `ImportError` inside the script.

*Documentation*

+ New documentation home page, and new animations in the [Agentic forecasting][agentic-guide] user guide: what reaches the LLM and how its suggestions are validated, how `create_cv()` and `backtest()` [validate the way you deploy][agentic-guide-backtesting], and how `compare()` [picks the model by measured performance][agentic-guide-compare]. ([#28](https://github.com/skforecast/skforecast-ai/pull/28), [#36](https://github.com/skforecast/skforecast-ai/pull/36))

+ The Quick start section is reorganized into [Installation](../quick-start/how-to-install.md), [Your first forecast](../quick-start/first-forecast.ipynb), now a notebook with its outputs, and the new [Ask the assistant](../quick-start/ask-the-assistant.md). [Using the CLI][cli-guide] is rewritten as a shorter guide organized by task, and the [API reference][assistant] opens with a table of the methods of `ForecastingAssistant`. ([#28](https://github.com/skforecast/skforecast-ai/pull/28))


**Fixed**

*Data and profiles*

+ [<code>ForecastingAssistant.profile()</code>][assistant] reads rows that are not in date order sorted, as the generated script does, and says so in `DataProfile.warnings`: descending dates gave a script that failed, and shuffled rows gave other lags and predictions without any warning. A timestamp with several rows of different values raises `ValueError` suggesting the column to pass as `series_id_column`, instead of silently keeping the first one. ([#32](https://github.com/skforecast/skforecast-ai/pull/32), [#47](https://github.com/skforecast/skforecast-ai/pull/47))

+ Text dates, in a CSV or in a `date_column`, are read as the generated script reads them, so for day-first dates such as `13/01/2012` the profile, the lags and `forecast()` now match the script. Dates written in more than one format, and a date column with empty cells or mixed UTC offsets, raise `InvalidInputError` naming the column, where the script failed or the dates silently became an exogenous variable. ([#32](https://github.com/skforecast/skforecast-ai/pull/32))

+ [<code>ForecastingAssistant.profile()</code>][assistant] infers the frequency despite missing timestamps, which left it unknown and made every forecaster fail with "`y` has a pandas DatetimeIndex without a frequency". For long-format data it reads the frequency and the missing timestamps of every series, not only of the first one: series of different frequencies raise `InvalidInputError`, where the generated script resampled them without an error. ([#27](https://github.com/skforecast/skforecast-ai/pull/27), [#32](https://github.com/skforecast/skforecast-ai/pull/32))

+ A profile, a plan or a result saved with `pickle` by an earlier version loads with the fields added since, where reading one of them raised `AttributeError`. ([#45](https://github.com/skforecast/skforecast-ai/pull/45))

*Plans and overrides*

+ [<code>ForecastingAssistant.plan()</code>][assistant] and every method that builds a plan raise `InvalidInputError` for plans whose generated script always failed: `ForecasterDirectMultiVariate` on long-format data with several series, a multi-series forecaster on a single series, and an exogenous column named like a lag or a window feature (such as `lag_1`). ([#32](https://github.com/skforecast/skforecast-ai/pull/32))

+ [<code>ForecastingAssistant.plan()</code>][assistant] leaves out the calendar features whose columns already exist among the exogenous variables (for example `month` or `hour`), which made `forecast()` and `backtest()` fail with "Duplicated feature names detected". The data column is used instead, and the plan explanation names the skipped features.

+ [<code>ForecastingAssistant.refine_plan()</code>][assistant] no longer carries over values that do not apply to the refined plan: switching forecaster family re-derives the estimator, lags and window features (an ML plan refined with `forecaster="ForecasterStats"` kept `Ridge`), and a new `estimator` drops the previous `estimator_kwargs`. With an LLM, a suggestion of lags or window features that a check of the plan rejects is discarded with a `UserWarning`. ([#27](https://github.com/skforecast/skforecast-ai/pull/27), [#37](https://github.com/skforecast/skforecast-ai/pull/37))

+ Plans with missing values drop rows only when the estimator cannot handle them. The missing timestamps restored by `asfreq()` now count as missing values, so a `Ridge` plan drops those rows instead of failing with "Input X contains NaN", and `RandomForestRegressor` is treated as NaN-tolerant, as it is since scikit-learn 1.4. ([#27](https://github.com/skforecast/skforecast-ai/pull/27))

+ `estimator_kwargs` with numpy values (for example taken from `np.logspace`) made `forecast()`, `backtest()` and `compare()` fail with `NameError: name 'np' is not defined`, and the plan could not be saved as JSON. They are now stored as the Python values they hold.

+ The script of a `ForecasterDirectMultiVariate` plan that does not use the exogenous columns fitted them as series too. It now fits only the target series, so its predictions change. ([#41](https://github.com/skforecast/skforecast-ai/pull/41))

+ Infinite values of the target, an `estimator_kwargs` name that the ARIMA model of `ForecasterStats` does not accept, a foundation model whose backend package is not installed and a `context_length` that is not a positive integer raise before the generated script runs, where it failed inside it. [<code>ForecastingAssistant.profile()</code>][assistant] of a target that is almost all infinite no longer raises a `ValueError` that did not say why. ([#37](https://github.com/skforecast/skforecast-ai/pull/37), [#41](https://github.com/skforecast/skforecast-ai/pull/41))

*Forecasting*

+ [<code>ForecastingAssistant.forecast()</code>][assistant] checks the future `exog` and the end of the target before running: missing or misdated rows, final rows without a target value and missing values that the predictions read raise `InvalidInputError`, where they gave missing, shifted or wrong predictions without an error. What LightGBM and the other tolerant estimators can read gives a warning instead. A plan with `use_exog=False` no longer requires a future `exog`. ([#27](https://github.com/skforecast/skforecast-ai/pull/27), [#32](https://github.com/skforecast/skforecast-ai/pull/32))

+ In evaluation mode (`test_size`), [<code>ForecastingAssistant.forecast()</code>][assistant] checks the training partition as in prediction mode, where a missing value read by the lags, or a series without data at the split, failed inside the script or scored shifted predictions. For data recorded within the day, a training set that ended at midnight no longer includes that whole day, and with long-format series that start on different dates the split no longer falls after the data. ([#37](https://github.com/skforecast/skforecast-ai/pull/37), [#41](https://github.com/skforecast/skforecast-ai/pull/41), [#43](https://github.com/skforecast/skforecast-ai/pull/43))

+ [<code>ForecastingAssistant.forecast()</code>][assistant] in evaluation mode computes the same eight regression metrics as backtesting; it left out, without saying so, any other than MAE, MSE, MASE and MAPE. `compare()` raises `ValueError` before running any candidate for a metric it cannot rank, a metric listed twice or an invalid `interval`, instead of failing every candidate. ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

*Backtesting and comparison*

+ [<code>ForecastingAssistant.backtest()</code>][assistant] raises `InvalidInputError` before running where the script failed inside skforecast: a missing target value that a lag or a test fold reads ("Input contains NaN"), a series with fewer values than its lags read, a first training window shorter than the forecaster needs, or a direct forecaster backtested with a `gap`. `create_cv()` warns when it builds such a strategy, and each candidate of `compare()` reports the same message. ([#27](https://github.com/skforecast/skforecast-ai/pull/27), [#37](https://github.com/skforecast/skforecast-ai/pull/37), [#41](https://github.com/skforecast/skforecast-ai/pull/41), [#43](https://github.com/skforecast/skforecast-ai/pull/43), [#47](https://github.com/skforecast/skforecast-ai/pull/47))

+ [<code>ForecastingAssistant.backtest()</code>][assistant] and `backtest_code()` failed with "Cannot compare tz-naive and tz-aware timestamps" when the dates of the data have a time zone and `initial_train_size` is a date without one (the default of `create_cv()`), and raised `TypeError` for a `TimeSeriesFold` whose `initial_train_size` is a pandas Timestamp. The date is now read in the time zone of the data, kept in the new `DataProfile.time_zone`.

+ [<code>ForecastingAssistant.backtest()</code>][assistant] and `compare()` with an `interval` on several series computed conformal prediction intervals for `ForecasterRecursiveMultiSeries` and `ForecasterDirectMultiVariate`, while the plan and `forecast()` use bootstrapping. They now use bootstrapping too, so the bounds of these backtests change; the point predictions and the metrics do not. ([#33](https://github.com/skforecast/skforecast-ai/pull/33))

+ With `refit=False` or an integer `refit`, the backtesting script, `cv_config` and explanation of a `ForecasterStats` plan said that it was trained once (or every n folds) on a growing window, while skforecast refits ARIMA models in every fold. They now state what runs, and [<code>ForecastingAssistant.create_cv()</code>][assistant] warns with skforecast's `IgnoredArgumentWarning` when a `refit` or `fixed_train_size` passed for it does not run; the metrics do not change. ([#33](https://github.com/skforecast/skforecast-ai/pull/33))

+ [<code>ForecastingAssistant.create_cv()</code>][assistant] with a `prompt` could return a strategy whose first training window was too short for the forecaster of the plan, which failed in `backtest()`. A suggestion below the minimum the plan needs is now retried, falling back to the deterministic defaults after three attempts. ([#45](https://github.com/skforecast/skforecast-ai/pull/45))

*Generated scripts*

+ A crafted value could inject code into the generated script, which `forecast()` and `backtest()` execute: a field of a plan or of a profile loaded from JSON, a foundation model ID or a column name of a CSV. A name that must come from a fixed set raises `ValueError` when the script is rendered, and any other value is written as a quoted literal. A column name with a quote no longer gives a script that fails with `SyntaxError`. ([#31](https://github.com/skforecast/skforecast-ai/pull/31))

+ [<code>ForecastingAssistant.forecast()</code>][assistant], `backtest()` and `compare()` given a CSV path returned a script that loaded `'data.csv'` instead of that file. The script now loads the CSV path or URL passed, also in `forecast_code()`, `backtest_code()` and the CLI. ([#34](https://github.com/skforecast/skforecast-ai/pull/34))

+ The generated script, run as a file, did not read the data as `forecast()` does in two cases: data without dates, where it failed, and long-format data with exogenous variables, where the dates of `exog_future.csv` were read as text and it gave other predictions. It now reads them the same way. ([#34](https://github.com/skforecast/skforecast-ai/pull/34))

*Errors and warnings*

+ Invalid inputs that raised an error of pandas, skforecast or Python (`KeyError`, `AttributeError`, "could not convert string to float", a `ParserError`) now raise `InvalidInputError`, still a `ValueError`, naming the argument at fault: a `series_id_column` that does not exist, a target with text values, a CSV file that cannot be read... See [Exceptions and warnings][exceptions] ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

+ A generated script that does not compile raises `ForecastExecutionError` in `forecast()` and `backtest()`, like a script that fails while it runs, instead of a bare `SyntaxError`. `ForecastExecutionError` has two new attributes, `failed_line` and `failed_statement`: the line of `generated_code` where the error was raised and the statement that holds it. ([#31](https://github.com/skforecast/skforecast-ai/pull/31))

+ [<code>ForecastingAssistant.forecast()</code>][assistant] did not show the warnings that skforecast emits while the generated script runs, such as `MissingValuesWarning` when the estimator is trained with missing values. They are now shown once it ends, and your warning filters still decide which ones. ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

*LLM layer*

+ Without the API key of the provider, [<code>ForecastingAssistant.ask()</code>][assistant], `refine_plan(prompt=...)` and `create_cv(prompt=...)` raised a `UserError` of pydantic-ai. `ask()` now raises `LLMCallError`, and the other two return the deterministic result with a `UserWarning`, as when the call fails. ([#46](https://github.com/skforecast/skforecast-ai/pull/46))

+ [<code>ForecastingAssistant.ask()</code>][assistant] about the result of `backtest_code()` was told that the script trains on all the data and forecasts the future, without metrics. It now receives it as a backtest, with its cross-validation strategy and number of folds, like the result of `backtest()`. ([#34](https://github.com/skforecast/skforecast-ai/pull/34))

+ Two explanations were wrong, and `ask()` repeated them. The explanation of [<code>ForecastingAssistant.compare()</code>][assistant] said that multi-series candidates were ranked by the metric "pooled across series", when it is averaged across series, and the plan explanation said "NaN rows kept (NaN-tolerant estimator)" even when no value was missing. ([#29](https://github.com/skforecast/skforecast-ai/pull/29))

+ A profile or a plan loaded from JSON, or a column name of the data, could add or close sections of what [<code>ForecastingAssistant.ask()</code>][assistant] sends to the LLM through a line break or a tag. Those texts are now escaped. ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

*CLI*

+ Errors and warnings go to standard error instead of standard output, where they broke the JSON of `--format json` for a program reading it. With `--format json` an error is a JSON object `{"error": {"code", "message", "field", "hint"}}`, and an error that has a remedy prints it as `Tip: ...` after the message. See [Using the CLI][cli-guide] ([#37](https://github.com/skforecast/skforecast-ai/pull/37))

+ `skforecast-ai config set` no longer accepts `output.format`. No command read it, so the setting had no effect. `config show` lists it, and any other unknown key found in the file, as ignored. ([#28](https://github.com/skforecast/skforecast-ai/pull/28))


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
