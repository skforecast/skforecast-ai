---
name: skforecast-ai-forecasting
description: Forecast time series stored in CSV files with the tools of the skforecast-ai MCP server (profile, plan, create_cv, backtest, compare, forecast). Use when asked to forecast, backtest or compare forecasting models on tabular time series and the skforecast-ai server is connected.
---

# Forecasting with the skforecast-ai MCP server

The server runs a deterministic forecasting workflow built on skforecast.
Every decision (forecaster, estimator, lags, metric, cross-validation) comes
from rules, so the same inputs give the same results. You choose the inputs
and explain the results; the server decides and computes. Never invent a
number: every figure you report must come from a response or one of its
files.

## Workflow

1. `profile(data_path, target, date_column?, series_id_column?)`: the
   absolute path of a CSV file inside the directory the server may read.
   `target` is one column, or a list of columns for several series side by
   side; `series_id_column` names the column of series ids when the series
   are stacked. Read the summary and the `notices`: frequency, series,
   gaps, exogenous columns and the recommended forecaster.
2. `plan(profile_id, steps, ...)`: `steps` is the horizon in observations
   (12 for a year of monthly data), at most the length of the longest
   series. Leave the other arguments out to take the recommendation; set
   them only when the user asks. `metric` (one metric, or a list whose
   first one ranks) replaces the metric selected from the data, and only
   the metrics given are computed. `use_exog: false` leaves the
   exogenous columns out, so `forecast` needs no `exog_path`.
   `differentiation` (usually 1, for a series with a trend) differences
   the target before training; build the strategy of `create_cv` from
   that plan, since a backtest needs the same order in both.
   `calendar_features` (an empty list for none), `target_transformer`
   (`StandardScaler` or `none`) and `dropna_from_series` replace the
   rules of the machine learning forecasters.
3. Optionally `refine_plan(plan_id, overrides)` to change some decisions.
   An omitted key keeps the value of the plan; every key but
   `forecaster`, `estimator` and `steps` set to null goes back to the
   default.
4. `create_cv(plan_id, ...)`: the backtesting strategy. Read `cost` before
   running anything; above 50 estimator fits it already carries the
   `LongTrainingWarning` the backtest would emit.
5. `backtest(cv_id, plan_id?)`: the accuracy of the plan of the strategy
   over its folds. `plan_id` backtests another plan of the same profile on
   the same folds.
6. Optionally `compare(cv_id, candidates?)`: several configurations on the
   same folds, ranked by its `metric`, else by the metric chosen for the
   plan of the strategy, else by the one selected from the data, with a
   seasonal naive baseline. `links.best_plan_id` is the plan of the winner. Without
   `candidates` it runs the forecasters the profile recommends for the
   family of the data (with several series, ForecasterRecursiveMultiSeries
   and ForecasterFoundation), or the estimators of the recommended
   forecaster when that leaves one, without those above 500 estimator
   fits. Without `interval` it uses the interval of the plan of the
   strategy, so the winner keeps it (with an asymmetric interval there
   is no baseline: it only takes symmetric ones, such as `[0.1, 0.9]`).
7. `forecast(plan_id, test_size?, exog_path?)`: the future. `exog_path` is
   required when the plan uses exogenous variables. With `test_size` it is
   a single hold-out evaluation instead, without `exog_path`: pass the
   integer `steps` (the last `steps` observations) or the ISO 8601 date the
   test set starts at. A fraction only works when it gives exactly `steps`
   observations.

`get_code(object_id)` returns the Python script that ran (for a plan, the
one that would run; a profile has none), so the user can reproduce any
result without the server. `describe_object(object_id)` returns a response
again; `list_objects()` lists the ids.

## How far to trust a result

From most to least reliable:

1. A `compare` in which the winner beats the baseline: measured over the
   `n_folds` of the strategy (at least 2) against a reference. If the
   baseline wins, say so: the data may not be forecastable better than
   repeating the last season. There is no baseline with several series,
   when the target has missing values or dates, or with an asymmetric
   interval (the summary says why):
   then read the rows per series of `files.best_metrics` (`files.metrics`
   of a backtest). A `mean_absolute_scaled_error` below 1 beats a naive
   forecast of that series, above 1 does worse. The summary only gives the
   average, so the worst series is not in it: name it.
