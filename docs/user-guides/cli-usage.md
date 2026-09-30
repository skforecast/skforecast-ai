# Using the CLI

The `skforecast-ai` command runs the same pipeline as the Python API from a terminal. Point it at a CSV file or URL, name the target column and the horizon, and it returns the profile of the data, the plan, the predictions, the metrics or the standalone Python script behind them. The core commands need no LLM and no configuration.

This guide shows how to use the commands together. The [CLI reference](../api/cli.md), generated from the code, lists every option of every command; in the terminal, run `skforecast-ai <command> --help`.

---

## Quick start

The CLI is part of the core installation (`pip install skforecast-ai`). The examples in this guide use a public monthly dataset with two exogenous variables; set its URL once:

```bash
DATA="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"
```

```bash
# Inspect the data and see the recommended forecaster and estimator
skforecast-ai profile "$DATA" --target y --date-column fecha

# Hold out the last 12 months, forecast them and report the metrics
skforecast-ai forecast "$DATA" --target y --date-column fecha --steps 12 --test-size 12
```

---

## Commands

| Command | What it does | LLM |
|---------|--------------|-----|
| `profile` | Inspect a dataset and recommend a forecaster and an estimator | |
| `plan` | Build the forecasting plan: forecaster, estimator, lags, window features, interval | |
| `refine-plan` | Change fields of a saved plan without profiling the data again | Optional |
| `forecast` | Profile, plan, generate the script and run it | |
| `forecast-code` | Generate the forecasting script without running it | |
| `backtest` | Evaluate the plan with time series cross-validation | Optional |
| `backtest-code` | Generate the backtesting script without running it | |
| `compare` | Backtest several candidates on the same folds and rank them | |
| `ask` | Answer a question about your data, a plan or forecasting in general | Required |
| `check-llm` | Check how the LLM configuration resolves | Required |
| `config` | Show, set and locate the configuration file | |

The commands that read data take a local CSV path or an `https://` URL as their first argument.

---

## Your data

The combination of `--target`, `--date-column` and `--series-id-column` tells the CLI which layout the CSV has.

| Layout | Options | Example |
|--------|---------|---------|
| Single series | `--target` with one column | `--target y --date-column fecha` |
| Multi-series, wide | `--target` with comma-separated columns | `--target "item_1,item_2,item_3" --date-column date` |
| Multi-series, long | `--target` plus `--series-id-column` | `--target revenue --date-column date --series-id-column store_id` |

```bash
# Multi-series, wide: one column per series
ITEMS="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/simulated_items_sales.csv"
skforecast-ai forecast "$ITEMS" --target "item_1,item_2,item_3" --date-column date --steps 7

# Multi-series, long: one row per series and date (local file)
skforecast-ai forecast sales.csv --target revenue --date-column date --series-id-column store_id --steps 30
```

Every command that reads data accepts these three options, so the examples below apply to any layout.

---

## Forecast

`forecast` runs the whole pipeline in one call and works in two modes:

- **Evaluation mode** (`--test-size`): holds out the end of the series, forecasts it and reports metrics. `--test-size` takes an integer (the last *N* observations), a float in `(0, 1)` (the last fraction) or a date (the start of the test set).
- **Prediction mode** (the default): trains on all the data and forecasts the next `--steps` periods. There is no ground truth, so there are no metrics. When the data has exogenous variables, their future values are required: pass `--exog` with a CSV that has the date column and the same exogenous columns, covering the horizon.

```bash
# Evaluation mode: hold out the last 20% of the series
skforecast-ai forecast "$DATA" --target y --date-column fecha --steps 12 --test-size 0.2

# Prediction mode: this dataset has exogenous variables, so their future values are needed
skforecast-ai forecast "$DATA" --target y --date-column fecha --steps 12 --exog future_exog.csv

# Prediction intervals, with the predictions and the script saved to files
skforecast-ai forecast "$DATA" --target y --date-column fecha --steps 12 --test-size 12 \
  --interval "0.1,0.9" --output-predictions preds.csv --output-code forecast.py
```

A series without exogenous variables forecasts the future with no extra input:

```bash
H2O="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o.csv"
skforecast-ai forecast "$H2O" --target x --date-column fecha --steps 12
```

`--interval` takes two quantiles between 0 and 1: `"0.1,0.9"` is an 80% interval. Percentile values such as `"10,90"` are deprecated and will stop working in a future skforecast release.

`forecast-code` builds the same plan and writes the prediction script instead of running it, to the terminal or to `--output`. The script is the code `forecast` would execute: when the data has exogenous variables, it reads their future values from `exog_future.csv`. `--format json` wraps the script with the profile and the plan.

```bash
skforecast-ai forecast-code "$DATA" --target y --date-column fecha --steps 12 --output forecast.py
```

