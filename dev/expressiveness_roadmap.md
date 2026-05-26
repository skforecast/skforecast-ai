# Expressiveness Roadmap

> Making the stateless pipeline more powerful without adding sessions or persistence.

This document outlines concrete improvements to make `skforecast_ai` more expressive
through three pillars: **richer overrides**, **structured explanations**, and **flexible
export formats**. Each item references the specific files to modify and includes a
priority (P0 = do first, P2 = nice-to-have) and effort estimate (S/M/L).

---

## 1. Richer Overrides

The `refine_plan()` method currently accepts 5 kwargs (`forecaster`, `estimator`,
`estimator_kwargs`, `steps`, `interval`). Users can't control many decisions that the
pipeline makes automatically.

> **Design decision:** Overrides are plain `**kwargs` validated by an `allowed_keys`
> set inside `refine_plan()`. No `PlanOverrides` schema — it was dead code and added
> indirection without benefit. The kwargs approach is simpler, more Pythonic, and
> maps directly to CLI flags.

### 1.1 New override kwargs for `refine_plan()`

| Kwarg | Type | Purpose | Priority | Effort |
|-------|------|---------|----------|--------|
| `metric` | `str` | Override primary evaluation metric | P0 | S |
| `interval_method` | `Literal["bootstrapping", "conformal"]` | Choose interval method | P0 | S |
| `window_features` | `list[dict]` | Override rolling statistics (e.g. `[{"stat": "mean", "window_size": 7}]`) | P1 | M |
| `dropna_from_series` | `bool` | Force NaN handling strategy | P0 | S |
| `train_size` | `float \| int` | Train/test split ratio (0.0–1.0) or absolute size | P1 | M |
| `transformer_y` | `str` | Scaling for target (e.g. `"StandardScaler"`) | P1 | M |
| `transformer_exog` | `str` | Scaling for exog (e.g. `"StandardScaler"`) | P1 | M |
| `n_boot` | `int` | Number of bootstrap iterations for intervals | P2 | S |
| `encoding` | `Literal["ordinal", "ordinal_category", "onehot"]` | Multi-series encoding | P1 | S |

**Files:**
- `skforecast_ai/assistant.py` — expand `allowed_keys` set and plumb new kwargs
  through `generate_plan()`
- `skforecast_ai/schemas/plans.py` — delete `PlanOverrides` class (dead code)

### 1.2 New CLI flags

| Flag | Maps to kwarg | Command(s) | Priority | Effort |
|------|---------------|------------|----------|--------|
| `--lags` | `lags` | `plan`, `refine-plan`, `generate-code`, `forecast` | P0 | S |
| `--metric` | `metric` | `plan`, `refine-plan`, `generate-code`, `forecast` | P0 | S |
| `--interval-method` | `interval_method` | `plan`, `refine-plan`, `generate-code`, `forecast` | P0 | S |
| `--window-features` | `window_features` | `plan`, `refine-plan` | P1 | M |
| `--dropna` / `--no-dropna` | `dropna_from_series` | `plan`, `refine-plan`, `forecast` | P0 | S |
| `--train-size` | `train_size` | `generate-code`, `forecast` | P1 | S |
| `--encoding` | `encoding` | `plan`, `refine-plan` | P1 | S |

**File:** `skforecast_ai/cli.py` — add `click.option` decorators to relevant commands.

### 1.3 Override validation

Add validation logic inside `refine_plan()` (or a private helper `_validate_overrides`)
that raises `ValueError` for incompatible combinations:

