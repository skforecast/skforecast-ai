# MCP server for coding agents

Coding agents such as Claude Code, Cursor or Claude Desktop can call **skforecast-ai** as a set of tools through the [Model Context Protocol](https://modelcontextprotocol.io) (MCP). The agent brings the language model: it reads your request, calls the tools and explains the results. skforecast-ai brings the forecasting: every decision (forecaster, estimator, lags, metric, cross-validation) is made by the same deterministic rules as in Python, and every result comes with the script that produced it.

The server needs the `mcp` extra (also included in `all`):

```bash
pip install "skforecast-ai[mcp]"
```

---

## Start the server

The agent starts the server itself, as a command, and talks to it over its standard input and output. `--allow-dir` is required: the server only reads CSV files inside that directory.

```bash
skforecast-ai mcp --allow-dir /path/to/data
```

| Option | Default | Meaning |
|:--|:--|:--|
| `--allow-dir` | (required) | Directory the server may read. Only absolute paths of `.csv` files inside it are accepted, also after resolving symbolic links. |
| `--output-dir` | a new temporary directory | Where the server writes predictions, metrics, leaderboards and long texts. It is also the working directory of the server, and it is kept when the server stops. Its path is logged when the server starts. |
| `--max-objects` | 256 | Most objects (profiles, plans, results) the server keeps. |
| `--max-memory-mb` | 1024 | Memory the objects may take. Beyond either limit, the least recently used objects are removed. |
| `--max-file-mb` | 256 | Largest CSV file (data or future exogenous values) the server reads, checked on the size of the file before reading it. 0 for no limit. |
| `--allow-model` | (none) | Model ID prefix of a foundation model with a license restriction or gated weights that the server may run, for example `google/timesfm-3.0`. Repeat it for several. |

The client starts the command by name. If it does not find `skforecast-ai`, give the absolute path of the one in your Python environment (`which skforecast-ai` on Linux and macOS, `where skforecast-ai` on Windows) in the commands below.

### Claude Code

```bash
claude mcp add skforecast-ai -- skforecast-ai mcp --allow-dir /path/to/data
```

### Claude Desktop and Cursor

Add the server to the MCP configuration of the client (`claude_desktop_config.json` for Claude Desktop, `.cursor/mcp.json` for Cursor):

```json
{
  "mcpServers": {
    "skforecast-ai": {
      "command": "skforecast-ai",
      "args": ["mcp", "--allow-dir", "/path/to/data"]
    }
  }
}
```

---

## Give the agent the skill

The package ships a skill, `SKILL.md`, that teaches an agent the workflow, how far to trust each result, the cost of a backtest, the format of dates, what each error code asks for and what reaches the agent. It is written for the agent that calls the server; the [skills for the LLM](skills.md) are a different thing, the skforecast guides that `ask()` sends to its own model. Agents that follow the [Agent Skills](https://agentskills.io/specification) standard load it from a skills directory. Find it in your installation:

```bash
python -c "from importlib.resources import files; print(files('skforecast_ai') / 'mcp' / 'skills' / 'skforecast-ai-forecasting')"
```

and copy that folder into `.claude/skills/` of your project (or `~/.claude/skills/` for every project) to use it with Claude Code. Its content is [below](#the-skill).

---

## What a session looks like

You ask, for example, *"Forecast the next 12 months of `/path/to/data/h2o.csv` and tell me how accurate it is"*. The agent then calls:

1. `profile(data_path="/path/to/data/h2o.csv", target="x")`: the frequency, the series, the exogenous columns and the recommended forecaster, as a profile id.
2. `plan(profile_id=..., steps=12)`: lags, window features, metric and preprocessing, as a plan id.
3. `create_cv(plan_id=...)`: the cross-validation strategy, with its cost.
4. `backtest(cv_id=...)` and, to compare configurations, `compare(cv_id=...)`.
5. `forecast(plan_id=...)`: the forecast of the next 12 months.

Each of these tools returns an id for the next ones, a plain-text summary (the one `describe()` gives in Python) and the warnings of the call. The summary of a backtest or a forecast carries its metrics and statistics of the predictions, and that of a comparison its leaderboard; the predictions themselves, row by row, go to CSV files in the output directory, listed in `files`. `get_code` returns the script that ran, which you can run yourself without the server. The [API reference](../api/mcp.md) lists every tool, its arguments and its errors.

`compare` sends a progress notification when each candidate starts and ends, and stops before its next candidate when the client cancels it. The other tools run to their end once started.

---

## Errors

A failed call returns an error whose text is `Error executing tool <name>: ` followed by a JSON object with `code`, `message`, `field`, `hint` and `details`. `code` is stable, so the agent can act on it: the [error codes](../api/mcp.md#errors) are those of the Python API plus the ones of the server (`unknown_id`, `inconsistent_ids`, `invalid_path`, `path_not_allowed`, `url_not_allowed`, `data_changed`, `model_not_allowed`, `file_too_large`). When a script fails, `details.failure_id` names its traceback and code, which `get_failure` returns.

---

## What the agent sees

The data never travels whole to the agent, and the agent's language model sees what the agent reads:

- **Summaries** carry statistics (minimum, maximum, mean, standard deviation, missing values), dates, column names and series ids, the decisions and their explanations, the metrics, statistics of the predictions and the leaderboard of a comparison. Never rows. The summary of a plan also names the data file its script reads; the other summaries do not name it.
- **Messages** of errors and warnings are forwarded as the library writes them. They can name columns and series ids and quote up to 5 values of the data (categories, dates). The server cuts an error message at 4,000 characters, its hint at 1,000 and each text of its `details` at 500, and sends at most 20 warnings of 1,000 characters each (`notices_omitted` counts the rest). An unexpected error (`internal_error`) carries only the type of the exception and an id: its message and traceback, which can quote a value, go to the log of the server (stderr) under that id.
- **Scripts** (`get_code`) and **failures** (`get_failure`) name the path of the data file, and a failure holds a traceback, which can quote values.
- **Files** in the output directory hold rows (predictions, metrics). The agent reads them only if it opens them.

`values_included` is always false in the response of a tool that creates an object, as a reminder that no rows were sent.

---

## Security

- **Files.** The server reads only absolute paths of `.csv` files inside `--allow-dir`. A path outside it is rejected before the server looks at the file system, so the error does not say whether the file exists, and checked again after resolving symbolic links. URLs are rejected: download the file first. A file that changes between the profile and a later call, or during a call, is rejected (`data_changed`).
- **Code.** The server never accepts a plan, a profile or a strategy as JSON, only ids and typed arguments, and checks every value the scripts use. The scripts run in the process of the server, with the permissions of the user who started it: the server limits what the agent can read and pass, not what a script can do. Run it as a user without access to what the agent should not reach.
- **Network.** The server does not open network connections itself. Foundation models (`ForecasterFoundation`) download their weights from the Hugging Face Hub the first time they run; the first time a model whose weights are not in the local Hugging Face cache is used, a `ModelDownloadNotice` tells the agent, with the license of the model. Set `HF_HUB_OFFLINE=1` in the environment of the server to forbid downloads (and use only models already downloaded). Through the server, foundation models only take the `estimator_kwargs` that keep the data on your machine.
- **Foundation models and their licenses.** By default the server only runs the foundation models for which skforecast registers no license restriction and no gated weights: Chronos-2 (`autogluon/chronos-2`, `amazon/chronos-2`, the default), TimesFM 2.5 (`google/timesfm-2.5`), TabICL (`soda-inria/tabicl`) and Nori (`Synthefy/Nori`). The others need `--allow-model` with their prefix, once you have read and accepted their license: TimesFM 3.0 (`google/timesfm-3.0`, non-commercial), Moirai (`Salesforce/moirai-2`, CC-BY-NC-4.0), TabPFN (`priorlabs/tabpfn`, non-commercial without an enterprise license), TS-ICL (`taharnbl/TS-ICL`, non-commercial) and t0 (`theforecastingcompany/t0`, gated weights). Without it, `plan`, `refine_plan` and `compare` reject them with `model_not_allowed`, whose hint tells the agent which option to ask you for.
- **Working directory.** The server runs in the output directory, so a library that writes files next to it (CatBoost writes `catboost_info/`) does not write into your project.

---

## Limits

- Calls run one at a time; a call waits for the previous one to end.
- The server reads CSV files of at most `--max-file-mb` (256 MB by default), and a horizon (`steps`) longer than the longest series is rejected when the plan is built.
- Ids live while the server runs. An id of a previous run, or of an object removed to stay within `--max-objects` and `--max-memory-mb`, gives `unknown_id` saying which.
- A summary, a script or a failure longer than 20,000 characters is cut in the response; the full text is written to the output directory.
- `compare` has no `metric` argument yet: candidates are ranked by the metric of the profile.
- The script of a forecast with future exogenous values reads them from `exog_future.csv` in its working directory: copy the file there to run it.

---

## The skill

The `SKILL.md` shipped with the package:

````markdown
--8<-- "skforecast-ai-forecasting/SKILL.md"
````

---

## See also

- [MCP server API](../api/mcp.md): every tool, its arguments, its files and its errors.
- [Using the CLI](cli-usage.md): the `mcp` command next to the other commands.
- [Skills for the LLM](skills.md): the skforecast guides that `ask()` sends to its model, not to a coding agent.
- [Agent Skills specification](https://agentskills.io/specification): the format of a `SKILL.md` file.