---

## Adjust the plan

`plan` shows the modeling decisions without running anything: forecaster, estimator, lags, window features, calendar features, metric and interval. Each decision can be overridden, and the assistant fills in the rest.

```bash
skforecast-ai plan "$DATA" --target y --date-column fecha --steps 12

# Choose the forecaster, the estimator and its hyperparameters
skforecast-ai plan "$DATA" --target y --date-column fecha --steps 12 \
  --forecaster ForecasterDirect --estimator Ridge --estimator-kwargs '{"alpha": 0.5}'

# Explicit lags and window features instead of the deterministic selection
skforecast-ai plan "$DATA" --target y --date-column fecha --steps 12 \
  --lags "1,2,3,12" --window-features '[{"stats": ["mean"], "window_size": 12}]'
```

The commands that build a plan (`forecast`, `forecast-code`, `backtest`, `backtest-code`) take the same overrides; `--help` of each command lists the ones it supports.

---

## Backtest and compare

`backtest` evaluates the plan over several folds, as it would run in production. The cross-validation options you do not pass (`--initial-train-size`, `--fold-stride`, `--refit`, `--fixed-train-size`, `--gap`, `--allow-incomplete-fold`) are decided by the assistant from the profile and the plan.

```bash
# Folds decided by the assistant
skforecast-ai backtest "$DATA" --target y --date-column fecha --steps 12

# Your own folds: 100 initial observations, a new fold every 6 steps,
# a fixed training window, no refit and 3 steps between training and test
skforecast-ai backtest "$DATA" --target y --date-column fecha --steps 12 \
  --initial-train-size 100 --fold-stride 6 --fixed-train-size --no-refit --gap 3

# Save the predictions of every fold and the script
skforecast-ai backtest "$DATA" --target y --date-column fecha --steps 12 \
  --output-predictions backtest_preds.csv --output-code backtest.py
```

`backtest-code` takes the data, plan and cross-validation options and writes the backtesting script instead of running it.

```bash
skforecast-ai backtest-code "$DATA" --target y --date-column fecha --steps 12 \
  --initial-train-size 100 --no-refit --output backtest.py
```

`compare` backtests several candidates on the same folds and ranks them by the metric. Without `--candidates`, the candidates are built from the profile. With it, each candidate is a `[name, config]` pair; the config takes `forecaster`, `estimator`, `estimator_kwargs`, `lags` and `window_features`, and all the candidates must belong to the same forecaster family.

```bash
# Candidates built from the profile
skforecast-ai compare "$DATA" --target y --date-column fecha --steps 12

# Your own candidates, ranked by the first metric; save the script of the winner
skforecast-ai compare "$DATA" --target y --date-column fecha --steps 12 \
  --candidates '[["recursive", {"forecaster": "ForecasterRecursive"}], ["direct", {"forecaster": "ForecasterDirect", "estimator": "Ridge", "lags": [1, 2, 3, 12]}]]' \
  --metric "mean_absolute_scaled_error,mean_absolute_error" \
  --output-code best.py
```

`compare` also takes the cross-validation options of `backtest`.

---

## Save, reuse and chain

A saved plan separates the modeling decision from its execution: review it, keep it under version control, and run it again later against updated data.

```bash
# Save the plan
skforecast-ai plan "$DATA" --target y --date-column fecha --steps 12 --format json --output plan.json

# Change the horizon and add an interval without profiling the data again
skforecast-ai refine-plan --from-plan plan.json --steps 6 --interval "0.1,0.9" \
  --format json --output plan_6.json

# Go back to the deterministic selection of lags and window features
skforecast-ai refine-plan --from-plan plan.json --lags auto --window-features auto \
  --format json --output plan_auto.json

# Generate the script from the saved plan: no data argument needed
skforecast-ai forecast-code --from-plan plan.json --output forecast.py

# Run the saved plan; options given with --from-plan are applied on top of it
skforecast-ai forecast "$DATA" --from-plan plan.json --test-size 12 --interval "0.1,0.9"
skforecast-ai backtest "$DATA" --from-plan plan.json
```

`--from-plan` reads the file written by `plan` or `refine-plan`, a bundle with the profile and the plan. `--from-profile` reads the file written by `profile --format json` and is accepted by `plan`, `compare` and `ask`. With `--from-plan`, `forecast-code` and `backtest-code` need no data argument (the script loads the path recorded in the profile); `forecast`, `backtest` and `compare` always need the data because they run the model.

Both options read from standard input when given `-`, so the commands chain with pipes. `-q` hides the progress spinners.

```bash
skforecast-ai profile "$DATA" --target y --date-column fecha --format json -q | \
  skforecast-ai plan --from-profile - --steps 12 --format json -q | \
  skforecast-ai refine-plan --from-plan - --interval "0.1,0.9" --format json -q | \
  skforecast-ai forecast-code --from-plan - --output forecast.py
```

