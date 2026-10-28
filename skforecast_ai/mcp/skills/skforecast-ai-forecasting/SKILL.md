---
name: skforecast-ai-forecasting
description: Forecast time series stored in CSV files with the tools of the skforecast-ai MCP server (profile, plan, create_cv, backtest, compare, forecast). Use when asked to forecast, backtest or compare forecasting models on tabular time series and the skforecast-ai server is connected. Also use it before answering what the server or you can see of the user's data (privacy) and what the server does not do.
---

# Forecasting with the skforecast-ai MCP server

The server runs a deterministic forecasting workflow built on skforecast.
Every decision (forecaster, estimator, lags, metric, cross-validation) comes
from rules, so the same inputs give the same results. You choose the inputs
and explain the results; the server decides and computes. Never invent a
number: every figure you report must come from a response or one of its
files. Do not derive one either: no percentage, difference or ratio that a
response does not give ("45% better" from a metric, a margin between two
candidates), nor a root mean squared error from `mean_squared_error`: the
default metrics include `root_mean_squared_error`, and a `metric` of `plan`
of your own can list it.

## Workflow

1. `profile(data_path, target, date_column?, series_id_column?,
   exog_columns?, sep?, decimal?, thousands?, dayfirst?)`: the absolute
   path of a CSV file inside the directory the server may read, which its
   instructions name: build the path from
   it when the user gives a relative one, without searching the file
   system. `target` is one column, or a list of columns for
   several series side by side; `series_id_column` names the column of
   series ids when the series are stacked. Every other column is an
   exogenous variable unless `exog_columns` names the ones to use (an
   empty list for none); set it only when the user asks. Read the summary
   and the `notices`: frequency, series, gaps, exogenous columns and the
   recommended forecaster. Do not open the data file with your own tools
   to look at it: `profile` gives its columns and statistics without rows.
   When the user named the column to forecast, pass it as `target` at
   once. Only when they did not, call `profile` without `target`: its
   error lists the columns of the file, so never guess a target to see
   them. Read the file only to locate a problem an error reports.
2. `plan(profile_id, steps, ...)`: `steps` is the horizon in observations
   (12 for a year of monthly data), at most the length of the longest
   series. When the user gives no horizon (or no target, and more than one
   column could be it), ask; if you assume one, say so before the results. Leave the other arguments out to take the recommendation; set
   them only when the user asks. `metric` (one metric, or a list whose
   first one ranks) replaces the metric selected from the data, and only
   the metrics given are computed. `use_exog: false` leaves the
   exogenous columns out, so `forecast` needs no `exog_path`.
   `differentiation` (usually 1, for a series with a trend) differences
   the target before training; a strategy of `create_cv` serves plans
   with any order, so candidates of `compare` that differ in it share it.
   `calendar_features` (an empty list for none), `target_transformer`
   (`StandardScaler` or `none`) and `dropna_from_series` replace the
   rules of the machine learning forecasters.
3. Optionally `refine_plan(plan_id, overrides)` to change some decisions.
   An omitted key keeps the value of the plan; every key but
   `forecaster`, `estimator` and `steps` set to null goes back to the
   default. A value the new forecaster or estimator cannot take is left
   out, with a notice that names it (the `estimator_kwargs` of another
   estimator; the `differentiation`, `calendar_features` and
   `target_transformer` with `ForecasterStats`, a foundation model or the
   baseline): tell the user. A `backtest` or `forecast` of a plan whose
   estimator you chose instead of the one the rules recommend for its
   forecaster (after a `MissingValuesNotice`, say) carries an
   `EstimatorNotRecommendedNotice`: say in your answer which estimator
   ran, which one the rules recommend and why it was changed.
