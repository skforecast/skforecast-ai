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
   are stacked. Read the summary: frequency, series, gaps, exogenous
   columns and the recommended forecaster.
2. `plan(profile_id, steps, ...)`: `steps` is the horizon in observations
   (12 for a year of monthly data). Leave the other arguments out to take
   the recommendation; set them only when the user asks.
3. Optionally `refine_plan(plan_id, overrides)` to change some decisions.
   An omitted key keeps the value of the plan; `estimator_kwargs`,
   `interval`, `lags` and `window_features` set to null go back to the
   default.
4. `create_cv(plan_id, ...)`: the backtesting strategy. Read `cost` before
   running anything.
5. `backtest(cv_id, plan_id?)`: the accuracy of the plan of the strategy
   over its folds. `plan_id` backtests another plan of the same profile on
   the same folds.
6. Optionally `compare(cv_id, candidates?)`: several configurations on the
   same folds, ranked by the metric of the profile, with a seasonal naive
   baseline. `links.best_plan_id` is the plan of the winner.
7. `forecast(plan_id, test_size?, exog_path?)`: the future. `exog_path` is
   required when the data has exogenous variables. With `test_size` (the
   last `steps` observations, a fraction, or the date the test set starts
   at) it is a single hold-out evaluation instead, without `exog_path`.

`get_code(object_id)` returns the Python script that ran (for a plan, the
one that would run; a profile has none), so the user can reproduce any
result without the server. `describe_object(object_id)` returns a response
again; `list_objects()` lists the ids.

## How far to trust a result

From most to least reliable:

1. A `compare` in which the winner beats the baseline: measured over the
   `n_folds` of the strategy (at least 2) against a reference. If the
   baseline wins, say so: the data may not be forecastable better than
   repeating the last season.
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
response reports the total). Above 50 estimator fits a run gets a
`LongTrainingWarning` notice and can take minutes; `compare` without
`candidates` leaves out the candidates above 500. Before an expensive run,
tell the user and prefer fewer folds (a larger `fold_stride` or a later
`initial_train_size`) or `refit=false` (train once, no help for
ForecasterStats). `compare` reports its progress per candidate and stops
before its next candidate when you cancel it; the other tools run to their
end once started.

## Inputs

- Paths: absolute paths of `.csv` files inside the allowed directory. No
  URLs: download the file first. No relative paths and no `~`.
- Dates: ISO 8601 text, `"2012-01-01"`, where an argument takes one
  (`initial_train_size` of `create_cv`, `test_size` of `forecast`). A count
  is a number, never text: `"12"` is rejected.
- Arguments are strict: an unknown argument or a wrong type is an error,
  never ignored. `compare` takes no `metric` in this version.
- Future exogenous values (`exog_path`): one row per date of the horizon
  (and per series when they are stacked), with the date column of the data.
- Ids are valid while the server runs. After a restart, or when an id was
  removed to keep the server within its limits, create the object again.
- Foundation models only take the `estimator_kwargs` `context_length`,
  `cross_learning`, `point_estimate`, `max_horizon`,
  `add_calendar_features` and `n_fourier_terms`. Models with a license
  restriction or gated weights (prefixes `google/timesfm-3.0`,
  `Salesforce/moirai-2`, `priorlabs/tabpfn`, `theforecastingcompany/t0`,
  `taharnbl/TS-ICL`) only run when the user started the server with
  `--allow-model PREFIX`; without it they are `model_not_allowed`.

## Responses

- `summary`: plain text with the decisions, their explanations and
  statistics. A backtest or a forecast adds its metrics and the minimum,
  maximum and mean of the predictions; a comparison, its leaderboard. A
  long summary is cut at 20,000 characters; the full text is in
  `files.summary`.
- `values_included` is always false: the rows (predictions, metrics, the
  leaderboard) are CSV files listed in `files`. Read them when you need
  the values.
- `notices`: the warnings of the call, with their source (`data`, `plan`
  or `runtime`); at most 20, and `notices_omitted` counts the rest.
- `links`: the ids an object was built from. `changeable`: the arguments
  of `refine_plan` or `create_cv` that build a variant of it.

## Errors

An error arrives as `Error executing tool <name>: ` followed by a JSON
object `{code, message, field, hint, details}`. Act on `code` and `field`,
and follow `hint` when there is one:

| code | What to do |
|---|---|
| `invalid_argument` | Fix the argument named in `field`, as the message says. |
| `insufficient_data` | Ask for less: a shorter horizon, fewer lags, a smaller first training set. |
| `data_not_found`, `invalid_path`, `path_not_allowed`, `url_not_allowed` | Pass the absolute path of a CSV file inside the allowed directory. |
| `data_unreadable` | The file is not a CSV the server can read. |
| `data_changed` | The file changed: call `profile` again (or the tool again for an exogenous file). |
| `unknown_id` | Use an id from `list_objects`, or create the object again. |
| `inconsistent_ids` | Pass `backtest` a plan and a strategy built from the same profile. |
| `execution_failed`, `all_candidates_failed` | `get_failure(details.failure_id)` returns the traceback and the code. |
| `missing_dependency` | Tell the user which package to install. |
| `model_not_allowed` | Tell the user the license in the message; only if they accept it, ask them to restart the server with the `--allow-model` option of `hint`. |
| `internal_error` | Report it to the user; do not retry with the same inputs. |

A candidate of `compare` that fails is ranked last instead of failing the
call: `get_failure(comparison_id, candidate)` says why.

## Privacy

The server never sends rows of data in a response. Messages of errors and
warnings are forwarded as the library writes them: they can name columns
and series ids and quote up to 5 values of the data (categories, dates).
The server cuts a message at 4,000 characters, a hint at 1,000, each text
of `details` at 500 and each notice at 1,000; an unexpected error
(`internal_error`) quotes only the first line of its message, at most 200
characters. A failure (`get_failure`) holds a traceback, which can quote
values. Scripts, failures and the summary of a plan name the path of the
data file; the other summaries do not. Tell the user when they ask what you
can see.

Foundation models download their weights from the Hugging Face Hub the
first time they run; a `ModelDownloadNotice` (source `plan`) says so, with
the license, the first time a model whose weights are not in the local
cache is used. The user can forbid downloads by starting the server with
`HF_HUB_OFFLINE=1`.
