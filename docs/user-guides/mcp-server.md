# MCP server for coding agents

Coding agents such as Claude Code, Cursor or Claude Desktop can call **skforecast-ai** as a set of tools through the [Model Context Protocol](https://modelcontextprotocol.io) (MCP). The agent brings the language model: it reads your request, calls the tools and explains the results. skforecast-ai brings the forecasting: every decision (forecaster, estimator, lags, metric, cross-validation) is made by the same deterministic rules as in Python, and every result comes with the script that produced it.

---

## Install

There are three ways to install it. Pick the tab of your agent: the Claude Code plugin installs the server and its skill in two commands; the other agents install the skill with `npx skills` and start the server with `uvx`; or install the package yourself with pip or pipx.

=== "Claude Code"

    Claude Code installs the server and its skill as a plugin from the marketplace of this repository. The plugin starts the server with [uv](https://docs.astral.sh/uv/) (`uvx`), so install uv first. In Claude Code:

    ```text
    /plugin marketplace add skforecast/skforecast-ai
    /plugin install skforecast-ai@skforecast-ai
    ```

    The plugin starts `uvx --from "skforecast-ai[mcp]==<version>" skforecast-ai mcp --allow-dir <your project>`: the server may read every CSV file of the project you open in Claude Code (also an export of credentials or of personal data saved as `.csv`, whose values an error or a summary can quote), and the version of the server is the version of the plugin. To pass other options (another directory, `--allow-model`, `HF_HUB_OFFLINE`, or the backend of a foundation model with `uvx --with`), add the server by hand instead, as in the next tab, and disable the plugin: with both, two servers run.

    Before the first use, warm up `uvx` with the version of the plugin (see below why): `uvx --from "skforecast-ai[mcp]==<version>" skforecast-ai --version`.

=== "Cursor, Codex and others"

    Install the skill for your agent with the [skills](https://github.com/vercel-labs/skills) command:

    ```bash
    npx skills add skforecast/skforecast-ai --skill skforecast-ai-forecasting
    ```

    Then add the server to the MCP configuration of your client. These examples start it with [uv](https://docs.astral.sh/uv/) (`uvx`), so nothing else has to be installed; the place and format of the configuration are those of each client, so check its documentation if they differ. The path of `--allow-dir` must be absolute: the client starts the server from a working directory of its own choosing.

    **Cursor**, in `.cursor/mcp.json` of the project (or `~/.cursor/mcp.json` for every project):

    ```json
    {
      "mcpServers": {
        "skforecast-ai": {
          "command": "uvx",
          "args": [
            "--from", "skforecast-ai[mcp]",
            "skforecast-ai", "mcp", "--allow-dir", "/absolute/path/to/project"
          ]
        }
      }
    }
    ```

    **Codex**, in `~/.codex/config.toml`:

    ```toml
    [mcp_servers.skforecast-ai]
    command = "uvx"
    args = [
      "--from", "skforecast-ai[mcp]",
      "skforecast-ai", "mcp", "--allow-dir", "/absolute/path/to/project",
    ]
    startup_timeout_sec = 120
    tool_timeout_sec = 1800
    ```

    The two timeouts are needed: by default Codex waits 10 seconds for a server to start, less than the first start of `uvx` takes, and 60 seconds for a tool to answer, less than a comparison can take.

    **Claude Code without the plugin**, for every project (`-s user`):

    ```bash
    claude mcp add -s user skforecast-ai -- uvx --from "skforecast-ai[mcp]" skforecast-ai mcp --allow-dir /absolute/path/to/project
    ```

    **Claude Desktop** takes the JSON of Cursor in `claude_desktop_config.json`.

=== "pip or pipx"

    Install the package with its `mcp` extra (also included in `all`) in a Python environment, or with pipx in an environment of its own:

    ```bash
    pip install "skforecast-ai[mcp]"
    pipx install "skforecast-ai[mcp]"
    ```

    The client then starts the command `skforecast-ai mcp --allow-dir /absolute/path/to/data`, for example with `"command": "skforecast-ai"` in the JSON of the previous tab. If it does not find `skforecast-ai`, give the absolute path of the one in your environment (`which skforecast-ai` on Linux and macOS, `where skforecast-ai` on Windows), or start it with the Python of that environment: `/path/to/python -m skforecast_ai mcp --allow-dir /absolute/path/to/data`.

    Copy the skill by hand: find it in your installation with

    ```bash
    python -c "from importlib.resources import files; print(files('skforecast_ai') / 'mcp' / 'skills' / 'skforecast-ai-forecasting')"
    ```

    and copy that folder into the skills directory of your agent (`.claude/skills/` of your project, or `~/.claude/skills/` for every project, with Claude Code).

**The first start takes about a minute.** `uvx` downloads and installs the package and its dependencies the first time (about 60 seconds), and a client may give up on a server that takes that long to start. Run this once before connecting the agent, so later starts take about 2 seconds:

```bash
uvx --from "skforecast-ai[mcp]" skforecast-ai --version
```

**Options in the configuration of the client.** Options of the server go at the end of `args` (for example `"--allow-model", "google/timesfm-3.0"` to run TimesFM 3.0 once you have accepted its license), and variables of its environment in `env`:

```json
{
  "mcpServers": {
    "skforecast-ai": {
      "command": "uvx",
      "args": [
        "--from", "skforecast-ai[mcp]",
        "skforecast-ai", "mcp", "--allow-dir", "/absolute/path/to/project",
        "--allow-model", "google/timesfm-3.0"
      ],
      "env": {"HF_HUB_OFFLINE": "1"}
    }
  }
}
```

With `claude mcp add`, the variables go before `--`: `claude mcp add -s user skforecast-ai -e HF_HUB_OFFLINE=1 -- uvx ...`. In `~/.codex/config.toml`, an `env = { HF_HUB_OFFLINE = "1" }` line under `[mcp_servers.skforecast-ai]`.

---

## Options of the server

The agent starts the server itself, as a command, and talks to it over its standard input and output. `--allow-dir` is required: the server only reads CSV files inside that directory.

```bash
skforecast-ai mcp --allow-dir /path/to/data
```

| Option | Default | Meaning |
|:--|:--|:--|
| `--allow-dir` | (required) | Directory the server may read, as an absolute path (an empty or relative value is rejected). Only absolute paths of `.csv` files inside it are accepted, also after resolving symbolic links. |
| `--output-dir` | a new temporary directory | Where the server writes predictions, metrics, leaderboards and long texts. It is also the working directory of the server, and it is kept when the server stops. Its path is logged when the server starts. |
| `--max-objects` | 256 | Most objects (profiles, plans, results) the server keeps. |
| `--max-memory-mb` | 1024 | Memory the objects may take. Beyond either limit, the least recently used objects are removed. |
| `--max-file-mb` | 256 | Largest CSV file (data or future exogenous values) the server reads, checked on the size of the file before reading it. 0 for no limit. |
| `--allow-model` | (none) | Model ID prefix of a foundation model that the server may run although its license restricts commercial use, its weights are gated or its provider requires an account, for example `google/timesfm-3.0`. Repeat it for several. Without it the server only runs the models for which skforecast says none of these applies: today Chronos-2, TimesFM 2.5, TabICL, Nori and t0. A model for which skforecast gives no license information needs the option too. |

When it starts, the server checks that it can write to the output directory and stops with an error otherwise. It writes its log to the standard error, one line per event: the directories it uses when it starts, the message and traceback of an unexpected error with its id, and one line when the client disconnects (it then exits with code 0, also in the middle of a call).

The skill, `SKILL.md`, teaches the agent the workflow, how far to trust each result, the cost of a backtest, the format of dates, what each error code asks for and what reaches the agent. It is written for the agent that calls the server; the [skills for the LLM](skills.md) are a different thing, the skforecast guides that `ask()` sends to its own model. It follows the [Agent Skills](https://agentskills.io/specification) standard, and its content is [below](#the-skill). The most important of its rules also reach the agent without it, in the instructions of the server.

---

## What a session looks like

You ask, for example, *"Forecast the next 12 months of `/path/to/data/h2o.csv` and tell me how accurate it is"*. The agent then calls:

1. `profile(data_path="/path/to/data/h2o.csv", target="x")`: the frequency, the series, the exogenous columns and the recommended forecaster, as a profile id. Every column other than the target, the date and the series ids is an exogenous variable, unless `exog_columns` names the ones to use.
2. `plan(profile_id=..., steps=12)`: lags, window features, metric and preprocessing, as a plan id.
3. `create_cv(plan_id=...)`: the cross-validation strategy, with its cost: estimator fits, or for a foundation model, which is never trained, its inference windows (at most one per series and fold). Above 2000 windows, which can take a minute or more on a CPU (seconds on a GPU), a notice warns, as above 50 estimator fits.
4. `backtest(cv_id=...)` and, to compare configurations, `compare(cv_id=...)`.
5. `forecast(plan_id=...)`: the forecast of the next 12 months.

Each of these tools returns an id for the next ones, a plain-text summary (the one `describe()` gives in Python) and the warnings of the call. The summary of a backtest or a forecast carries its metrics and statistics of the predictions, and that of a comparison its leaderboard; the predictions themselves, row by row, go to CSV files in the output directory, listed in `files`. `get_code` returns the script that ran, which you can run yourself without the server. The [API reference](../api/mcp.md) lists every tool, its arguments and its errors.

`compare` sends a progress notification when each candidate starts and ends. Any long call (a backtest, a forecast, a candidate of `compare`) also sends one every 5 seconds while it runs, naming what runs and for how long ("ForecasterStats: running (35 s)"), so a client does not give up on a request that is still working, as long as it asked for progress. Cancelling a call waits for the candidate or the backtest in progress to end: a cancelled `compare` skips its remaining candidates, and a cancelled call registers nothing. Until it ends, only the read tools (`get_code`, `get_failure`, `list_objects`, `describe_object`) answer; the others wait their turn.

---

## Errors

A failed call returns an error whose text is `Error executing tool <name>: ` followed by a JSON object with `code`, `message`, `field`, `hint` and `details`. `code` is stable, so the agent can act on it: the [error codes](../api/mcp.md#errors) are those of the Python API plus the ones of the server (`unknown_id`, `inconsistent_ids`, `invalid_path`, `path_not_allowed`, `url_not_allowed`, `data_changed`, `model_not_allowed`, `file_too_large`). When a script fails, `details.failure_id` names its traceback and code, which `get_failure` returns.

---

## What the agent sees

The data never travels whole to the agent, and the agent's language model sees what the agent reads:

- **Summaries** carry statistics (minimum, maximum, mean, standard deviation, missing values), dates, column names and series ids, the decisions and their explanations, the metrics, statistics of the predictions and the leaderboard of a comparison. Never rows of the data or of the predictions. The summary of a plan also names the data file its script reads; the other summaries do not name it.
- **Messages** of errors and warnings are forwarded as the library writes them. They can name columns and series ids and quote up to 5 values of the data (categories, dates). The server cuts an error message at 4,000 characters, its hint at 1,000 and each text of its `details` at 500, and sends at most 20 warnings of 1,000 characters each (`notices_omitted` counts the rest). An unexpected error (`internal_error`) carries only the type of the exception and an id: its message and traceback, which can quote a value, go to the log of the server (stderr) under that id.
- **The allowed directory.** The instructions the server gives the agent when it connects name the absolute path of `--allow-dir`, so the agent can find a file you name by a relative path without searching your file system.
- **Scripts** (`get_code`) name the path of the data file they read. **Failures** (`get_failure`) do not (the code that ran reads the data in memory), but they hold a traceback, which can quote values.
- **Files** in the output directory hold rows (predictions, metrics). The agent reads them only if it opens them.

`values_included` is always false in the response of a tool that creates an object, as a reminder that no rows of the data or of the predictions were sent; the metrics and the leaderboard are in the summary.

---

## Security

- **Files.** The server reads only absolute paths of `.csv` files inside `--allow-dir`. A path outside it is rejected before the server looks at the file system, so the error does not say whether the file exists, and checked again after resolving symbolic links. URLs are rejected: download the file first. A file that changes between the profile and a later call, or during a call, is rejected (`data_changed`).
- **Code.** The server never accepts a plan, a profile or a strategy as JSON, only ids and typed arguments, and checks every value the scripts use. The scripts run in the process of the server, with the permissions of the user who started it: the server limits what the agent can read and pass, not what a script can do. Run it as a user without access to what the agent should not reach.
- **Network.** The server does not open network connections itself. Foundation models (`ForecasterFoundation`) download their weights the first time they run; the first time a model whose weights are not in the local Hugging Face cache is used, a `ModelDownloadNotice` tells the agent, with the license that skforecast registers for models of that name (the server does not check that the repository exists); later plans and comparisons with the model carry that license in a `ModelLicenseNotice`. With the weights already downloaded, the backend still contacts the Hugging Face Hub on each run to check them, without sending data. TabPFN keeps its weights in a cache of its own, so its notice only says that the server cannot tell whether they are downloaded. Set `HF_HUB_OFFLINE=1` in the environment of the server to forbid any connection to the Hugging Face Hub (and use only models already downloaded). Through the server, foundation models only take the `estimator_kwargs` that keep the data on your machine.
- **Foundation models and their licenses.** The server reads the license of each foundation model from skforecast. By default it only runs the models whose license does not restrict commercial use, whose weights are not gated and whose provider requires no account of its own: today Chronos-2 (`autogluon/chronos-2`, `amazon/chronos-2`, the default), TimesFM 2.5 (`google/timesfm-2.5`), TabICL (`soda-inria/tabicl`), Nori (`Synthefy/Nori`) and t0 (`theforecastingcompany/t0`). The others need `--allow-model` with their prefix, once you have read and accepted their license: TimesFM 3.0 (`google/timesfm-3.0`, non-commercial), Moirai (`Salesforce/moirai-2`, CC-BY-NC-4.0), TabPFN (`priorlabs/tabpfn`, non-commercial, and Prior Labs requires an account and accepting its license) and TS-ICL (`taharnbl/TS-ICL`, non-commercial). So does a model for which skforecast gives no license information. Without it, `plan`, `refine_plan` and `compare` reject them with `model_not_allowed`, whose hint tells the agent which option to ask you for.
- **Working directory.** The server runs in the output directory, so a library that writes files next to it (CatBoost writes `catboost_info/`) does not write into your project.

---

## Limits

- Calls run one at a time; a call waits for the previous one to end.
- The server reads CSV files of at most `--max-file-mb` (256 MB by default), and a horizon (`steps`) longer than the longest series is rejected when the plan is built.
- Ids live while the server runs. An id of a previous run, or of an object removed to stay within `--max-objects` and `--max-memory-mb`, gives `unknown_id` saying which.
- A summary, a script or a failure longer than 20,000 characters is cut in the response; the full text is written to the output directory.
- Foundation models (`ForecasterFoundation`) need their backend package where the server runs: Chronos-2, the default, needs `chronos-forecasting` (the `foundation` extra). Without it, `backtest` and `forecast` answer `missing_dependency`, whose hint gives the `pip install` command and the `--with` option of `uvx`.
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