2. A `backtest`: measured over the same folds, but without a reference.
3. A `forecast` with `test_size`: one window of `steps` observations. It
   can be lucky or unlucky; do not present it as the accuracy of the model.
4. A `forecast` of the future: no measure of error at all. Report it with
   the accuracy of the backtest or comparison of the same plan.

Prediction intervals are estimates: report them as such. Read `notices`
before you report anything: any notice can change what the result means
(a data problem, a warning of the plan, a long training), so tell the user
about it.

## Cost

`create_cv` returns the `cost` of backtesting its plan: `n_folds`, `n_fits`
(trainings of the forecaster) and `estimator_fits`. A direct forecaster
trains one estimator per step; ForecasterStats is refitted in every fold
whatever `refit` says; foundation models and the baseline count 0, but a
foundation model downloads its weights the first time. `compare` runs every
candidate on the same folds, so it costs about the sum of their fits (its
response reports the total). `compare_estimator_fits` of `create_cv` is
that sum for a `compare` without `candidates`, which can be far more than
the plan (with `refit=true`, ForecasterDirect fits one estimator per step
and fold); a `CompareCostNotice` says so. Above 50 estimator fits a run gets a
`LongTrainingWarning` notice and can take minutes; `compare` without
`candidates` leaves out the candidates above 500. Before an expensive run,
tell the user and prefer fewer folds (a larger `fold_stride` or a later
`initial_train_size`) or `refit=false` (train once, no help for
ForecasterStats).

Progress and cancellation: `compare` reports when each candidate starts
and ends, and any long call (a backtest, a forecast, a candidate) sends a
progress notification every 5 seconds while it runs, naming what runs and
for how long ("ForecasterStats: running (35 s)"). Cancelling a `compare`
waits for the candidate in progress to end and skips the rest; cancelling
another tool waits for it to end (the backtest or the forecast in
progress). Meanwhile only the read tools (`get_code`, `get_failure`,
`list_objects`, `describe_object`) answer: the others wait their turn.

## Inputs

- Paths: absolute paths of `.csv` files inside the allowed directory. No
  URLs: download the file first. No relative paths and no `~`.
- Dates: ISO 8601 text, `"2012-01-01"`, where an argument takes one
  (`initial_train_size` of `create_cv`, `test_size` of `forecast`). A count
  is a number, never text: `"12"` is rejected.
- Arguments are strict: an unknown argument or a wrong type is an error,
  never ignored. Metrics are the names of skforecast:
  `mean_absolute_error`, `mean_squared_error`,
  `mean_absolute_scaled_error`, and the others the schema lists.
- Messages of the library name the arguments of its Python API: `data` is
  `data_path`, `exog` is `exog_path`, `profile`, `plan` and `cv` are the
  ids `profile_id`, `plan_id` and `cv_id`, and `forecast()` or
  `backtest()` are the tools `forecast` and `backtest`. A message can
  also give advice that needs Python (read the file with pandas,
  `dayfirst=True`): follow the `hint` of the error instead.
- Future exogenous values (`exog_path`): one row per date of the horizon
  (and per series when they are stacked), with the date column of the data.
- Ids are valid while the server runs. After a restart, or when an id was
  removed to keep the server within its limits, create the object again.

## Data problems

When the profile, a notice or an error shows a problem in the CSV file
(missing dates, rows without a target, a wrong date column, duplicated
dates, dates written in more than one format, a series without values, an
exogenous column named like a lag or a window feature), tell the user what
it is and what it changes. Never change their file. Only if they agree,
write a corrected copy inside the allowed directory, under a new name, and
`profile` the copy; say what you changed.

## Foundation models

`ForecasterFoundation` forecasts with a pre-trained model, without
training. Its default model is Chronos-2 (`autogluon/chronos-2-small`).
Each of the others has its own license and size, so tell the user which
model, its license and that it downloads its weights before you choose
one; never switch models on your own. Through the server they only take
the `estimator_kwargs` `context_length`, `cross_learning`,
`point_estimate`, `max_horizon`, `add_calendar_features` and
`n_fourier_terms`. Models whose license
restricts commercial use, whose weights are gated or whose provider
requires an account (today the prefixes `google/timesfm-3.0`,
`Salesforce/moirai-2`, `priorlabs/tabpfn` and `taharnbl/TS-ICL`), and any
model for which skforecast gives no license information, only run when
the user started the server with `--allow-model PREFIX`; without it they
are `model_not_allowed`. A model
without its backend package installed where the server runs is
`missing_dependency`.