4. `create_cv(plan_id, ...)`: the backtesting strategy. Read `cost` before
   running anything; above 50 estimator fits (2000 inference windows for a
   foundation model) a `CostNotice` gives the number that `confirm_cost`
   of `backtest` (or of `compare` without `candidates`) needs once the user
   chose that run (see Cost). A notice says when a
   `backtest` of its plan would fail (a direct forecaster with `gap`, or
   a first training window shorter than the forecaster needs): change
   the strategy as the notice says before running it.
5. `backtest(cv_id, plan_id?, confirm_cost?)`: the accuracy of the plan
   of the strategy over its folds. `plan_id` backtests another plan of the
   same profile on the same folds.
6. Optionally `compare(cv_id, candidates?, confirm_cost?)`: several
   configurations on the same folds, ranked by its `metric`, else by the
   metric chosen for the plan of the strategy, else by the one selected
   from the data, with a seasonal naive baseline. `links.best_plan_id` is the plan of the winner. Without
   `candidates` it runs the forecasters the profile recommends for the
   family of the data (with several series, ForecasterRecursiveMultiSeries
   and ForecasterFoundation), or the estimators of the recommended
   forecaster when that leaves one, without those above 500 estimator
   fits. Without `candidates`, when the strategy was created for another
   plan (one from `refine_plan`, say), that plan runs too, with its own
   decisions, in the row `Strategy plan`, a name no candidate can take.
   With `candidates` only they run: the summary names the candidate that
   makes the decisions of that plan, or says, with a notice, that it was
   not compared, and then no row is the user's plan. The summary names
   the row of the plan of the strategy: report that row as the user's
   plan. A row named after a
   forecaster runs the plan the profile recommends for it, which is the
   user's plan only when the summary names that row. Without `interval`
   it uses the interval of the plan of the strategy, so the winner keeps
   it (with an asymmetric interval there is no baseline: it only takes
   symmetric ones, such as `[0.1, 0.9]`).
   The other candidates do not take `use_exog` from that plan: to compare
   them without exogenous variables, `profile` with `exog_columns: []`.
7. `forecast(plan_id, test_size?, exog_path?)`: the future. `exog_path` is
   required when the plan uses exogenous variables: without a file of
   future values from the user, ask for it, or build the plan again with
   `use_exog: false` and say that they were left out. Never write those
   values yourself, nor answer with a `test_size` evaluation instead. With
   `test_size` it is a single hold-out evaluation instead, without
   `exog_path`: pass the integer `steps` (the last `steps` observations) or
   the ISO 8601 date the test set starts at. A fraction only works when it
   gives exactly `steps` observations.

`get_code(object_id)` returns the Python script that ran (for a plan, the
one that would run; a profile has none), so the user can reproduce any
result without the server, and `requirements`, the packages to install
for it with the versions the server runs: name those, not others. Hand
the script as it is; if you change anything (the path of the data, a
comment), say what. `describe_object(object_id)` returns a response
again; `list_objects()` lists the ids.

## How far to trust a result

From most to least reliable:

1. A `compare` in which the winner beats the baseline: measured over the
   `n_folds` of the strategy (at least 2) against a reference. The
   summary says how many configurations beat the baseline: quote that
   count, and never call the winner the only one unless it says so. If
   the baseline wins, say so: the data may not be forecastable better
   than repeating the last season. There is no baseline with several series,
   when the target has missing values or dates, or with an asymmetric
   interval (the summary says why):
   then read the rows per series of `files.best_metrics` (`files.metrics`
   of a backtest). A `mean_absolute_scaled_error` below 1 beats the
   one-step naive forecast of that series, above 1 does worse. The summary
   only gives the average, so the worst series is not in it: name it.
2. A `backtest`: measured over the same folds, but without a reference.
3. A `forecast` with `test_size`: one window of `steps` observations. It
   can be lucky or unlucky; do not present it as the accuracy of the model,
   nor as the forecast of the future: its dates are already in the data (a
   `HoldoutEvaluationNotice` names them).
4. A `forecast` of the future: no measure of error at all. Report it with
   the accuracy of the backtest or comparison of the same plan.

