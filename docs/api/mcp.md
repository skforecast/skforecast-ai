# MCP server

The MCP server serves the deterministic workflow of `ForecastingAssistant` to coding agents (Claude Code, Cursor, Claude Desktop and any other MCP client). It needs the `mcp` extra:

```bash
pip install "skforecast-ai[mcp]"
skforecast-ai mcp --allow-dir /path/to/data
```

Importing `skforecast_ai` never imports the server or the `mcp` package. The options of the command are in the [CLI reference](cli.md); how to connect an agent and give it the skill that ships with the package, in [MCP server for coding agents](../user-guides/mcp-server.md).

## Tools

Every tool that creates an object returns a [`ToolResult`][skforecast_ai.mcp.models.ToolResult] with its `id`; later tools take ids, never objects, so no plan, profile or cross-validation strategy is ever accepted as JSON.

| Tool | Takes | Returns |
|:--|:--|:--|
| `profile` | `data_path`, `target`, `date_column`, `series_id_column` | a profile id |
| `plan` | `profile_id`, `steps`, `interval`, `forecaster`, `estimator`, `estimator_kwargs`, `lags`, `window_features` | a plan id |
| `refine_plan` | `plan_id`, `overrides` (the keys of `refine_plan()`; an omitted key keeps the value of the plan, and `estimator_kwargs`, `interval`, `lags` and `window_features` set to null ask for the default) | a new plan id |
| `create_cv` | `plan_id` and the arguments of `create_cv()` | a cv id, with its cost |
| `backtest` | `cv_id`, `plan_id` (another plan of the same profile; null for the plan of the strategy) | a backtest id; predictions and metrics in CSV files |
| `compare` | `cv_id`, `candidates` (`[{name, config}]`, null for those of the profile), `interval`, `baseline` | a comparison id, the plan of the winner in `links.best_plan_id`; the leaderboard and the predictions and metrics of the winner in CSV files |
| `forecast` | `plan_id`, `test_size` (null to forecast the future), `exog_path` | a forecast id; predictions (and metrics in evaluation) in CSV files |
| `get_code` | `object_id`, `candidate` (of a comparison) | a [`CodeResult`][skforecast_ai.mcp.models.CodeResult]: the script that ran, or that would run for a plan. A forecast with `exog_path` reads the future exogenous values from `exog_future.csv` in its working directory: copy the file there to run it |
| `get_failure` | `object_id` (`details.failure_id` of an error, or a comparison), `candidate` | a [`FailureResult`][skforecast_ai.mcp.models.FailureResult]: the traceback and the code of a failed run |
| `list_objects` | `kind` | an [`ObjectList`][skforecast_ai.mcp.models.ObjectList] |
| `describe_object` | `object_id` | the `ToolResult` that created the object |

`compare` takes no `metric` in this version: candidates are ranked by the metric of the profile. A candidate whose configuration is not valid is ranked last with its error, as in Python, and `get_failure` returns why it failed. `compare` sends a progress notification when each candidate starts and ends (`2 * completed + started` over `2 * total`). Every tool that runs the core also sends one every 5 seconds while its worker thread is busy, to a client that asked for progress: `k` notifications after an event of progress `p` send `p + k / (k + 1)` (from 0, with no total, for a call without events), so the values grow without reaching the next event, and the message names what runs and for how long ("ForecasterStats: running (35 s)"). A cancelled `compare` stops before its next candidate; any other cancelled call waits for its work to end. A cancelled call registers nothing. While a call runs, only `get_code`, `get_failure`, `list_objects` and `describe_object` answer; the other tools wait their turn.

Foundation models only take the `estimator_kwargs` `context_length`, `cross_learning`, `point_estimate`, `max_horizon`, `add_calendar_features` and `n_fourier_terms` through the server: other arguments of the adapters of skforecast can send the data to a remote service or download files. A foundation model for which skforecast registers a license restriction or gated weights (`license_restriction`, `requires_hf_auth` of its `FoundationModelInfo`) only runs when the server was started with `--allow-model` and a prefix of its model ID; otherwise `plan`, `refine_plan` and `compare` raise `model_not_allowed`. The weights of a foundation model are downloaded from the Hugging Face Hub the first time it runs: the first time a plan or a candidate uses a model whose weights are not in the local Hugging Face cache, the response carries a `ModelDownloadNotice` (source `plan`) with its license. Set `HF_HUB_OFFLINE=1` in the environment of the server to forbid downloads.

Arguments are checked strictly: an unknown argument, a number written as text or a float for an integer is an error. Dates are ISO 8601 text.

The files of a response are CSV files with the index of the data: `predictions` and `metrics` of a backtest or a forecast, `leaderboard`, `best_predictions` and `best_metrics` of a comparison. A summary, a script or a failure too long for a response is written to a file as well.