Pipes work in bash, zsh and fish. On Windows, use Git Bash or WSL: PowerShell pipes pass objects instead of text.

---

## Use the LLM

The LLM commands need the `[llm]` extra and a provider (see [Configuring the LLM](llm-configuration.md)). The LLM explains the decisions and turns plain-language descriptions into plan or cross-validation settings; every suggestion is validated before it is used, and the rest of the pipeline stays deterministic.

Set the provider once, then check that it works before running anything else. `check-llm` reports where each setting comes from and exits with code 1 when a check fails, so it can guard a script.

```bash
export SKFORECAST_AI_LLM="openai:gpt-5.5"

# Check the configuration; --test-call also sends a one-line prompt to the model
skforecast-ai check-llm --test-call
```

`ask` answers a general question, or a question about a dataset (its profile), a plan or a saved file. `--data` takes a local CSV file; adding `--steps` builds a plan, so the answer covers the plan and the generated script.

```bash
# General question
skforecast-ai ask "How do I choose between recursive and direct strategies?"

# About a dataset: the LLM receives its profile
skforecast-ai ask "Why this forecaster?" --data h2o_exog.csv --target y --date-column fecha

# About the plan built for it and its script
skforecast-ai ask "Why these lags?" --data h2o_exog.csv --target y --date-column fecha --steps 12

# About a saved plan
skforecast-ai ask "Why these lags?" --from-plan plan.json

# Choose the skills sent with the question
skforecast-ai ask "How do I set up prediction intervals?" --skills "prediction-intervals"
```

The LLM receives summary statistics of the data (frequency, date range, target statistics, missing values, significant lags), the plan and the script, never the observations. See [What is sent to the LLM](llm-configuration.md#what-is-sent-to-the-llm) and, for `--skills`, [Skills](skills.md).

Two commands take a `--prompt` in plain language. In `refine-plan`, it describes the domain and the LLM proposes lags and window features; in `backtest`, it describes how the model is deployed and the LLM translates it into the cross-validation strategy.

```bash
skforecast-ai refine-plan --from-plan plan.json \
  --prompt "Monthly sales with a yearly cycle and a strong December peak" \
  --format json --output plan_llm.json

skforecast-ai backtest "$DATA" --target y --date-column fecha --steps 12 \
  --prompt "We retrain every month with a one-month data delay"
```

---

## Configuration

Settings that apply to every call are kept in `~/.config/skforecast-ai/config.toml`.

```bash
skforecast-ai config set llm.provider "openai:gpt-5.5"
skforecast-ai config show   # current values, API key masked
skforecast-ai config path   # location of the file
```

### LLM resolution precedence

Each LLM setting is read from the first source that defines it: the command option, then the environment variable, then the configuration file.

| Setting | Option | Environment variable | Config key |
|---------|--------|----------------------|------------|
| Provider and model | `--llm` | `SKFORECAST_AI_LLM` | `llm.provider` |
| Endpoint | `--base-url` | `SKFORECAST_AI_BASE_URL` | `llm.base_url` |
| API key | `--api-key` | `SKFORECAST_AI_API_KEY` | `llm.api_key` |
| Send data to the LLM | `--send-data-to-llm` | `SKFORECAST_AI_SEND_DATA_TO_LLM` | `llm.send_data_to_llm` |

`--base-url` is the server URL for Ollama and OpenAI-compatible endpoints, and the AWS region for Bedrock; see [Providers and credentials](llm-configuration.md#providers-and-credentials) for the model strings and the environment variable each provider reads. `--send-data-to-llm` exists for parity with the Python API: the CLI never sends observations, whatever its value. `--skills` is not read from the configuration; pass it on each call.

---

## Scripting

- `--format json` prints the full result as JSON, the same content as `model_dump_json()` in Python. The default is a table (`profile`, `plan`, `refine-plan`, `forecast`, `backtest`, `compare`, `check-llm`), the script (`forecast-code`, `backtest-code`) or text (`ask`).
- `--output` (`-o`) writes the output of `profile`, `plan`, `refine-plan` and the `*-code` commands to a file. `--output-predictions` and `--output-code` save the predictions and the script of the commands that run a model.
- `--quiet` (`-q`) hides the progress spinners.

| Exit code | Meaning |
|-----------|---------|
| 0 | Success |
| 1 | Error: missing file, unknown column, no LLM configured, unreachable URL, failed execution or a failed `check-llm` |
| 2 | Invalid usage: unknown option or missing argument |

Shell completion for commands and options (bash, zsh, fish, PowerShell) is installed with `skforecast-ai --install-completion`; restart the shell afterwards.
