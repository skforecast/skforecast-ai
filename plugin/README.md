# skforecast-ai

Forecast time series in CSV files from your coding agent, with deterministic [skforecast](https://skforecast.org) workflows. The plugin brings two things: the skforecast-ai MCP server, whose tools profile a file, plan a forecaster, backtest it, compare candidates and forecast, and a skill that teaches the agent to use them.

The agent brings the language model and explains the results. Every forecasting decision (forecaster, estimator, lags, metric, cross-validation) comes from rule-based code, so the same file gives the same plan and the same predictions, and every result comes with the Python script that produced it.

Ask in plain language:

- "Forecast the next 12 months of `data/sales.csv` and tell me how accurate it is."
- "Compare the candidate models for `data/demand.csv` and show me the leaderboard."
- "Give me the script that produced that forecast."

## Requirements

[uv](https://docs.astral.sh/uv/) must be installed: the plugin starts the server with `uvx`. The server needs Python 3.10 or newer, which `uv` provides.

## What the plugin runs

One local MCP server over stdio, started with the command of `.mcp.json`:

```text
uvx skforecast-ai-mcp==<version> --allow-project-dir
```

- **It downloads** the package `skforecast-ai-mcp`, the launcher of the server, pinned to the version of the plugin, with `skforecast-ai` at that same version and their dependencies from PyPI the first time, which takes about 30 seconds. Nothing else is installed.
- **It reads** only `.csv` files inside the project you open, by absolute path. That includes any export of credentials or of personal data saved as `.csv` in the project. The project is the directory the agent was started in, which the server reads from the environment variable `CLAUDE_PROJECT_DIR`; it refuses to start in your home directory or in the root of a disk.
- **It writes** predictions, metrics and leaderboards to a new temporary directory, never into your project.
- **It runs** the generated forecasting scripts in the process of the server, with your permissions.
- **It opens no network connection itself.** Foundation models need a backend package that the plugin does not install. If you add one, it downloads the weights of the model from the Hugging Face Hub the first time and checks them on each run, without sending data.

There are no hooks, no commands and no other scripts in the plugin.

## What the agent sees

The responses of the tools carry summaries: statistics of the data, dates, column names, the decisions and their explanations, the metrics and the leaderboard. They never carry rows of your data or of the predictions, which stay in files on your machine. Error and warning messages can name columns and quote up to 5 values of the data.

## Documentation

[MCP server for coding agents](https://ai.skforecast.org/stable/user-guides/mcp-server.html) has the setup for other clients, every tool and option, what the server does with your data and the troubleshooting.

## License

Apache-2.0. Source: <https://github.com/skforecast/skforecast-ai>.
