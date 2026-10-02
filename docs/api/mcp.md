# MCP server

The MCP server serves the deterministic workflow of `ForecastingAssistant` to coding agents (Claude Code, Cursor, Claude Desktop and any other MCP client). It needs the `mcp` extra:

```bash
pip install "skforecast-ai[mcp]"
skforecast-ai mcp --allow-dir /path/to/data
```

Importing `skforecast_ai` never imports the server or the `mcp` package. The options of the command are in the [CLI reference](cli.md).

## Tools

Every tool that creates an object returns a [`ToolResult`][skforecast_ai.mcp.models.ToolResult] with its `id`; later tools take ids, never objects, so no plan, profile or cross-validation strategy is ever accepted as JSON.

| Tool | Takes | Returns |
|:--|:--|:--|
| `profile` | `data_path`, `target`, `date_column`, `series_id_column` | a profile id |
| `plan` | `profile_id`, `steps`, `interval`, `forecaster`, `estimator`, `estimator_kwargs`, `lags`, `window_features` | a plan id |
| `refine_plan` | `plan_id`, `overrides` (the keys of `refine_plan()`; an omitted key keeps the value of the plan, and `estimator_kwargs`, `interval`, `lags` and `window_features` set to null ask for the default) | a new plan id |
| `create_cv` | `plan_id` and the arguments of `create_cv()` | a cv id, with its cost |
| `get_code` | `object_id` | a [`CodeResult`][skforecast_ai.mcp.models.CodeResult]: the script of a plan, or the code of a cross-validation strategy |
| `list_objects` | `kind` | an [`ObjectList`][skforecast_ai.mcp.models.ObjectList] |
| `describe_object` | `object_id` | the `ToolResult` that created the object |

Arguments are checked strictly: an unknown argument, a number written as text or a float for an integer is an error. Dates are ISO 8601 text.

The `notices` of a response are the warnings the call emitted, deduplicated, with their source: `data` (reading or profiling the data), `plan` (a warning the plan carries in `plan.warnings`) or `runtime`. Deprecation warnings go to the log of the server (stderr) instead.

## Limits

- The server keeps at most 256 objects and about 1 GB of them (`--max-objects`, `--max-memory-mb`); beyond that, the least recently used ones are removed and their ids raise `unknown_id` saying so. Objects built from a removed one keep working.
- Ids do not survive a restart of the server: an id of a previous run raises `unknown_id` saying so.
- A summary or a script longer than 20,000 characters is cut in the response, and the full text is written to the output directory (`files`).
- Calls run one at a time; a call waits for the previous one to end.
- The output directory (`--output-dir`, by default a new temporary directory that is kept when the server stops) is also the working directory of the server.
- The scripts run in the process of the server, with the permissions of the user who started it.

## Errors

A failure of a tool reaches the agent as an error result whose text is `Error executing tool <name>: ` followed by a JSON object with `code`, `message`, `field`, `hint` and `details`. `code` is one of the [codes of the core](exceptions.md#error-codes) or one of the server:

| `code` | When |
|:--|:--|
| `unknown_id` | The id does not exist, was removed to stay within the limits of the server (`details.removed`), or comes from a previous run of the server. |
| `invalid_path` | The path is not absolute, does not end in `.csv` or holds a control character. |
| `path_not_allowed` | The path is outside the directory given to `--allow-dir`, also after resolving symbolic links. It is checked before looking at the file, so the error does not say whether a file outside exists. |
| `url_not_allowed` | The path is a URL. Download the file into the allowed directory. |
| `data_changed` | The CSV file changed while the server was reading it. Nothing is registered. |

The messages of the core are forwarded as they are: they can name columns, series ids and values of the data, such as categories or dates (at most 5 values each). An error that skforecast-ai did not raise itself is an `internal_error` with its type and the first line of its message (at most 200 characters), which can also quote a value. The server cuts a message to 4,000 characters.

::: skforecast_ai.mcp.create_server

::: skforecast_ai.mcp.run_server

::: skforecast_ai.mcp.models
    options:
      members:
        - ToolResult
        - ToolNotice
        - CodeResult
        - ObjectInfo
        - ObjectList