`mean_absolute_scaled_error` and `root_mean_squared_scaled_error` divide
the error by that of the one-step naive forecast (repeat the previous
value) on the training data, in every result and every row of a
leaderboard (a `MetricReferenceNotice` of a backtest or a forecast says
so). That reference is not a seasonal naive forecast nor the baseline of
`compare`: never report a value below 1 as beating either, nor turn it
into a percentage against them.

Prediction intervals are estimates: report them as such, and only from the
rows of `files.predictions` (the bounds of each step). If you have not read
that file, do not describe the interval: name the file. The summary gives
the minimum, maximum and mean of each bound, not a width, so no range
around the point comes from it. The level of `interval` (`[0.1, 0.9]` is
80 %) is nominal: a `backtest` or a `compare` measures it. Their summary
gives, next to the nominal coverage, the share of the actual values that
fell inside the interval (`coverage`) and its mean width in the units of
the target (`interval_width`), by series in `files.metrics` and as columns
of the leaderboard (they do not rank). Report the measured coverage with
the interval, by series when there are several. An
`IntervalCoverageNotice` says that it is clearly below the nominal level:
then never present the interval at its nominal level, nor in a `forecast`
of the same plan; give the measured coverage instead. A `forecast` with
`test_size` does not measure it: one window is too short. With several
series, a notice (and the summary) says when a series was not forecast in
every test fold where it has values: its metrics, and the average across
series, use fewer folds than those of the others, so say it when you
report them. Read `notices` before you report
anything: any notice can change what the result means (a data problem, a
warning of the plan, a long training), so tell the user about it.

## Cost

`create_cv` returns the `cost` of backtesting its plan: `n_folds`, `n_fits`
(trainings of the forecaster), `estimator_fits` and `inference_windows`. A
direct forecaster trains one estimator per step; ForecasterStats is
refitted in every fold whatever `refit` says; foundation models and the
baseline count 0 estimator fits. A foundation model is never trained: its
cost is `inference_windows`, one per series and fold (and it downloads its
weights the first time). `compare` runs every candidate on the same folds,
so it costs the sum of theirs: its `cost` has `n_folds` of the shared
strategy and the totals over all its candidates, the baseline included
(`n_fits`, `estimator_fits` and `inference_windows`), counted before they
run. `compare_estimator_fits` and `compare_inference_windows` of `create_cv`
are those sums for a `compare` without `candidates`, which can be far more
than the plan (with `refit=true`, ForecasterDirect fits one estimator per
step and fold; with many series, the foundation model forecasts each one in
each fold); a `CompareCostNotice` says so (for a foundation plan, its own
`LongTrainingWarning` notice says it instead). `inference_windows` is an
upper bound: a series without data in a fold is not forecast in it.
`compare` without `candidates` leaves out the candidates above 500
estimator fits, never the recommended forecaster nor the plan of the
strategy.

Above 50 estimator fits, or 2000 inference windows (for a `compare`, all
its candidates together), a run is expensive and can take minutes on a
CPU: `backtest` and `compare` refuse it, before anything runs, unless
`confirm_cost` is the number of its cost (its estimator fits, or its
inference windows when only those are above). `create_cv` gives that
number for its plan and for a `compare` without `candidates`, in `cost`
and in its `CostNotice`. With `candidates`, call `compare` without
`confirm_cost`: below the thresholds it runs, and above them its error
(`cost_not_confirmed`) gives the total, what each
candidate adds and the number (a candidate whose plan cannot be built,
or that fails the checks of `backtest`, runs nothing and is not
counted). A number given for another strategy,
plan or candidates is refused the same way, with the new one. Before an
expensive run, stop and do not run it: tell the user the number of fits
and the cheaper strategies the `CostNotice` or the error names. They are
only those that lower that cost: an integer `refit` (retrain every n
folds) or `refit=false` (train once) do nothing for ForecasterStats
(refitted in every fold) nor for a foundation model (never trained), nor
once the strategy trains once; fewer folds (a larger `fold_stride`, a
later `initial_train_size` or `skip_folds`, which ForecasterStats does
not allow) and, for a foundation model, fewer series. Run the expensive one,
with `confirm_cost`, only when the user chooses it in so many words:
asking to retrain regularly is not that choice, and never pass
`confirm_cost` before you asked.