## Responses

- `summary`: plain text with the decisions, their explanations and
  statistics. A backtest or a forecast adds its metrics and the minimum,
  maximum and mean of the predictions; a comparison, its leaderboard. A
  long summary is cut at 20,000 characters; the full text is in
  `files.summary`.
- `values_included` is always false: no response holds rows of the data
  or of the predictions. The summaries do carry the metrics and the
  leaderboard; the rows (predictions, metrics per fold or series, the
  whole leaderboard) are CSV files listed in `files`. Read them when you
  need the values.
- `notices`: the warnings of the call, with their source (`data`, `plan`
  or `runtime`); at most 20, and `notices_omitted` counts the rest. A
  profile carries the problems of the data (`DataProfileWarning`: missing
  dates, short series, missing values), and a plan carries them again with
  its own warnings, so you see them where you decide.
- `links`: the ids an object was built from. `changeable`: the arguments
  of `refine_plan` or `create_cv` that build a variant of it.

## Errors

An error arrives as `Error executing tool <name>: ` followed by a JSON
object `{code, message, field, hint, details}`. Act on `code` and `field`,
and follow `hint` when there is one:

| code | What to do |
|---|---|
| `invalid_argument` | Fix the argument named in `field`, as the message says. |
| `insufficient_data` | Ask for less: a shorter horizon, fewer lags, a smaller first training set. A target column without any value, or a series too short for the forecaster (the message names it), is also reported this way. |
| `data_not_found`, `invalid_path`, `path_not_allowed`, `url_not_allowed` | Pass the absolute path of a CSV file inside the allowed directory. |
| `data_unreadable` | The file is not a CSV the server can read (empty, binary, not UTF-8, or rows with more fields than the header). Tell the user, as for the data problems above. |
| `file_too_large` | The file is larger than the server reads (`--max-file-mb`, 256 MB by default): pass a smaller file, or ask the user to raise the limit. |
| `data_changed` | The file changed: call `profile` again (or the tool again for an exogenous file). |
| `unknown_id` | Use an id from `list_objects`, or create the object again. |
| `inconsistent_ids` | Pass `backtest` a plan and a strategy built from the same profile. |
| `execution_failed`, `all_candidates_failed` | `get_failure(details.failure_id)` returns the traceback and the code. |
| `missing_dependency` | Tell the user which package to install; `hint` says how, for pip and for uvx. A foundation model without its backend fails this way before running (in `compare`, such a candidate fails and is ranked last). |
| `model_not_allowed` | Tell the user the license in the message; only if they accept it, ask them to restart the server with the `--allow-model` option of `hint`. |
| `internal_error` | Report it to the user with `details.error_id`, which finds the message in the log of the server; do not retry with the same inputs. |

A candidate of `compare` that fails is ranked last instead of failing the
call: `get_failure(comparison_id, candidate)` says why.

## Privacy

The server never sends rows of data in a response. Messages of errors and
warnings are forwarded as the library writes them: they can name columns
and series ids and quote up to 5 values of the data (categories, dates).
The server cuts a message at 4,000 characters, a hint at 1,000, each text
of `details` at 500 and each notice at 1,000. An unexpected error
(`internal_error`) carries only the type of the exception and an id
(`details.error_id`): its message, which can quote a value, goes to the log
of the server with that id. A failure (`get_failure`) holds a traceback,
which can quote values. The scripts of `get_code` and the summary of a
plan name the path of the data file; the other summaries and the failures
do not. Tell the user when they ask what you can see.

Foundation models download their weights from the Hugging Face Hub the
first time they run; a `ModelDownloadNotice` (source `plan`) says so, with
the license, the first time a model whose weights are not in the local
cache is used. The user can forbid downloads by starting the server with
`HF_HUB_OFFLINE=1`.
