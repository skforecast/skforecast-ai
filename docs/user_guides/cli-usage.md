# CLI reference

The `skforecast-ai` CLI runs the full forecasting pipeline from a terminal. Pass a CSV path or URL, specify your target column and horizon, and receive predictions, evaluation metrics, and the standalone Python script that produced them. No Python code required.

```bash
pip install "skforecast-ai[cli]"
```

Run `skforecast-ai --help` or `skforecast-ai <command> --help` for inline documentation on any command.

---

## Commands overview

| Command | Description |
|---------|-------------|
| `profile` | Inspect dataset and recommend forecaster/estimator |
| `plan` | Generate a detailed forecasting plan |
| `refine-plan` | Refine an existing plan by overriding specific fields |
| `forecast-code` | Generate a self-contained Python forecasting script |
| `backtest-code` | Generate a self-contained Python backtesting script |
| `forecast` | Run end-to-end forecasting (profile → plan → code → execute) |
| `backtest` | Run backtesting evaluation (profile → plan → CV → backtest) |
| `ask` | Ask forecasting questions using an LLM |
| `config show` | Display current configuration |
| `config set` | Set a configuration value |
| `config path` | Print config file location |

---

## Forecast examples

The examples below cover the most common dataset shapes. Every command works the same way regardless of data source: swap in your own file path or URL.

### Monthly series with exogenous variables

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Profile
skforecast-ai profile "$URL" --target y --date-column fecha

# Plan
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24

# Plan with intervals
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --interval "10,90"

# Generate code
skforecast-ai forecast-code "$URL" --target y --date-column fecha --steps 24 --output forecast.py

# Generate code with intervals
skforecast-ai forecast-code "$URL" --target y --date-column fecha --steps 24 --interval "10,90" --output forecast.py

# Forecast (end-to-end)
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12

# Forecast with intervals + save predictions
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 --interval "10,90" --output-predictions preds.csv

# Forecast with JSON output
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 --format json > preds.json

# Override forecaster/estimator
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 --forecaster ForecasterDirect --estimator Ridge
```

### Hourly series (high frequency)

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/bike_sharing_dataset_clean.csv"

# Profile
skforecast-ai profile "$URL" --target users --date-column date_time

# Plan
skforecast-ai plan "$URL" --target users --date-column date_time --steps 24

# Generate code
skforecast-ai forecast-code "$URL" --target users --date-column date_time --steps 24 --output bike_forecast.py

# Forecast
skforecast-ai forecast "$URL" --target users --date-column date_time --steps 24

# Forecast with intervals
skforecast-ai forecast "$URL" --target users --date-column date_time --steps 24 --interval "10,90"
```

### Multi-series, wide format

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/simulated_items_sales.csv"

# Profile
skforecast-ai profile "$URL" --target "item_1,item_2,item_3" --date-column date

# Plan
skforecast-ai plan "$URL" --target "item_1,item_2,item_3" --date-column date --steps 30

# Generate code
skforecast-ai forecast-code "$URL" --target "item_1,item_2,item_3" --date-column date --steps 30 --output multi_forecast.py

# Forecast
skforecast-ai forecast "$URL" --target "item_1,item_2,item_3" --date-column date --steps 30 --output-predictions preds_multi.csv
```

### Multi-series, long format (local file)

```bash
# Profile
skforecast-ai profile sales.csv --target revenue --date-column date --series-id-column store_id

# Forecast
skforecast-ai forecast sales.csv --target revenue --date-column date --series-id-column store_id --steps 30 --output-predictions preds_sales.csv
```

### Simple daily series

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/visitas_por_dia_web_cienciadedatos.csv"

# Profile
skforecast-ai profile "$URL" --target Usuarios --date-column date

# Forecast
skforecast-ai forecast "$URL" --target Usuarios --date-column date --steps 14
```

---

## Backtest code

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

## Backtest

Run backtesting evaluation with cross-validation. Chains profile → plan → create_cv → backtest automatically. See [Backtesting & validation](backtesting.md) for a conceptual overview and the Python API equivalent.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Basic backtest (uses smart deterministic CV defaults)
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

## Refine plan

Iteratively adjust an existing plan without re-profiling the dataset: override the horizon, switch forecasters, change estimator hyperparameters, or add prediction intervals.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Save a plan, then refine it
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --format json > plan.json

# Override forecast horizon
skforecast-ai refine-plan --from-plan plan.json --steps 12 --format json > plan_12.json

# Switch forecaster
skforecast-ai refine-plan --from-plan plan.json --forecaster ForecasterDirect --format json

# Override estimator hyperparameters
skforecast-ai refine-plan --from-plan plan.json --estimator-kwargs '{"n_estimators": 500}' --format json

# Add prediction intervals
skforecast-ai refine-plan --from-plan plan.json --interval "10,90" --format json

# Pipe: plan → refine → forecast-code
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --format json -q | \
  skforecast-ai refine-plan --from-plan - --steps 12 --forecaster ForecasterDirect --format json -q | \
  skforecast-ai forecast-code --from-plan - --output forecast.py -q
```

---

## Plan save and load

Save a plan to JSON and replay it later. This separates the modeling decision from execution: useful for auditing, scheduling, or running the same plan against updated data.

!!! note
    When `--from-plan` is used, `DATA` and `--target`/`--steps` are optional for `forecast-code` (values are taken from the bundle). `DATA` is still required for `forecast`, which needs actual data to execute.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Save a plan for later replay
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --format json > plan.json

# Generate code from a saved plan (no re-profiling needed)
skforecast-ai forecast-code --from-plan plan.json --output forecast.py

# Execute a saved plan against data
skforecast-ai forecast "$URL" --from-plan plan.json

# Override interval at execution time
skforecast-ai forecast "$URL" --from-plan plan.json --interval "10,90"
```

---

## Ask

!!! note "Requires LLM extras"
    `ask` requires an API key and the LLM extras: `pip install "skforecast-ai[llm]"`. See [Using the AI assistant](using-the-ai-assistant.md) for supported providers, API key setup, and local model options.

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

# Custom endpoint (Ollama)
skforecast-ai ask "How to handle missing values?" \
  --llm openai:llama3 --base-url http://localhost:11434/v1

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
| `--exog-future` | | Future exog CSV | `forecast` |

### Forecast configuration

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--steps` | | Forecast horizon | `plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest`, `ask` |
| `--forecaster` | | Override forecaster class | `plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest` |
| `--estimator` | | Override estimator class | `plan`, `forecast-code`, `backtest-code`, `forecast`, `backtest` |
| `--interval` | | Interval percentiles, e.g. `"10,90"` | `plan`, `forecast-code`, `backtest-code`, `forecast` |

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
| `--from-plan` | | Load plan bundle JSON (file or `-` for stdin) | `refine-plan`, `forecast-code`, `backtest-code`, `forecast` |

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
| `--output` | `-o` | Write to file | `profile`, `plan`, `forecast-code`, `backtest-code` |
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

Providers: `openai:model`, `anthropic:model`, `google:model`, `groq:model`, `ollama:model`.

---

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (missing file, bad column, no LLM, unreachable URL, execution failures) |

---

## Shell completion

Typer provides built-in shell completion. To install it:

```bash
skforecast-ai --install-completion
```

This adds tab completion for commands, options, and arguments in your current shell (bash, zsh, fish, PowerShell). After installation, restart your shell or source the config file.
