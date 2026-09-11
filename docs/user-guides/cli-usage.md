# CLI reference

The `skforecast-ai` CLI runs the full forecasting pipeline from a terminal. Point it at a CSV file or URL, name your target column and horizon, and it returns predictions, evaluation metrics, and the standalone Python script that produced them.

Run `skforecast-ai --help` or `skforecast-ai <command> --help` for inline documentation on any command.

---

## Prerequisites

```bash
pip install skforecast-ai
```

The `ask` and `check-llm` commands, `refine-plan --prompt` and `backtest --prompt` also need the optional LLM extras and an API key:

```bash
pip install "skforecast-ai[llm]"
```

See [How to install](../quick-start/how-to-install.md) for the provider-specific extras and [LLM resolution precedence](#llm-resolution-precedence) below for where the provider, endpoint and API key are read from.

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
| `compare` | Compare several forecasters and report a ranked leaderboard |
| `ask` | Ask forecasting questions using an LLM |
| `check-llm` | Check how the LLM configuration resolves and whether it can be used |
| `config show` | Display the current configuration |
| `config set` | Set a configuration value |
| `config path` | Print the config file location |

Data commands take a CSV path or an `https://` URL as their data argument. `refine-plan` works on a saved plan instead, and `ask` receives an optional dataset through `--data`.

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

# Explicit lags and window features instead of the automatic selection
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 \
  --lags "1,2,3,12" --window-features '[{"stats": ["mean"], "window_size": 12}]'

# Save the plan as JSON for later replay
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --format json > plan.json

# From a saved profile (DATA and --target come from it)
skforecast-ai plan --from-profile profile.json --steps 24
```

!!! note "Interval values are quantiles"
    `--interval` takes two comma-separated quantiles between 0 and 1, for example `"0.1,0.9"` for an 80% interval. Percentile values such as `"10,90"` are deprecated and will stop working in a future skforecast release.

---

## refine-plan

Adjust an existing plan without re-profiling the dataset: change the horizon, switch forecasters, tune estimator hyperparameters, set lags or window features, or add intervals. With `--prompt`, the LLM proposes lags and window features from the domain knowledge you describe (requires the LLM extras and a provider, see [ask](#ask)).

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

# Set lags and window features explicitly
skforecast-ai refine-plan --from-plan plan.json --lags "1,2,3,12" \
  --window-features '[{"stats": ["mean", "std"], "window_size": 12}]' --format json

# Go back to the deterministic lag and window feature selection
skforecast-ai refine-plan --from-plan plan.json --lags auto --window-features auto --format json

# Let the LLM propose lags and window features from domain knowledge
skforecast-ai refine-plan --from-plan plan.json --llm openai:gpt-5.5 \
  --prompt "Monthly sales with a yearly cycle and a strong December peak" --format json
```

---

## Save and replay a plan

A saved plan separates the modeling decision from execution, which helps with auditing, scheduling, or rerunning the same plan against updated data.

!!! note
    When `--from-plan` is used, `DATA`, `--target`, and `--steps` are optional for `forecast-code` and `backtest-code` (the values come from the bundle), and `--from-profile` makes `DATA` and `--target` optional for `plan`. `DATA` is still required for `forecast`, `backtest` and `compare`, which need actual data to execute.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Save a plan
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --format json > plan.json

# Generate code from the saved plan (no re-profiling)
skforecast-ai forecast-code --from-plan plan.json --output forecast.py

# Execute the saved plan against data
skforecast-ai forecast "$URL" --from-plan plan.json

# Override the interval at execution time: any modeling flag given alongside
# --from-plan is applied on top of the saved plan, as refine-plan would
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
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

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
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 --exog future_exog.csv
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

# From a saved plan (DATA is optional: the script loads the path recorded in the profile)
skforecast-ai backtest-code --from-plan plan.json --output backtest_script.py

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
  --llm openai:gpt-5.5 \
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

## compare

Compare several forecaster configurations with the same cross-validation strategy and report a metric-ranked leaderboard. Chains profile → plan → create_cv → backtest for each candidate. When `--candidates` is omitted, the candidates are built automatically from the profile.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Auto-built candidates from the profile
skforecast-ai compare "$URL" --target y --date-column fecha --steps 12

# Explicit candidate configurations (JSON array of [name, config] pairs)
skforecast-ai compare "$URL" --target y --date-column fecha --steps 12 \
  --candidates '[["rec", {"forecaster": "ForecasterRecursive"}], ["dir", {"forecaster": "ForecasterDirect", "estimator": "Ridge", "lags": [1, 2, 3, 12]}]]'

# Rank by a specific metric (first entry ranks the table)
skforecast-ai compare "$URL" --target y --date-column fecha --steps 12 \
  --metric "mean_absolute_scaled_error,mean_absolute_error"

# Custom CV configuration
skforecast-ai compare "$URL" --target y --date-column fecha --steps 12 \
  --initial-train-size 100 --refit --expanding-train

# Save the winning configuration's script
skforecast-ai compare "$URL" --target y --date-column fecha --steps 12 \
  --output-code best_script.py

# JSON output (full serialized ComparisonResult)
skforecast-ai compare "$URL" --target y --date-column fecha --steps 12 --format json
```

### Pipe: profile → compare

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

skforecast-ai profile "$URL" --target y --date-column fecha --format json -q | \
  skforecast-ai compare "$URL" --from-profile - --steps 12
```

---

## ask

!!! note "Requires LLM extras"
    `ask` requires an API key and the LLM extras: `pip install "skforecast-ai[llm]"`. See [Configuring the LLM](llm-configuration.md) for supported providers, API key setup, and local model options.

Query an LLM about your data, a saved profile or plan, or general forecasting strategy. With `--data` the dataset is profiled first and the profile is what the LLM explains; add `--steps` to build a plan and have the question answered about the plan and the script generated from it. `--from-profile` explains a saved profile and `--from-plan` explains a saved plan bundle together with its generated script, without any data.

The LLM receives a summary of the dataset (frequency, date range, target statistics, missing values, significant lags), the modeling decisions and the generated script. The observations themselves are never sent by the CLI: none of the objects `ask` works with carry them, so `--send-data-to-llm` has no effect on what leaves your machine.

```bash
# Set LLM (or use --llm flag on each call)
export SKFORECAST_AI_LLM="openai:gpt-5.5"

# Q&A mode: general question
skforecast-ai ask "How do I choose between recursive and direct strategies?"

# Explain the profile of a dataset
skforecast-ai ask "Why this forecaster?" \
  --data h2o_exog.csv --target y --date-column fecha

# Explain the plan built for it (adds --steps)
skforecast-ai ask "What patterns do you see?" \
  --data h2o_exog.csv --target y --date-column fecha --steps 24

# Explain a saved profile
skforecast-ai ask "Why this forecaster?" --from-profile profile.json

# Explain a saved plan bundle and the script generated from it
skforecast-ai ask "Why these lags?" --from-plan plan.json

# JSON output
skforecast-ai ask "Recommend a forecasting approach" \
  --data h2o_exog.csv --target y --date-column fecha --steps 24 --format json

# Local model via Ollama
skforecast-ai ask "How to handle missing values?" \
  --llm ollama:qwen3:8b

# Specific skills
skforecast-ai ask "How to set up prediction intervals?" \
  --skills "prediction-intervals,hyperparameter-optimization"
```

---

## check-llm

Report how the LLM configuration resolves before running anything: provider and model, where the credentials come from and whether the environment variable is set (its value is never shown), what `--base-url` means for that provider, whether the extras are installed and, for Ollama, whether the server answers. The command exits with code 1 when a check fails, so it can guard a script. With `--test-call`, a one-line prompt is sent to the model once the static checks pass. See [Configuring the LLM](llm-configuration.md#check-your-configuration).

```bash
# Check the configuration resolved from flags, environment and config file
skforecast-ai check-llm --llm openai:gpt-5.5

# Same, and send a one-line prompt to the model
skforecast-ai check-llm --llm openai:gpt-5.5 --test-call

# Machine-readable report (the `ok` field summarizes it)
skforecast-ai check-llm --format json

# Local model: also checks that the Ollama server answers
skforecast-ai check-llm --llm ollama:qwen3:8b
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
| `--target` | `-t` | Target column(s), comma-separated | `profile`, `plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `compare`, `ask` |
| `--date-column` | `-d` | Date/timestamp column | `profile`, `plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `compare`, `ask` |
| `--series-id-column` | `-s` | Series identifier (long-format) | `profile`, `plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `compare`, `ask` |
| `--exog` | | Future exogenous CSV covering the horizon (prediction mode) | `forecast` |
| `--data` | | Dataset CSV for context | `ask` |

### Forecast configuration

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--steps` | | Forecast horizon | `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `compare`, `ask` |
| `--test-size` | | Evaluation test set size: int (last *N* obs), float in (0,1) (fraction), or date (test-set start). Omit to forecast the future. | `forecast` |
| `--forecaster` | | Override forecaster class | `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest` |
| `--estimator` | | Override estimator class | `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest` |
| `--estimator-kwargs` | | Estimator hyperparameters as a JSON string | `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest` |
| `--interval` | | Interval quantiles, e.g. `"0.1,0.9"`. With `--from-plan`, replaces the interval of the plan | `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `compare` |
| `--lags` | | Explicit lags: a positive int or a comma-separated list of unique positive ints, e.g. `"1,2,3,12"`; `auto` re-runs the deterministic selection when refining a saved plan | `plan`, `refine-plan`, `forecast-code`, `backtest-code` |
| `--window-features` | | Window features as a JSON array, e.g. `'[{"stats": ["mean"], "window_size": 7}]'`; `auto` re-runs the deterministic selection when refining a saved plan | `plan`, `refine-plan`, `forecast-code`, `backtest-code` |
| `--candidates` | | Candidate configurations as a JSON array of `[name, config]` pairs | `compare` |
| `--metric` | | Metric(s) to compute, comma-separated; the first ranks the leaderboard | `compare` |

### Cross-validation / backtest

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--initial-train-size` | | Initial training window: number of observations or an ISO date (e.g. `2023-03-01`) marking the end of the initial training set | `backtest`, `backtest-code`, `compare` |
| `--fold-stride` | | Step size between CV folds | `backtest`, `backtest-code`, `compare` |
| `--refit/--no-refit` | | Refit model each fold (unset: decided by the assistant) | `backtest`, `backtest-code`, `compare` |
| `--fixed-train-size/--expanding-train` | | Fixed or expanding window (unset: decided by the assistant) | `backtest`, `backtest-code`, `compare` |
| `--gap` | | Gap between train and test | `backtest`, `backtest-code`, `compare` |
| `--allow-incomplete-fold/--no-incomplete-fold` | | Allow last incomplete fold (unset: decided by the assistant) | `backtest`, `backtest-code`, `compare` |

### Plan / reproducibility

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--from-profile` | | Load profile JSON (file or `-` for stdin) | `plan`, `compare`, `ask` |
| `--from-plan` | | Load plan bundle JSON (file or `-` for stdin) | `refine-plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `ask` |

### LLM

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--llm` | | LLM provider | `ask`, `refine-plan`, `backtest`, `check-llm` |
| `--base-url` | | Custom LLM endpoint (AWS region for `bedrock`, server URL for `ollama`) | `ask`, `refine-plan`, `backtest`, `check-llm` |
| `--api-key` | | API key for the LLM provider | `ask`, `refine-plan`, `backtest`, `check-llm` |
| `--test-call` | | Send a one-line prompt to the model once the static checks pass | `check-llm` |
| `--send-data-to-llm` | | Accepted for parity with the Python API; the CLI never sends observations | `ask` |
| `--skills` | | Comma-separated skill names to include; see [Skills](skills.md) for the valid names | `ask` |
| `--prompt` | | Natural-language guidance for the LLM: domain knowledge for lags and window features, or the deployment scenario for the CV strategy | `refine-plan`, `backtest` |

### Output

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--format` | | Output format: `table` or `json` (`code` or `json` for `forecast-code` and `backtest-code`, `text` or `json` for `ask`) | all data commands |
| `--output` | `-o` | Write to file | `profile`, `plan`, `refine-plan`, `forecast-code`, `backtest-code` |
| `--output-predictions` | | Save predictions CSV | `forecast`, `backtest` |
| `--output-code` | | Save generated script (the winner's for `compare`) | `forecast`, `backtest`, `compare` |
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
skforecast-ai config set llm.provider "openai:gpt-5.5"
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
| `--llm` flag | `--llm openai:gpt-5.5` |
| `SKFORECAST_AI_LLM` env var | `export SKFORECAST_AI_LLM="openai:gpt-5.5"` |
| Config file | `skforecast-ai config set llm.provider "openai:gpt-5.5"` |
| `--base-url` flag | `--base-url http://localhost:11434/v1` |
| `SKFORECAST_AI_BASE_URL` env var | `export SKFORECAST_AI_BASE_URL="http://localhost:11434/v1"` |
| Config file | `skforecast-ai config set llm.base_url "http://localhost:11434/v1"` |
| `--api-key` flag | `--api-key sk-...` |
| `SKFORECAST_AI_API_KEY` env var | `export SKFORECAST_AI_API_KEY="sk-..."` |
| Config file | `skforecast-ai config set llm.api_key "sk-..."` |
| `--send-data-to-llm` flag | `--send-data-to-llm` / `--no-send-data-to-llm` |
| `SKFORECAST_AI_SEND_DATA_TO_LLM` env var | `export SKFORECAST_AI_SEND_DATA_TO_LLM=false` |
| Config file | `skforecast-ai config set llm.send_data_to_llm false` |

`--send-data-to-llm` follows the same precedence and is off by default. It mirrors the Python API, where it governs the `DataSentToLLMWarning` of `ask()` on results; the CLI `ask` command never sends observations, whatever its value. `--skills` is not resolved from config; pass it per call.

Providers: `openai:model`, `anthropic:model`, `google:model`, `groq:model`, `bedrock:model` (with `--base-url` as the AWS region, e.g. `--base-url eu-west-1`) and `ollama:model`. Any other prefix is treated as an OpenAI-compatible endpoint when combined with `--base-url`. See [Providers and credentials](llm-configuration.md#providers-and-credentials) for the environment variable each provider reads and the meaning of `--base-url`.

---

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (missing file, bad column, no LLM, unreachable URL, execution failures, a failed `check-llm`) |
| 2 | Invalid usage (unknown flag, missing required argument) |

---

## Shell completion

Typer provides built-in shell completion. To install it:

```bash
skforecast-ai --install-completion
```

This adds tab completion for commands, options, and arguments in your current shell (bash, zsh, fish, PowerShell). After installation, restart your shell or source the config file.
