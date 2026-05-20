# CLI Usage

## Setup

```bash
conda activate skforecast_ai_py13
pip install -e ".[cli,dev]"
```

## Commands Overview

| Command | Description |
|---------|-------------|
| `profile` | Inspect dataset and recommend forecaster/estimator |
| `plan` | Generate a detailed forecasting plan |
| `generate-code` | Generate a self-contained Python script |
| `forecast` | Run end-to-end forecasting (profile → plan → code → execute) |
| `ask` | Ask forecasting questions using an LLM |

## Full Examples by Dataset

### h2o_exog — Monthly single series with exogenous variables

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# Profile
skforecast-ai profile "$URL" --target y --date-column fecha

# Plan
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24

# Plan with intervals
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --interval "10,90"

# Generate code
skforecast-ai generate-code "$URL" --target y --date-column fecha --steps 24 --output forecast.py

# Generate code with intervals
skforecast-ai generate-code "$URL" --target y --date-column fecha --steps 24 --interval "10,90" --output forecast.py

# Forecast (end-to-end)
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12

# Forecast with intervals + save predictions
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 --interval "10,90" --output-predictions preds.csv

# Forecast with JSON output
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 --format json

# Override forecaster/estimator
skforecast-ai forecast "$URL" --target y --date-column fecha --steps 12 --forecaster ForecasterDirect --estimator Ridge
```

### bike_sharing — Hourly single series with 10 exogenous features

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/bike_sharing_dataset_clean.csv"

# Profile
skforecast-ai profile "$URL" --target users --date-column date_time

# Plan
skforecast-ai plan "$URL" --target users --date-column date_time --steps 24

# Generate code
skforecast-ai generate-code "$URL" --target users --date-column date_time --steps 24 --output bike_forecast.py

# Forecast
skforecast-ai forecast "$URL" --target users --date-column date_time --steps 24

# Forecast with intervals
skforecast-ai forecast "$URL" --target users --date-column date_time --steps 24 --interval "10,90"
```

### items_sales — Daily multi-series (wide format, 3 series)

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/simulated_items_sales.csv"

# Profile
skforecast-ai profile "$URL" --target "item_1,item_2,item_3" --date-column date

# Plan
skforecast-ai plan "$URL" --target "item_1,item_2,item_3" --date-column date --steps 30

# Generate code
skforecast-ai generate-code "$URL" --target "item_1,item_2,item_3" --date-column date --steps 30 --output multi_forecast.py

# Forecast
skforecast-ai forecast "$URL" --target "item_1,item_2,item_3" --date-column date --steps 30
```

### Multi-series long format (local file)

```bash
# Profile
skforecast-ai profile sales.csv --target revenue --date-column date --series-id store_id

# Forecast
skforecast-ai forecast sales.csv --target revenue --date-column date --series-id store_id --steps 30
```

### website_visits — Daily single series, no exogenous

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/visitas_por_dia_web_cienciadedatos.csv"

# Profile
skforecast-ai profile "$URL" --target Usuarios --date-column date

# Forecast
skforecast-ai forecast "$URL" --target Usuarios --date-column date --steps 14
```

## Ask Command (requires LLM)

```bash
# Set LLM (or use --llm flag on each call)
export SKFORECAST_AI_LLM="openai:gpt-4o-mini"

# Q&A mode — general question
skforecast-ai ask "How do I choose between recursive and direct strategies?"

# Explain mode — with data context
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

## Flags Reference

| Flag | Short | Description | Commands |
|------|-------|-------------|----------|
| `--target` | `-t` | Target column(s), comma-separated | all |
| `--date-column` | `-d` | Date/timestamp column | all |
| `--series-id` | `-s` | Series identifier (long-format) | all |
| `--steps` | | Forecast horizon | `plan`, `generate-code`, `forecast`, `ask` |
| `--forecaster` | | Override forecaster class | `plan`, `generate-code`, `forecast` |
| `--estimator` | | Override estimator class | `plan`, `generate-code`, `forecast` |
| `--interval` | | Interval percentiles, e.g. `"10,90"` | `plan`, `generate-code`, `forecast` |
| `--format` | | Output format | all |
| `--output` | `-o` | Write to file | `profile`, `plan`, `generate-code` |
| `--quiet` | `-q` | Suppress spinners | all |
| `--llm` | | LLM provider | `ask` |
| `--base-url` | | Custom LLM endpoint | `ask` |
| `--send-data-to-llm` | | Allow raw data to LLM | `ask` |
| `--skills` | | Skill names to include | `ask` |
| `--exog-future` | | Future exog CSV | `forecast` |
| `--output-predictions` | | Save predictions CSV | `forecast` |
| `--output-code` | | Save generated script | `forecast` |

## LLM Configuration

| Method | Example |
|--------|---------|
| `--llm` flag | `--llm openai:gpt-4o-mini` |
| `SKFORECAST_AI_LLM` env var | `export SKFORECAST_AI_LLM="openai:gpt-4o-mini"` |
| `--base-url` flag | `--base-url http://localhost:11434/v1` |
| `SKFORECAST_AI_BASE_URL` env var | `export SKFORECAST_AI_BASE_URL="http://localhost:11434/v1"` |

Providers: `openai:model`, `anthropic:model`, `google:model`.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | User error (missing file, bad column, no LLM, unreachable URL) |
| 2 | Runtime error |
