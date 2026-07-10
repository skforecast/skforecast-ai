# CLI reference

The `skforecast-ai` CLI runs the full forecasting pipeline from a terminal. Point it at a CSV file or URL, name your target column and horizon, and it returns predictions, evaluation metrics, and the standalone Python script that produced them.

Run `skforecast-ai --help` or `skforecast-ai <command> --help` for inline documentation on any command.

---

## Prerequisites

```bash
pip install skforecast-ai
```

The `ask` command and LLM-assisted backtest configuration also need the optional LLM extras and an API key:

```bash
pip install "skforecast-ai[llm]"
```

See the AI assistant documentation for supported providers, API keys, and local model setup.

---

## Commands overview

| Command | Description |
|---------|-------------|
| `profile` | Inspect a dataset and recommend a forecaster/estimator |
| `plan` | Generate a detailed forecasting plan |
| `refine-plan` | Adjust an existing plan by overriding specific fields |
| `forecast-code` | Generate a self-contained Python forecasting script |
| `backtest-code` | Generate a self-contained Python backtesting script |
| `forecast` | Run end-to-end forecasting (profile, plan, code, execute) |
| `backtest` | Run backtesting evaluation (profile, plan, CV, backtest) |
| `ask` | Ask forecasting questions using an LLM |
| `config show` | Display the current configuration |
| `config set` | Set a configuration value |
| `config path` | Print the config file location |

Every command takes a CSV path or an `https://` URL as its data argument.

---

## Quick start

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Inspect the data and see the recommended model
skforecast-ai profile "$URL" --target y --date-column fecha

# Forecast the next 12 steps
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12
```

---

## Dataset shapes

The CLI handles three data layouts. The combination of `--target`, `--date-column`, and `--series-id-column` tells it which one you have.

| Layout | Flags | Example |
|--------|-------|---------|
| Single series | `--target` with one column | `--target y --date-column fecha` |
| Multi-series, wide | `--target` with comma-separated columns | `--target "item_1,item_2,item_3" --date-column date` |
| Multi-series, long | `--target` plus `--series-id-column` | `--target revenue --date-column date --series-id-column store_id` |

```bash
# Single series, monthly, with exogenous variables
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12

# Single series, hourly
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/bike_sharing_dataset_clean.csv"
skforecast-ai forecast "$URL" --target users --date-column date_time --steps 24

# Multi-series, wide
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/simulated_items_sales.csv"
skforecast-ai forecast "$URL" --target "item_1,item_2,item_3" --date-column date --steps 30

# Multi-series, long (local file)
skforecast-ai forecast sales.csv --target revenue --date-column date --series-id-column store_id --steps 30
```

---

## profile

Inspect a dataset and print the recommended forecaster, estimator, and key data characteristics. No horizon required.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

skforecast-ai profile "$URL" --target y --date-column fecha

# JSON output (machine-readable, used as input to `plan`)
skforecast-ai profile "$URL" --target y --date-column fecha --format json
```

---

## plan

Turn a profile into a detailed forecasting plan: forecaster, estimator, lags, preprocessing, and (optionally) prediction intervals.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

skforecast-ai plan "$URL" --target y --date-column fecha --steps 24

# With prediction intervals
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --interval "0.1,0.9"

# Override the recommended forecaster or estimator
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 \
  --forecaster ForecasterDirect --estimator Ridge

# Save the plan as JSON for later replay
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --format json > plan.json
```

!!! note "Interval values are quantiles"
    `--interval` takes two comma-separated quantiles between 0 and 1, for example `"0.1,0.9"` for an 80% interval. Percentile values such as `"10,90"` are deprecated and will stop working in a future skforecast release.

---

## refine-plan

Adjust an existing plan without re-profiling the dataset: change the horizon, switch forecasters, tune estimator hyperparameters, or add intervals.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Save a plan, then refine it
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --format json > plan.json

# Override the forecast horizon
skforecast-ai refine-plan --from-plan plan.json --steps 12 --format json > plan_12.json

# Switch forecaster
skforecast-ai refine-plan --from-plan plan.json --forecaster ForecasterDirect --format json

# Override estimator hyperparameters
skforecast-ai refine-plan --from-plan plan.json --estimator-kwargs '{"n_estimators": 500}' --format json

# Add prediction intervals
skforecast-ai refine-plan --from-plan plan.json --interval "0.1,0.9" --format json
```

---

## Save and replay a plan

A saved plan separates the modeling decision from execution, which helps with auditing, scheduling, or rerunning the same plan against updated data.

!!! note
    When `--from-plan` is used, `DATA`, `--target`, and `--steps` are optional for `forecast-code` (the values come from the bundle). `DATA` is still required for `forecast`, which needs actual data to execute.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Save a plan
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --format json > plan.json