The `notices` of a response are the warnings the call emitted, deduplicated, with their source: `data` (reading or profiling the data), `plan` (a warning the plan carries in `plan.warnings`) or `runtime`. Deprecation warnings go to the log of the server (stderr) instead. Besides those, a profile carries `data_profile.warnings` (category `DataProfileWarning`, source `data`), a plan carries them too, with any text of `plan.warnings` not emitted in the call (category `PlanWarning`), and `create_cv` carries the `LongTrainingWarning` that a backtest of the strategy will emit (above 50 estimator fits).

`compare` without `interval` computes the interval of the plan the strategy was built for (unlike `compare()` in Python, whose default is no interval), so the plan of the winner keeps it; to compare without one, build the strategy from a plan without interval. The seasonal naive baseline and `ForecasterStats` only compute symmetric intervals (lower + upper = 1), so with an asymmetric one they fail and are ranked last. `backtest` and `forecast` of a `ForecasterFoundation` plan whose backend package is not installed where the server runs raise `missing_dependency` before running anything; a candidate of `compare` with that model fails and is ranked last, as in Python.

## Limits

- The server keeps at most 256 objects and about 1 GB of them (`--max-objects`, `--max-memory-mb`); beyond that, the least recently used ones are removed and their ids raise `unknown_id` saying so. Objects built from a removed one keep working.
- Ids do not survive a restart of the server: an id of a previous run raises `unknown_id` saying so.
- A summary, a script or a failure longer than 20,000 characters is cut in the response, and the full text is written to the output directory (`files`).
- Calls run one at a time; a call waits for the previous one to end.
- CSV files larger than `--max-file-mb` (256 MB by default) are rejected before being read, and `plan` and `refine_plan` reject a `steps` longer than the longest series of the profile (`invalid_argument`).
- The output directory (`--output-dir`, by default a new temporary directory that is kept when the server stops) is also the working directory of the server.
- The scripts run in the process of the server, with the permissions of the user who started it. The server trusts the agent as much as that user: it limits what the agent can read (`--allow-dir`) and pass, not what the scripts it builds can do.
- The JSON of the results, their scripts and the summary of a plan (its script lists the file it reads) name the path of the data file; the other summaries do not.

## Errors

A failure of a tool reaches the agent as an error result whose text is `Error executing tool <name>: ` followed by a JSON object with `code`, `message`, `field`, `hint` and `details`. `code` is one of the [codes of the core](exceptions.md#error-codes) or one of the server:

| `code` | When |
|:--|:--|
| `unknown_id` | The id does not exist, was removed to stay within the limits of the server (`details.removed`), or comes from a previous run of the server. |
| `inconsistent_ids` | The plan and the cross-validation strategy passed to `backtest` come from different profiles. |
| `invalid_path` | The path is not absolute, does not end in `.csv` or holds a control character. |
| `path_not_allowed` | The path is outside the directory given to `--allow-dir`, also after resolving symbolic links. It is checked before looking at the file, so the error does not say whether a file outside exists. |
| `url_not_allowed` | The path is a URL. Download the file into the allowed directory. |
| `file_too_large` | The CSV file (data or future exogenous values) is larger than `--max-file-mb` (256 MB by default; 0 for no limit). Its size is checked before reading it; `details` has the size and the limit. |
| `model_not_allowed` | A foundation model with a license restriction or gated weights that `--allow-model` does not allow. `details` has its license; `hint` names the option to ask the user for. |
| `data_changed` | The CSV file changed since it was profiled, or the data or the exogenous file changed while the server was reading it. Nothing is registered; call `profile` again (or the tool again, for the exogenous file). |

When a script fails (`execution_failed`) or every candidate of a comparison fails (`all_candidates_failed`), `details.failure_id` names the full failure, which `get_failure` returns: it never goes in the error itself. Like the messages, a failure can quote values of the data, and the code it holds names the path of the data file.

The messages of the core are forwarded as they are: they can name columns, series ids and values of the data, such as categories or dates (at most 5 values each). An error that skforecast-ai did not raise itself is an `internal_error` with only its type and an id (`details.error_type`, `details.error_id`): its message and traceback, which can quote a value, are written to the log of the server (stderr) with that id. The server cuts a message to 4,000 characters, a hint to 1,000 and each text of `details` to 500, and a response carries at most 20 notices of 1,000 characters each (`notices_omitted` counts the rest).

::: skforecast_ai.mcp.create_server

::: skforecast_ai.mcp.run_server

::: skforecast_ai.mcp.models
    options:
      members:
        - ToolResult
        - ToolNotice
        - CodeResult
        - FailureResult
        - ObjectInfo
        - ObjectList
