# MCP server for coding agents

Coding agents such as Claude Code, Cursor or Claude Desktop can call **skforecast-ai** as a set of tools through the [Model Context Protocol](https://modelcontextprotocol.io) (MCP). The agent brings the language model: it reads your request, calls the tools and explains the results. skforecast-ai brings the forecasting: every decision (forecaster, estimator, lags, metric, cross-validation) is made by the same deterministic rules as in Python, and every result comes with the script that produced it.

Once the server is connected, you ask in plain language:

- *"Forecast the next 12 months of `data/sales.csv` and tell me how accurate it is."*
- *"Compare the candidate models for `data/demand.csv` and show me the leaderboard."*
- *"Give me the script that produced that forecast."*

The server needs Python 3.10 or newer. Most of the setups below start it with [uv](https://docs.astral.sh/uv/) (`uvx`), which installs the package for you, so install uv first.

---

## Install

Pick the tab of your agent. Every setup gives the server one directory, `--allow-dir`: it only reads CSV files inside it, so give it the narrowest directory that holds your data.

=== "Claude Code"

    Claude Code installs the server and its skill as a plugin from the marketplace of this repository:

    ```text
    /plugin marketplace add skforecast/skforecast-ai
    /plugin install skforecast-ai@skforecast-ai
    ```

    The plugin starts `uvx --from "skforecast-ai[mcp]==<version>" skforecast-ai mcp --allow-dir <your project>`, where `<version>` is the version of the plugin (`claude plugin list` shows it).

    !!! warning "The plugin can read every CSV file of your project"
        The allowed directory is the project you open in Claude Code. That includes an export of credentials or of personal data saved as `.csv`, whose values an error or a summary can quote.

    To pass other options (another directory, `--allow-model`, `HF_HUB_OFFLINE`, or the backend of a foundation model with `uvx --with`), add the server by hand instead and disable the plugin: with both, two servers run. For every project (`--scope user`):

    ```bash
    claude mcp add --scope user skforecast-ai -- uvx --from "skforecast-ai[mcp]" skforecast-ai mcp --allow-dir /absolute/path/to/project
    ```

=== "Cursor"

    In `.cursor/mcp.json` of the project (or `~/.cursor/mcp.json` for every project):

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

=== "VS Code"

    This button adds the server to your user configuration and asks for the directory the first time it starts:

    [![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Server-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect?url=vscode%3Amcp%2Finstall%3F%257B%2522name%2522%253A%2522skforecast-ai%2522%252C%2522command%2522%253A%2522uvx%2522%252C%2522args%2522%253A%255B%2522skforecast-ai-mcp%2522%252C%2522--allow-dir%2522%252C%2522%2524%257Binput%253Aallow_dir%257D%2522%255D%252C%2522inputs%2522%253A%255B%257B%2522type%2522%253A%2522promptString%2522%252C%2522id%2522%253A%2522allow_dir%2522%252C%2522description%2522%253A%2522Absolute%2520path%2520of%2520the%2520directory%2520with%2520your%2520CSV%2520files%2520%2528the%2520server%2520reads%2520only%2520inside%2520it%2529%2522%257D%255D%257D)

    It writes the command `uvx skforecast-ai-mcp --allow-dir <the directory you give>` (see the note below the tabs). To write the configuration yourself: in `.vscode/mcp.json` of the project (or run **MCP: Open User Configuration** from the Command Palette for every project). The key is `servers`, not `mcpServers`:

    ```json
    {
      "servers": {
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

=== "Codex"

    In `~/.codex/config.toml`:

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

=== "Claude Desktop"

    Open **Settings > Developer > Edit Config**, which opens `claude_desktop_config.json` (`~/Library/Application Support/Claude/` on macOS, `%APPDATA%\Claude\` on Windows), add the server and restart the application:

    ```json
    {
      "mcpServers": {
        "skforecast-ai": {
          "command": "uvx",
          "args": [
            "--from", "skforecast-ai[mcp]",
            "skforecast-ai", "mcp", "--allow-dir", "/absolute/path/to/data"
          ]
        }
      }
    }
    ```

=== "pip or pipx"

    Install the package with its `mcp` extra (also included in `all`) in a Python environment, or with pipx in an environment of its own:

    ```bash
    pip install "skforecast-ai[mcp]"
    pipx install "skforecast-ai[mcp]"
    ```

    The client then starts the command `skforecast-ai mcp --allow-dir /absolute/path/to/data`, for example with `"command": "skforecast-ai"` in the JSON of the Cursor tab. If it does not find `skforecast-ai`, give the absolute path of the one in your environment (`which skforecast-ai` on Linux and macOS, `where skforecast-ai` on Windows), or start it with the Python of that environment: `/path/to/python -m skforecast_ai mcp --allow-dir /absolute/path/to/data`.

    Copy the skill by hand: find it in your installation with

    ```bash
    python -c "from importlib.resources import files; print(files('skforecast_ai') / 'mcp' / 'skills' / 'skforecast-ai-forecasting')"
    ```

    and copy that folder into the skills directory of your agent (`.claude/skills/` of your project, or `~/.claude/skills/` for every project, with Claude Code).

The path of `--allow-dir` must be absolute: the client starts the server from a working directory of its own choosing. The place and format of the configuration are those of each client, so check its documentation if they differ.

!!! note "A shorter command: `skforecast-ai-mcp`"
    The package [skforecast-ai-mcp](https://pypi.org/project/skforecast-ai-mcp/) is a launcher with no logic of its own: it installs `skforecast-ai[mcp]` at its same version and runs `skforecast-ai mcp` with the arguments it receives. These two commands start the same server, with the same options and the same first start:

    ```bash
    uvx skforecast-ai-mcp --allow-dir /absolute/path/to/project
    uvx --from "skforecast-ai[mcp]" skforecast-ai mcp --allow-dir /absolute/path/to/project
    ```

    In the configurations above, that is `"args": ["skforecast-ai-mcp", "--allow-dir", "/absolute/path/to/project"]`; pin a version with `skforecast-ai-mcp==<version>`.

!!! tip "Warm up uvx before the first start"
    **The first start is slow.** `uvx` downloads and installs the package and its dependencies the first time, and Python loads them for the first time: about 30 seconds with a fast connection, more with a slow one. A client may give up on a server that takes that long to start: Claude Code waits 30 seconds by default. Run this once before connecting the agent, so later starts take a few seconds (the first one up to 10, the next ones about 2). With the plugin of Claude Code, use `"skforecast-ai[mcp]==<version>"`:

    ```bash
    uvx --from "skforecast-ai[mcp]" skforecast-ai --version
    ```

    In Claude Code, the `MCP_TIMEOUT` environment variable, in milliseconds, makes it wait longer instead: `MCP_TIMEOUT=120000 claude`.

**Install the skill.** [The skill](#the-skill) teaches the agent how to use the tools. The plugin of Claude Code already includes it. For Cursor, VS Code, Codex and other agents, install it with the [skills](https://github.com/vercel-labs/skills) command:

```bash
npx skills add skforecast/skforecast-ai --skill skforecast-ai-forecasting
```

Without the skill the server still works: the most important of its rules also reach the agent in the instructions of the server.

---

## Check the installation

Check that the agent sees the server before you ask for a forecast:

| Client | How to check |
|:--|:--|
| Claude Code | `/mcp` in a session, or `claude mcp list` in a terminal |
| Cursor | The MCP section of its settings lists the server and its tools |
| VS Code | **MCP: List Servers** in the Command Palette; **Show Output** opens the log of the server |
| Codex | `/mcp` in a session, or `codex mcp list` in a terminal |
| Claude Desktop | After the restart, the server appears among the connectors of the chat box ("+" button) |

Then ask something that needs the server, for example *"Profile `/absolute/path/to/project/data.csv` with skforecast-ai"*. The agent should call the `profile` tool and answer with the frequency of the data and the recommended forecaster. If the server does not appear, see [Troubleshooting](#troubleshooting).

---

## What a session looks like

You ask, for example, *"Forecast the next 12 months of `/path/to/data/h2o.csv` and tell me how accurate it is"*. The agent then calls:

1. `profile(data_path="/path/to/data/h2o.csv", target="x")`: the frequency, the series, the exogenous columns and the recommended forecaster, as a profile id. Every column other than the target, the date and the series ids is an exogenous variable, unless `exog_columns` names the ones to use.
2. `plan(profile_id=..., steps=12)`: lags, window features, metric and preprocessing, as a plan id.
3. `create_cv(plan_id=...)`: the cross-validation strategy, with its cost (estimator fits, or inference windows for a foundation model, which is never trained). A notice warns when the backtest will be long.
4. `backtest(cv_id=...)` and, to compare configurations, `compare(cv_id=...)`.
5. `forecast(plan_id=...)`: the forecast of the next 12 months.

Each of these tools returns an id for the next ones, a plain-text summary (the one `describe()` gives in Python) and the warnings of the call. The summary of a backtest or a forecast carries its metrics and statistics of the predictions, and that of a comparison its leaderboard; the predictions themselves, row by row, go to CSV files in the output directory, listed in `files`. `get_code` returns the script that ran, which you can run yourself without the server. The [API reference](../api/mcp.md) lists every tool, its arguments and its errors.

**Long calls.** `compare` sends a progress notification when each candidate starts and ends. Any long call (a backtest, a forecast, a candidate of `compare`) also sends one every 5 seconds while it runs, naming what runs and for how long ("ForecasterStats: running (35 s)"), so a client does not give up on a request that is still working, as long as it asked for progress. Cancelling a call waits for the candidate or the backtest in progress to end: a cancelled `compare` skips its remaining candidates, and a cancelled call registers nothing. Until it ends, only the read tools (`get_code`, `get_failure`, `list_objects`, `describe_object`) answer; the others wait their turn.

---

## Server options

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
| `--allow-model` | (none) | Model ID prefix of a foundation model that the server does not run by default, for example `google/timesfm-3.0`. Repeat it for several. See [Foundation models and licenses](#foundation-models-and-licenses). |

When it starts, the server checks that it can write to the output directory and stops with an error otherwise. It writes its log to the standard error, one line per event: the directories it uses when it starts, the message and traceback of an unexpected error with its id, and one line when the client disconnects (it then exits with code 0, also in the middle of a call).

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

With `claude mcp add`, the variables go before `--`: `claude mcp add --scope user skforecast-ai -e HF_HUB_OFFLINE=1 -- uvx ...`. In `~/.codex/config.toml`, an `env = { HF_HUB_OFFLINE = "1" }` line under `[mcp_servers.skforecast-ai]`.

**Update.** The plugin of Claude Code runs the version it was published with: update it with `claude plugin update skforecast-ai@skforecast-ai`. `uvx` keeps using the version it downloaded first: run `uvx --refresh --from "skforecast-ai[mcp]" skforecast-ai --version` to get the newest one, or pin the one you want in `args` (`"skforecast-ai[mcp]==<version>"`). With pip, `pip install -U "skforecast-ai[mcp]"`.

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
- **Code.** The server never accepts a plan, a profile or a strategy as JSON, only ids and typed arguments, and checks every value the scripts use.
- **Network.** The server does not open network connections itself. Foundation models (`ForecasterFoundation`) download their weights the first time they run, and their backend contacts the Hugging Face Hub on each run to check them, without sending data. Set `HF_HUB_OFFLINE=1` in the environment of the server to forbid any connection to the Hugging Face Hub (and use only models already downloaded). Through the server, foundation models only take the `estimator_kwargs` that keep the data on your machine.
- **Working directory.** The server runs in the output directory, so a library that writes files next to it (CatBoost writes `catboost_info/`) does not write into your project.

!!! warning "Scripts run with your permissions"
    The scripts run in the process of the server, with the permissions of the user who started it: the server limits what the agent can read and pass, not what a script can do. Run it as a user without access to what the agent should not reach.

### Foundation models and licenses

The server reads the license of each foundation model from skforecast. By default it only runs the models whose license does not restrict commercial use, whose weights are not gated and whose provider requires no account of its own. The others need `--allow-model` with their prefix, once you have read and accepted their license. So does a model for which skforecast gives no license information.

| Model | Model ID prefix | Runs by default | License |
|:--|:--|:--|:--|
| Chronos-2 (the default model) | `autogluon/chronos-2`, `amazon/chronos-2` | Yes | |
| TimesFM 2.5 | `google/timesfm-2.5` | Yes | |
| TabICL | `soda-inria/tabicl` | Yes | |
| Nori | `Synthefy/Nori` | Yes | |
| t0 | `theforecastingcompany/t0` | Yes | |
| TimesFM 3.0 | `google/timesfm-3.0` | With `--allow-model` | Non-commercial |
| Moirai | `Salesforce/moirai-2` | With `--allow-model` | CC-BY-NC-4.0 |
| TabPFN | `priorlabs/tabpfn` | With `--allow-model` | Non-commercial; Prior Labs requires an account and accepting its license |
| TS-ICL | `taharnbl/TS-ICL` | With `--allow-model` | Non-commercial |

Without the option, `plan`, `refine_plan` and `compare` reject those models with `model_not_allowed`, whose hint tells the agent which option to ask you for.

The first time a model whose weights are not in the local Hugging Face cache is used, a `ModelDownloadNotice` tells the agent, with the license that skforecast registers for models of that name (the server does not check that the repository exists); later plans and comparisons with the model carry that license in a `ModelLicenseNotice`. TabPFN keeps its weights in a cache of its own, so its notice only says that the server cannot tell whether they are downloaded.

### What the agent does before it calls the server

The server only controls its own tools. Its instructions, its errors and its skill tell the agent never to copy a file into `--allow-dir`, never to write data for you (future values of exogenous variables, missing months) and to ask before writing a corrected copy. An agent can still try to do it with the tools of its client (a `cp` in the shell, reading a file and writing it again), also before the first call to the server, when no message of the server has reached it.

In the checks of this release a small model tried to copy a file from outside the directory in 1 of 3 sessions, and to write a corrected copy before it was asked to in 1 of 12; a larger one in none. In one of those sessions the client allowed the write: the copy had the missing months filled with values of the agent's own, described as an interpolation, and the forecast was made on it.

!!! warning "Keep the agent asking before it writes"
    What stops it is the permission to write of your client: keep the agent asking before it writes or runs shell commands in the project (the default of Claude Code), and read what it proposes to write. With a small model, open any corrected copy and compare it with your file before you trust a forecast made on it.

---

## Troubleshooting

| Symptom | Cause | Fix |
|:--|:--|:--|
| The server does not appear, or fails to start the first time | `uvx` is still downloading the package when the client gives up | Run the warm up command of [Install](#install) once, then restart the client. In Claude Code, `MCP_TIMEOUT=120000 claude` also gives it time. In Codex, set `startup_timeout_sec` |
| The client cannot find `uvx` or `skforecast-ai` | The client starts the server with a `PATH` that is not the one of your terminal | Give the absolute path of the command (`which uvx`, `which skforecast-ai`) |
| The server stops as soon as it starts | `--allow-dir` is missing, relative or not a directory, or the output directory is not writable | Give an absolute path; the log of the server (stderr, shown by the client) says which |
| `path_not_allowed` | The file is outside `--allow-dir` | Copy the file there yourself, or restart the server with another `--allow-dir` |
| `invalid_path` or `url_not_allowed` | The path is relative, is not a `.csv` file or is a URL | Give the absolute path of a CSV file; download a URL first |
| `model_not_allowed` | The license of the foundation model restricts its use | Read its license and add `--allow-model` with its prefix |
| `missing_dependency` | The backend of a foundation model is not installed where the server runs | Install the package the hint names, or add it with `--with` to `uvx` |
| `unknown_id` | The server restarted, or removed the object to stay within its limits | Ask the agent to profile the data again |
| A tool times out in Codex | A comparison takes longer than the default 60 seconds | Set `tool_timeout_sec` |
| Two skforecast-ai servers in `/mcp` of Claude Code | The plugin and a server added by hand both run | Disable one of them |
| Two server processes with Claude Desktop | Claude Desktop starts the server twice when it opens and keeps both processes | Nothing to fix: it talks to one of them, and both stop when the application quits |

To see why a server does not start, run its command in a terminal: it prints the error and stops, or waits for a client (stop it with Ctrl+C).

---

## Errors

A failed call returns an error whose text is `Error executing tool <name>: ` followed by a JSON object with `code`, `message`, `field`, `hint` and `details`. `code` is stable, so the agent can act on it: the [error codes](../api/mcp.md#errors) are those of the Python API plus the ones of the server (`unknown_id`, `inconsistent_ids`, `invalid_path`, `path_not_allowed`, `url_not_allowed`, `data_changed`, `model_not_allowed`, `file_too_large`). When a script fails, `details.failure_id` names its traceback and code, which `get_failure` returns.

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

The skill, `SKILL.md`, teaches the agent the workflow, how far to trust each result, the cost of a backtest, the format of dates, what each error code asks for and what reaches the agent. It is written for the agent that calls the server; the [skills for the LLM](skills.md) are a different thing, the skforecast guides that `ask()` sends to its own model. It follows the [Agent Skills](https://agentskills.io/specification) standard.

??? note "The SKILL.md shipped with the package"

    ````markdown
    --8<-- "skforecast-ai-forecasting/SKILL.md"
    ````

---

## See also

- [MCP server API](../api/mcp.md): every tool, its arguments, its files and its errors.
- [Using the CLI](cli-usage.md): the `mcp` command next to the other commands.
- [Skills for the LLM](skills.md): the skforecast guides that `ask()` sends to its model, not to a coding agent.
- [Agent Skills specification](https://agentskills.io/specification): the format of a `SKILL.md` file.