# Generate code from the saved plan (no re-profiling)
skforecast-ai forecast-code --from-plan plan.json --output forecast.py

# Execute the saved plan against data
skforecast-ai forecast "$URL" --from-plan plan.json

# Override the interval at execution time
skforecast-ai forecast "$URL" --from-plan plan.json --interval "0.1,0.9"
```

---

## forecast-code

Generate a self-contained Python script without executing it. Useful for inspection, version control, or manual runs. The output is the script itself; use `--format json` to wrap it with the profile and plan.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

skforecast-ai forecast-code "$URL" --target y --date-column fecha --steps 24 --output forecast.py

# With prediction intervals
skforecast-ai forecast-code "$URL" --target y --date-column fecha --steps 24 \
  --interval "0.1,0.9" --output forecast.py

# From a saved plan
skforecast-ai forecast-code --from-plan plan.json --output forecast.py
```

---

## forecast

Run the full pipeline end-to-end (profile, plan, generate code, execute) and report predictions, plus metrics when you evaluate. See [Your first forecast](../quick-start/first-forecast.md) for a guided walkthrough.

`forecast` runs in two modes:

- **Prediction mode** (default): trains on all data and forecasts the future. No metrics. When the data has exogenous columns, supply their future values with `--exog`.
- **Evaluation mode** (`--test-size`): holds out the last part of the series as a test set and reports metrics. `--test-size` accepts an integer (last *N* observations), a float in `(0, 1)` (last fraction), or a date (the split point).

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o.csv"

# Forecast the future (prediction mode)
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12

# Evaluate the model on a held-out test set (reports metrics)
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 --test-size 0.2

# With prediction intervals and saved predictions
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 \
  --interval "0.1,0.9" --output-predictions preds.csv

# JSON output
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 --format json > preds.json

# Override forecaster and estimator
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 \
  --forecaster ForecasterDirect --estimator Ridge

# Prediction mode with exogenous data: provide future values covering the horizon
EXOG_URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"
skforecast-ai forecast "$EXOG_URL" --target y --date-column fecha --steps 12 --exog future_exog.csv
```

See [Dataset shapes](#dataset-shapes) for multi-series and long-format examples.

---

## backtest-code

Generate a backtesting script without executing it. Useful for inspection, version control, or manual execution.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Basic backtest code generation
skforecast-ai backtest-code "$URL" --target y --date-column fecha --steps 12

# Save to file
skforecast-ai backtest-code "$URL" --target y --date-column fecha --steps 12 --output backtest_script.py

# Custom CV configuration
skforecast-ai backtest-code "$URL" --target y --date-column fecha --steps 12 \
  --initial-train-size 100 --refit --expanding-train

# Fixed training window, no refit, with gap
skforecast-ai backtest-code "$URL" --target y --date-column fecha --steps 12 \
  --no-refit --fixed-train-size --gap 3

# From a saved plan
skforecast-ai backtest-code "$URL" --from-plan plan.json --output backtest_script.py

# JSON output (profile + plan + code)
skforecast-ai backtest-code "$URL" --target y --date-column fecha --steps 12 --format json

# Pipe: plan → backtest-code
skforecast-ai plan "$URL" --target y --date-column fecha --steps 12 --format json -q | \
  skforecast-ai backtest-code "$URL" --from-plan - --output backtest_script.py

# Multi-series
URL_MULTI="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/simulated_items_sales.csv"
skforecast-ai backtest-code "$URL_MULTI" --target "item_1,item_2,item_3" --date-column date --steps 14

# Override forecaster/estimator
skforecast-ai backtest-code "$URL" --target y --date-column fecha --steps 12 \
  --forecaster ForecasterDirect --estimator Ridge
```

---

## backtest

Run backtesting evaluation with cross-validation. Chains profile → plan → create_cv → backtest automatically.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Basic backtest (uses deterministic CV defaults)
skforecast-ai backtest "$URL" --target y --date-column fecha --steps 12

# Custom CV configuration
skforecast-ai backtest "$URL" --target y --date-column fecha --steps 12 \
  --initial-train-size 100 --refit --expanding-train

# Fixed training window, no refit
skforecast-ai backtest "$URL" --target y --date-column fecha --steps 12 \
  --no-refit --fixed-train-size

# With gap (deployment delay simulation)
skforecast-ai backtest "$URL" --target y --date-column fecha --steps 12 --gap 3

# JSON output
skforecast-ai backtest "$URL" --target y --date-column fecha --steps 12 --format json

# Save predictions and generated code
skforecast-ai backtest "$URL" --target y --date-column fecha --steps 12 \
  --output-predictions backtest_preds.csv --output-code backtest_script.py

# From a saved plan
skforecast-ai backtest "$URL" --from-plan plan.json