- Foundation model + `lags` → error (foundation models don't use lags)
- Statistical model + `window_features` → error
- `interval_method="conformal"` + `steps=1` → warning (conformal needs multi-step)
- `dropna_from_series=False` + non-NaN-tolerant estimator → error

This keeps validation co-located with the override application logic rather than
splitting it into a separate module.

**File:** `skforecast_ai/assistant.py` — inside or called from `refine_plan()`.

---

## 2. Structured Explanations

Currently, explanations are a single text string. This is fine for CLI output but
unusable for UIs, notebooks, or programmatic consumption.

### 2.1 `PlanExplanation` schema

Replace the `explanation: str` field in `ForecastPlan` with a structured model:

```python
class PlanExplanation(BaseModel):
    summary: str                    # 1-2 sentence overview
    task_rationale: str             # Why this task type was selected
    forecaster_rationale: str       # Why this forecaster was chosen
    estimator_rationale: str        # Why this estimator was chosen
    lag_rationale: str              # Why these lags (PACF peaks, seasonality)
    metric_rationale: str           # Why this metric fits the problem
    preprocessing_rationale: str    # Why preprocessing steps are needed
    interval_rationale: str | None  # Why this interval method (if intervals used)
    warnings: list[str]             # Advisory notes
```

Backward compatibility: keep `ForecastPlan.explanation` as a computed property that
joins the structured fields into a single string.

**Priority:** P1 | **Effort:** M

**Files:**
- `skforecast_ai/schemas/plans.py` — add `PlanExplanation` model
- `skforecast_ai/recommendation/explanation.py` — refactor `build_plan_explanation()`
  to return `PlanExplanation` instead of `str`

### 2.2 Expose PACF analysis in lag rationale

The lag selection logic uses PACF internally but doesn't expose the results. Include:

- Top significant PACF lags (values + significance threshold)
- Seasonal period detected
- Whether lags were truncated due to data size

**Priority:** P1 | **Effort:** S

**File:** `skforecast_ai/recommendation/autoregressive.py` — return PACF metadata
alongside selected lags.

### 2.3 Preprocessing step justifications

Each `PreprocessingStep` already has a `reason` field, but it's generic. Make it
context-specific:

- `"sort_index"` → "Data is not sorted chronologically (row 45 precedes row 12)"
- `"asfreq"` → "Index has no frequency set; detected frequency is 'h' from gaps"
- `"reshape_long_to_dict"` → "Long-format detected (series_id column 'store_id' has 10 unique values)"

**Priority:** P2 | **Effort:** S

**File:** `skforecast_ai/recommendation/preprocessing.py` — enrich reason strings.

---

## 3. Export Formats

### 3.1 Result bundle (`--output-bundle`)

A single JSON file containing the full pipeline output:

```json
{
  "version": "0.1.0",
  "timestamp": "2026-05-26T14:30:00Z",
  "profile": { ... },
  "plan": { ... },
  "code": "import pandas as pd\n...",
  "results": {
    "predictions": [ ... ],
    "metrics": { "mae": 0.12, "mse": 0.03 }
  }
}
```

This is the canonical "save and share" artifact — no sessions needed.

**Priority:** P1 | **Effort:** M

**Files:**
- `skforecast_ai/schemas/results.py` — add `ResultBundle` schema
- `skforecast_ai/cli.py` — add `--output-bundle` flag to `forecast` command

### 3.2 Plan metadata in generated code

Embed the plan as a header comment in generated scripts:

```python
# Generated by skforecast-ai v0.1.0
# Forecaster: ForecasterRecursive | Estimator: LGBMRegressor
# Lags: [1, 2, 3, 7, 14] | Metric: mean_absolute_error
# Steps: 10 | Interval: [10, 90] (bootstrapping)
# ---
```

Users can see what plan produced the code without needing the JSON.

**Priority:** P0 | **Effort:** S

**File:** `skforecast_ai/generation/code_templates.py` — prepend metadata block.

### 3.3 Metrics CSV export

When `--output-predictions preds.csv` is used, also write `preds_metrics.csv`:

```csv
metric,value
mean_absolute_error,0.123
mean_squared_error,0.034
mean_absolute_scaled_error,0.89
```

Or add `--output-metrics metrics.csv` as a separate flag.

**Priority:** P1 | **Effort:** S

**Files:**
- `skforecast_ai/cli.py` — add `--output-metrics` flag
- `skforecast_ai/execution/runner.py` — write metrics file

### 3.4 HTML report (self-contained)

A single-file HTML report with:
- Data profile summary (shape, frequency, missing values)
- Plan decisions table
- Predictions plot (inline chart via base64 or simple SVG)
- Metrics table

Use Jinja2 template with inline CSS. No external dependencies at render time.

**Priority:** P2 | **Effort:** L

**Files:**
- New `skforecast_ai/export/html_report.py`
- New `skforecast_ai/export/templates/report.html` (Jinja2)
- `skforecast_ai/cli.py` — add `--output-report report.html` flag

---

## 4. Code Generation Flexibility

### 4.1 Configurable train/test split

Currently hardcoded at 80/20. Allow users to control via `train_size` override:

- `float` (0.0–1.0): fraction for training (e.g. `0.8`)
- `int`: absolute number of observations for training
- `str` (date): split at a specific timestamp

**Priority:** P1 | **Effort:** M

**Files:**
- `skforecast_ai/schemas/plans.py` — add `train_size` to `ForecastPlan`
- `skforecast_ai/generation/code_templates.py` — parameterize split logic

### 4.2 Optional backtesting section

Add a `include_backtesting: bool = True` field to `ForecastPlan`. When enabled,
generated code includes a `TimeSeriesFold` + `backtesting_forecaster` section after
the simple train/test evaluation.

**Priority:** P2 | **Effort:** M

**File:** `skforecast_ai/generation/code_templates.py` — conditional backtesting block.

### 4.3 Optional hyperparameter search section

Add a `include_hyperparameter_search: bool = False` field. When enabled, generated
code includes a `bayesian_search_forecaster` block with a sensible default
`search_space` derived from the estimator.

**Priority:** P2 | **Effort:** L

**File:** `skforecast_ai/generation/code_templates.py` — conditional search block.

---

## 5. CLI UX Improvements

### 5.1 `--dry-run` mode

For `forecast` command: run profile + plan + code generation but skip execution.
Print the plan and generated code without running it.

```bash
skforecast-ai forecast data.csv --target value --steps 10 --dry-run
```

**Priority:** P0 | **Effort:** S

**File:** `skforecast_ai/cli.py` — add flag, short-circuit before `run_forecast()`.

### 5.2 Verbosity levels

```bash
skforecast-ai forecast data.csv --target value --steps 10 -v      # Show plan summary
skforecast-ai forecast data.csv --target value --steps 10 -vv     # Show plan + code
skforecast-ai forecast data.csv --target value --steps 10 -vvv    # Show everything + timing
```

**Priority:** P1 | **Effort:** M

**File:** `skforecast_ai/cli.py` — add `-v` count option, pass to internal functions.

### 5.3 Environment variable for `send_data_to_llm`

Add `SKFORECAST_AI_SEND_DATA_TO_LLM` env var (consistent with existing
`SKFORECAST_AI_LLM` and `SKFORECAST_AI_BASE_URL`).

**Priority:** P0 | **Effort:** S

**File:** `skforecast_ai/config.py` — read from env in config resolution.

---

## Implementation Order

```
Phase 1 (P0 — Quick wins)
├── 0.0 Delete dead PlanOverrides class from schemas/plans.py
├── 1.1 refine_plan() kwargs: metric, interval_method, dropna_from_series
├── 1.2 CLI flags: --lags, --metric, --interval-method, --dropna
├── 3.2 Plan metadata in generated code
├── 5.1 --dry-run flag
└── 5.3 SKFORECAST_AI_SEND_DATA_TO_LLM env var

Phase 2 (P1 — Core expressiveness)
├── 1.1 refine_plan() kwargs: window_features, train_size, transformer_y/exog, encoding
├── 1.2 CLI flags: --window-features, --train-size, --encoding
├── 1.3 Override validation
├── 2.1 PlanExplanation structured schema
├── 2.2 PACF analysis in lag rationale
├── 3.1 Result bundle (--output-bundle)
├── 3.3 Metrics CSV export (--output-metrics)
├── 4.1 Configurable train/test split
└── 5.2 Verbosity levels

Phase 3 (P2 — Polish)
├── 2.3 Context-specific preprocessing reasons
├── 3.4 HTML report
├── 4.2 Optional backtesting section in code gen
└── 4.3 Optional hyperparameter search section
```

---

## Design Principles

1. **Stateless first** — Every improvement makes a single invocation more powerful.
   No sessions, no saved state, no "project" concept.
2. **Composable** — JSON output from one command pipes into the next. Each flag is
   independent.
3. **Progressive disclosure** — Defaults are good. Overrides are optional. Verbosity
   scales with `-v`.
4. **Deterministic by default** — LLM features are opt-in. The core pipeline
   produces the same output for the same input.