Progress and cancellation: `compare` reports when each candidate starts
and ends, and any long call (a backtest, a forecast, a candidate) sends a
progress notification every 5 seconds while it runs, naming what runs and
for how long ("ForecasterStats: running (35 s)"). Cancelling a `compare`
waits for the candidate in progress to end and skips the rest; cancelling
another tool waits for it to end (the backtest or the forecast in
progress). Meanwhile only the read tools (`get_code`, `get_failure`,
`list_objects`, `describe_object`) answer: the others wait their turn.

## What a result says, and what the server does not do

Report what was measured, never why. A ranking says which candidate had the
lowest error over the folds, not what makes it better for the data: give
no cause, even hedged, for a ranking, a metric or the shape of a forecast
(a seasonal pattern, an event, too little data). Asked why, say that the
server does not measure it and restate the metric and its values.

The server does not search hyperparameters (`compare` runs the candidates
you list: call it that, not a grid search), detect anomalies, select
features or fill in missing values. Say so, offer what it does and stop
there. Do not do any of it another way in the same answer, by hand from
the files or with your own script, even labeled as outside the server:
that is for the user to ask once they know.

## Inputs

- Files: `.csv`, `.tsv`, `.csv.gz` or `.tsv.gz`, separated by `,`, `;`
  or tabulators, with `.` or `,` as decimal mark, and `.` between the
  thousands when `,` is the decimal mark (`1.705,11`). `profile` detects
  them and the profile records them; pass `sep`, `decimal` and
  `thousands` only when an error says they cannot be told. Dates written
  day first (`31/01/2024`) are read day first when a day after the 12th
  says so. When no date tells day from month (monthly data on the first
  of each month), `profile` takes the only order in which the dates are
  regular and says so in a `DataProfileWarning` notice: tell the user,
  who can profile again with `dayfirst`. When that does not tell it
  either (a year or less of monthly data), `profile` fails until
  `dayfirst` gives the order, which only the user knows: ask them, never
  guess it.
- Paths: absolute paths of those files inside the allowed directory,
  which the instructions of the server name (also `details.allowed_dir`
  of a path error). No URLs: download the file first. No relative paths
  and no `~`. Never copy or move a file of the user into that directory
  yourself: tell them it is outside, and that they can copy it there or
  restart the server with another `--allow-dir`.
- Dates: ISO 8601 text, `"2012-01-01"`, where an argument takes one
  (`initial_train_size` of `create_cv`, `test_size` of `forecast`), with
  a time zone (`Z`) only when the dates of the data have one. A count
  is a number, never text: `"12"` is rejected.
- Arguments are strict: an unknown argument or a wrong type is an error,
  never ignored, also a key of an entry of `window_features` other than
  `stats` and `window_size`, and a value of `estimator_kwargs` that a
  scikit-learn estimator rejects. Metrics are the names of skforecast:
  `mean_absolute_error`, `mean_squared_error` (in the squared units of the
  target), `root_mean_squared_error` (in its units),
  `mean_absolute_scaled_error`, and the others the schema lists. The CSV
  of metrics of a `backtest` and of a `forecast` with `test_size` name
  their columns that way, with a column `levels` for the series when there
  are several.
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
dates, dates written in more than one format, a series without
values, an exogenous column named like a lag or a window feature), tell the
user what it is and what it changes. Never change their file. Only if they
agree, write a corrected copy inside the allowed directory, under a new
name, and `profile` the copy; say what you changed. An error names the
first problem it finds, so the file can have others (the error of
repeated dates with different values also counts the identical repeated
rows and the missing dates): tell the user all of them when you ask, and
ask again before fixing a problem they have not agreed to.