# Override forecaster/estimator
skforecast-ai backtest "$URL" --target y --date-column fecha --steps 12 \
  --forecaster ForecasterDirect --estimator Ridge

# LLM-assisted CV configuration (describe your deployment scenario)
skforecast-ai backtest "$URL" --target y --date-column fecha --steps 12 \
  --llm openai:gpt-4o-mini \
  --prompt "We retrain weekly with a 2-day data delay"
```

### Multi-series backtest

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/simulated_items_sales.csv"

skforecast-ai backtest "$URL" --target "item_1,item_2,item_3" --date-column date --steps 14
```

### Long-format multi-series

```bash
skforecast-ai backtest sales.csv --target revenue --date-column date --series-id-column store_id --steps 30
```

### Pipe: plan → backtest

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

skforecast-ai plan "$URL" --target y --date-column fecha --steps 12 --format json -q | \
  skforecast-ai backtest "$URL" --from-plan -
```

---

## ask

!!! note "Requires LLM extras"
    `ask` requires an API key and the LLM extras: `pip install "skforecast-ai[llm]"`. See the AI assistant documentation for supported providers, API key setup, and local model options.

Query an LLM about your forecast, your data, or general forecasting strategy. The LLM can optionally receive your data profile for context, but raw data is never sent by default.

```bash
# Set LLM (or use --llm flag on each call)
export SKFORECAST_AI_LLM="openai:gpt-4o-mini"

# Q&A mode: general question
skforecast-ai ask "How do I choose between recursive and direct strategies?"

# Explain mode: with data context
skforecast-ai ask "What patterns do you see?" \
  --data h2o_exog.csv --target y --date-column fecha --steps 24

# JSON output
skforecast-ai ask "Recommend a forecasting approach" \
  --data h2o_exog.csv --target y --date-column fecha --steps 24 --format json

# Local model via Ollama
skforecast-ai ask "How to handle missing values?" \
  --llm ollama:llama3

# Specific skills
skforecast-ai ask "How to set up prediction intervals?" \
  --skills "prediction-intervals,hyperparameter-optimization"

# Send raw data to LLM (off by default for privacy)
skforecast-ai ask "Analyze this data" \
  --data h2o_exog.csv --target y --date-column fecha --steps 24 --send-data-to-llm
```

---

## Pipe composition

Commands can be chained via JSON stdin/stdout, using `-` as the source. This lets you inspect or modify intermediate results before they reach the next stage.

!!! tip "Shell compatibility"
    Pipe chaining uses standard POSIX syntax. It works in bash, zsh, and fish. On Windows, use Git Bash or WSL; native PowerShell pipes pass objects rather than text and require different syntax.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Profile → Plan
skforecast-ai profile "$URL" --target y --date-column fecha --format json | \
  skforecast-ai plan --from-profile - --steps 24 --format json

# Profile → Plan → Generate Code
skforecast-ai profile "$URL" --target y --date-column fecha --format json | \
  skforecast-ai plan --from-profile - --steps 24 --format json | \
  skforecast-ai forecast-code --from-plan - --output script.py

# Plan → Refine → Generate Code
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --format json | \
  skforecast-ai refine-plan --from-plan - --steps 12 --format json | \
  skforecast-ai forecast-code --from-plan - --output script.py

# Plan → Forecast
skforecast-ai plan "$URL" --target y --date-column fecha --steps 12 --format json | \
  skforecast-ai forecast "$URL" --from-plan -
```

### How it works

- `profile --format json` outputs a `ForecastingProfile` JSON object
- `plan --format json` outputs a bundle: `{"profile": {...}, "plan": {...}}`
- `refine-plan --format json` outputs the same bundle format (refined plan replaces original)
- `--from-profile -` reads a profile from stdin (or a file path)
- `--from-plan -` reads a plan bundle from stdin (or a file path)

---

## Flags reference

### Data input

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--target` | `-t` | Target column(s), comma-separated | `profile`, `plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `ask` |
| `--date-column` | `-d` | Date/timestamp column | `profile`, `plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `ask` |
| `--series-id-column` | `-s` | Series identifier (long-format) | `profile`, `plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `ask` |
| `--exog` | | Future exogenous CSV covering the horizon (prediction mode) | `forecast` |
| `--data` | | Dataset CSV for context | `ask` |

### Forecast configuration

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--steps` | | Forecast horizon | `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `ask` |
| `--test-size` | | Evaluation test set size: int (last *N* obs), float in (0,1) (fraction), or date (test-set start). Omit to forecast the future. | `forecast` |
| `--forecaster` | | Override forecaster class | `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest` |
| `--estimator` | | Override estimator class | `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest` |
| `--estimator-kwargs` | | Estimator hyperparameters as a JSON string | `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest` |
| `--interval` | | Interval quantiles, e.g. `"0.1,0.9"` | `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast` |

### Cross-validation / backtest

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--initial-train-size` | | Initial training window size | `backtest`, `backtest-code` |
| `--fold-stride` | | Step size between CV folds | `backtest`, `backtest-code` |
| `--refit/--no-refit` | | Refit model each fold | `backtest`, `backtest-code` |
| `--fixed-train-size/--expanding-train` | | Fixed or expanding window | `backtest`, `backtest-code` |
| `--gap` | | Gap between train and test | `backtest`, `backtest-code` |
| `--allow-incomplete-fold/--no-incomplete-fold` | | Allow last incomplete fold | `backtest`, `backtest-code` |

### Plan / reproducibility

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--from-profile` | | Load profile JSON (file or `-` for stdin) | `plan` |
| `--from-plan` | | Load plan bundle JSON (file or `-` for stdin) | `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest` |

### LLM

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--llm` | | LLM provider | `ask`, `backtest` |
| `--base-url` | | Custom LLM endpoint | `ask`, `backtest` |
| `--api-key` | | API key for the LLM provider | `ask`, `backtest` |
| `--send-data-to-llm` | | Allow raw data to LLM | `ask` |
| `--skills` | | Skill names to include | `ask` |
| `--prompt` | | LLM prompt for CV config | `backtest` |

### Output

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--format` | | Output format | all data commands |
| `--output` | `-o` | Write to file | `profile`, `plan`, `refine-plan`, `forecast-code`, `backtest-code` |
| `--output-predictions` | | Save predictions CSV | `forecast`, `backtest` |
| `--output-code` | | Save generated script | `forecast`, `backtest` |
| `--quiet` | `-q` | Suppress spinners | all data commands |

---

## Configuration

### Version

```bash
skforecast-ai --version
```

### Persistent config (TOML)

Config file location: `~/.config/skforecast-ai/config.toml` (XDG-compliant).

```bash
# Show config file path
skforecast-ai config path

# Set values
skforecast-ai config set llm.provider "openai:gpt-4o-mini"
skforecast-ai config set llm.base_url "http://localhost:11434/v1"
skforecast-ai config set llm.send_data_to_llm false
skforecast-ai config set output.format table

# Show current config
skforecast-ai config show
```

Valid keys: `llm.provider`, `llm.base_url`, `llm.api_key`, `llm.send_data_to_llm`, `output.format`.

### LLM resolution precedence

Settings are resolved in this order (first wins):

1. CLI flag (`--llm`, `--base-url`, `--api-key`)
2. Environment variable (`SKFORECAST_AI_LLM`, `SKFORECAST_AI_BASE_URL`, `SKFORECAST_AI_API_KEY`)
3. Config file (`llm.provider`, `llm.base_url`, `llm.api_key`)

| Method | Example |
|--------|---------|
| `--llm` flag | `--llm openai:gpt-4o-mini` |
| `SKFORECAST_AI_LLM` env var | `export SKFORECAST_AI_LLM="openai:gpt-4o-mini"` |
| Config file | `skforecast-ai config set llm.provider "openai:gpt-4o-mini"` |
| `--base-url` flag | `--base-url http://localhost:11434/v1` |
| `SKFORECAST_AI_BASE_URL` env var | `export SKFORECAST_AI_BASE_URL="http://localhost:11434/v1"` |
| Config file | `skforecast-ai config set llm.base_url "http://localhost:11434/v1"` |
| `--api-key` flag | `--api-key sk-...` |
| `SKFORECAST_AI_API_KEY` env var | `export SKFORECAST_AI_API_KEY="sk-..."` |
| Config file | `skforecast-ai config set llm.api_key "sk-..."` |
| `--send-data-to-llm` flag | `--send-data-to-llm` / `--no-send-data-to-llm` |
| `SKFORECAST_AI_SEND_DATA_TO_LLM` env var | `export SKFORECAST_AI_SEND_DATA_TO_LLM=false` |
| Config file | `skforecast-ai config set llm.send_data_to_llm false` |

`--send-data-to-llm` (used by `ask`) follows the same precedence and is off by default, so raw data is never sent unless you opt in. `--skills` is not resolved from config; pass it per call.

Providers: `openai:model`, `anthropic:model`, `google:model`, `groq:model`, and `ollama:model`. Any other prefix is treated as an OpenAI-compatible endpoint when combined with `--base-url`.

---

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (missing file, bad column, no LLM, unreachable URL, execution failures) |
| 2 | Invalid usage (unknown flag, missing required argument) |

---

## Shell completion

Typer provides built-in shell completion. To install it:

```bash
skforecast-ai --install-completion
```

This adds tab completion for commands, options, and arguments in your current shell (bash, zsh, fish, PowerShell). After installation, restart your shell or source the config file.