## Foundation models

`ForecasterFoundation` forecasts with a pre-trained model, without
training. Its default model is Chronos-2 (`autogluon/chronos-2-small`).
Each of the others has its own license and size, so tell the user which
model, its license and that it downloads its weights before you choose
one; never switch models on your own. State a license only as a response
gives it: a `ModelLicenseNotice` or a `ModelDownloadNotice` of a plan
with a foundation model or of a comparison that ran one, or the message
of `model_not_allowed`. Through the server they only take
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
| `insufficient_data` | Ask for less, as the message says: a shorter horizon, fewer lags, or a first training set that leaves room for the folds (smaller) or for the window of the forecaster (a later `initial_train_size`). A target column without any value, a series too short for the forecaster (the message names it), a horizon of half the data or more in `create_cv`, or a `test_size` that leaves fewer observations to train on than the forecaster needs, is also reported this way. |
| `data_not_found`, `invalid_path`, `url_not_allowed` | Pass the absolute path of a CSV file (`.csv`, `.tsv`, `.csv.gz` or `.tsv.gz`) inside the allowed directory. |
| `path_not_allowed` | The file is outside the allowed directory (`details.allowed_dir`). Do not copy or move it yourself: tell the user, who can copy it there or restart the server with another `--allow-dir`. |
| `data_unreadable` | The file is not a CSV the server can read (empty, binary, not UTF-8, rows with more fields than the header, or a column without name and values): tell the user, as for the data problems above. When the message says the separator, the decimal mark or the thousands separator cannot be told, or that the file holds `.` between thousands and in other values, call `profile` again with `sep`, `decimal` or `thousands` as the hint says, asking the user if you do not know them. When it says the dates read both day first and month first, ask the user in which order they are written and call `profile` again with `dayfirst`. |
| `cost_not_confirmed` | Nothing is wrong: the run is expensive. Do not call the tool again until the user answers: tell them the cost and the cheaper strategies of the message and the hint, and pass `confirm_cost` with the number of `details.confirm_cost` only if they choose that run (see Cost). |
| `file_too_large` | The file is larger than the server reads (`--max-file-mb`, 256 MB by default): pass a smaller file, or ask the user to raise the limit. |
| `data_changed` | The file changed: call `profile` again (or the tool again for an exogenous file). |
| `unknown_id` | Use an id from `list_objects`, or create the object again. |
| `inconsistent_ids` | Pass `backtest` a plan and a strategy built from the same profile. |
| `execution_failed`, `all_candidates_failed` | `get_failure(details.failure_id)` returns the traceback and the code. |
| `missing_dependency` | Tell the user which package to install; `hint` says how, for pip and for uvx. A foundation model without its backend fails this way before running (in `compare`, such a candidate fails and is ranked last). |
| `model_not_allowed` | Tell the user the license in the message; only if they accept it, ask them to restart the server with the `--allow-model` option of `hint`. |
| `internal_error` | Report it to the user with `details.error_id`, which finds the message in the log of the server; do not retry with the same inputs. |

A candidate of `compare` that fails is ranked last instead of failing the
call: `get_failure(comparison_id, candidate)` says why (with the id of a
comparison, `candidate` is required).

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
plan name the path of the data file (a script of `forecast`, also that of
`exog_path`); the other summaries and the failures do not. Tell the user when they ask what you can see.

Foundation models download their weights from the Hugging Face Hub the
first time they run; a `ModelDownloadNotice` (source `plan`) says so, with
the license skforecast registers for models of that name, the first time a
model whose weights are not in the local cache is used. Otherwise a
`ModelLicenseNotice` gives that license. Later runs still
contact the Hub to check the cached weights, without sending data. The
user can forbid any connection to it by starting the server with
`HF_HUB_OFFLINE=1`.
