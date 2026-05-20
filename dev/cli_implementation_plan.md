# CLI Implementation Plan — `skforecast-ai`

## Development Environment

```bash
conda activate skforecast_ai_py13
pip install -e ".[cli,dev]"
```

---

## 1. State of the Art — CLI Design in AI/ML Packages

### Reference Tools

| Tool | Framework | Key Patterns to Adopt |
|------|-----------|----------------------|
| [`gh copilot`](https://docs.github.com/en/copilot/using-github-copilot/using-github-copilot-in-the-command-line) (GitHub) | Cobra (Go) | Context-aware suggestions, `gh copilot explain` / `gh copilot suggest` split (explain vs act), shell integration, graceful auth flow, streaming responses with spinners |
| [`llm`](https://github.com/simonw/llm) (Simon Willison) | Click | Plugin system, `--format json`, config via `llm keys set`, piping between commands, streaming LLM output |
| [`aider`](https://github.com/paul-gauthier/aider) | argparse | Interactive mode as default, config files (`.aider.conf.yml`), env vars for secrets, `--no-stream` toggle |
| [`openai` CLI](https://github.com/openai/openai-python) | Click | Subcommand hierarchy (`openai api chat.completions.create`), `--output` file, structured JSON responses |
| [`instructor`](https://github.com/jxnl/instructor) | Typer | Structured output validation, retry logic, Pydantic model serialization to JSON |
| [`sktime`](https://github.com/sktime/sktime) | — | No CLI — gap in the ecosystem; opportunity for skforecast-ai |
| [`nixtla/mlforecast`](https://github.com/Nixtla/mlforecast) | — | No CLI either — confirms this is a differentiator |

### Best Practices Summary

1. **Deterministic-first, LLM-optional** — Core commands must work without any LLM configured. The `ask` command is the only one requiring an LLM.
2. **Structured output** — Default to human-readable rich tables; `--format json` for machine consumption and piping.
3. **File-in, file-out** — Accept CSV/Parquet paths as input; `--output` flag saves results to file.
4. **Progressive disclosure** — Auto-detect everything by default; explicit flags (`--forecaster`, `--estimator`, `--interval`) for power users.
5. **No secrets on command line** — API keys via env vars (`OPENAI_API_KEY`, `OLLAMA_HOST`) or a config command, never as positional args.
6. **Idempotent and reproducible** — Same input → same output. Plans serializable as JSON for auditing and replay.
7. **Composable via pipes** — JSON output of one command can be piped as input to the next (`profile → plan → generate-code`).
8. **Rich terminal UX** — Progress spinners for long operations, colored output, clear error messages with suggestions.
9. **Fail fast with helpful errors** — Validate inputs before expensive operations; suggest fixes in error messages.

### Why Typer

Already chosen in `pyproject.toml`. Good fit because:
- Built on Click, adds type hints and auto-completion
- `rich` integration for tables and panels (already a dependency via `typer[all]`)
- Auto-generated `--help` from docstrings
- `typer.testing.CliRunner` for testing (already imported in `tests/test_cli.py`)

---

## 2. Phased Implementation Plan

### Phase 1 — Core Deterministic Commands

**Goal:** Wrap the three main deterministic methods as CLI subcommands. No LLM required.

#### Commands

```bash
# Profile a dataset
skforecast-ai profile data.csv --target sales --date-column date
skforecast-ai profile data.csv --target "sales,revenue" --date-column date --series-id store_id

# Generate a plan
skforecast-ai plan data.csv --target sales --steps 24
skforecast-ai plan data.csv --target sales --steps 24 --forecaster ForecasterRecursiveMultiSeries

# Generate code
skforecast-ai generate-code data.csv --target sales --steps 24 --output forecast_script.py
```

#### Implementation Details

| Command | Wraps | Input | Output (default) | Output (`--format json`) |
|---------|-------|-------|-----------------|--------------------------|
| `profile` | `assistant.profile()` | CSV path + flags | Rich table (forecaster, estimator, candidates, data summary) | `ForecastingProfile.model_dump_json()` |
| `plan` | `assistant.profile()` + `assistant.generate_plan()` | CSV path + flags | Rich panel (plan explanation + key params) | `ForecastPlan.model_dump_json()` |
| `generate-code` | `assistant.generate_code()` | CSV path + flags | Python code to stdout (or file via `--output`) | `CodeGenerationResult` JSON |

#### Common Flags

```
DATA (positional)        Path to CSV or Parquet file
--target, -t             Target column name(s), comma-separated for multi-series
--date-column, -d        Date/timestamp column name
--series-id, -s          Series identifier column (long-format multi-series)
--steps                  Forecast horizon (required for plan/generate-code/forecast)
--forecaster             Override recommended forecaster class
--estimator              Override recommended estimator class
--interval               Prediction interval bounds, e.g. "10,90"
--format                 Output format: "table" (default) | "json"
--output, -o             Write output to file instead of stdout
--quiet, -q              Suppress non-essential output (spinners, banners)
```

#### Files to Create/Modify

- `skforecast_ai/cli.py` — Implement `profile`, `plan`, `generate-code` commands
- `tests/test_cli.py` — Tests for each command (success, missing args, bad file path, JSON output)

#### Acceptance Criteria

- [x] `skforecast-ai profile data.csv --target y` prints a formatted table
- [x] `skforecast-ai plan data.csv --target y --steps 10 --format json` outputs valid JSON parseable as `ForecastPlan`
- [x] `skforecast-ai generate-code data.csv --target y --steps 10 --output script.py` writes a runnable Python file
- [x] All commands fail gracefully with helpful errors for missing files, bad column names, etc.

---

### Phase 2 — Execution Command

**Goal:** Run end-to-end forecasting from CLI, outputting predictions.

#### Command

```bash
# Basic forecast
skforecast-ai forecast data.csv --target sales --steps 24

# With options
skforecast-ai forecast data.csv --target sales --steps 24 \
  --interval "10,90" \
  --output predictions.csv \
  --estimator LGBMRegressor
```

#### Implementation Details

| Command | Wraps | Output (default) | Output (`--format json`) |
|---------|-------|-----------------|--------------------------|
| `forecast` | `assistant.forecast()` | Rich table (metrics) + predictions summary | `ForecastResult` JSON (metrics + predictions as records) |

#### Additional Flags

```
--output-predictions     Path to save predictions DataFrame as CSV
--output-code            Path to save the generated script
--exog-future            Path to CSV with future exogenous variables
```

#### Acceptance Criteria

- [x] `skforecast-ai forecast data.csv --target y --steps 10` prints metrics and prediction summary
- [x] `--output predictions.csv` saves predictions to file
- [x] `--output-code script.py` saves the exact code that was executed
- [x] `--interval "10,90"` includes prediction intervals in output
- [x] Error handling for execution failures (bad data, incompatible estimator)

---

### Phase 3 — LLM-Powered Command

**Goal:** Enable `ask` subcommand for natural-language interaction.

#### Command

```bash
# General Q&A (no data needed)
skforecast-ai ask "How do I handle missing values in multi-series forecasting?"

# Explain a dataset
skforecast-ai ask "What's the best approach for this data?" --data data.csv --target sales

# Explain forecast results
skforecast-ai ask "Why is the MAE so high?" --data data.csv --target sales --steps 24
```

#### Implementation Details

| Command | Wraps | Requirements |
|---------|-------|-------------|
| `ask` | `assistant.ask()` | LLM must be configured (env var or config) |

#### LLM Configuration

```bash
# Via environment variables (preferred)
export SKFORECAST_AI_LLM="openai:gpt-4o-mini"
export OPENAI_API_KEY="sk-..."

# Or for Ollama
export SKFORECAST_AI_LLM="ollama:llama3"
export SKFORECAST_AI_BASE_URL="http://localhost:11434"
```

#### Additional Flags

```
--llm                    Override LLM provider (e.g. "openai:gpt-4o-mini")
--base-url               Custom LLM endpoint
--send-data-to-llm       Allow sending raw data to LLM (default: false)
--no-stream              Disable streaming output
--skills                 Comma-separated skill names to include
```

#### Acceptance Criteria

- [x] `skforecast-ai ask "question"` streams a response to stdout
- [x] Works with both OpenAI and Ollama providers
- [x] Clear error message when no LLM is configured
- [x] `--data` triggers profiling before the LLM call
- [x] `--send-data-to-llm` is opt-in, not default

---

### Phase 4 — Configuration & UX Polish

**Goal:** Persistent configuration, shell completion, polished UX.

#### Commands

```bash
# Config management
skforecast-ai config show
skforecast-ai config set llm "ollama:llama3"
skforecast-ai config set base-url "http://localhost:11434"

# Shell completion
skforecast-ai --install-completion
```

#### Features

- **Config file** at `~/.config/skforecast-ai/config.toml` (or `$XDG_CONFIG_HOME`)
- **Precedence**: CLI flags > env vars > config file > defaults
- **Shell completion** for bash/zsh/fish (built into Typer)
- **Version command**: `skforecast-ai --version`
- **Verbose/debug mode**: `--verbose` flag for detailed logging

#### Config File Format

```toml
[llm]
provider = "ollama:llama3"
base_url = "http://localhost:11434"
send_data_to_llm = false

[output]
format = "table"  # "table" or "json"
```

#### Acceptance Criteria

- [x] `skforecast-ai config set llm "openai:gpt-4o"` persists to config file
- [x] `skforecast-ai config show` displays current configuration
- [x] Config values are used as defaults for `--llm`, `--base-url`, `--format`
- [x] Shell completion works for command names and flags

---

### Phase 5 — Advanced Features

**Goal:** Pipeline composition, plan save/load, interactive mode.

#### Features

##### Plan Save/Load (Reproducibility)

```bash
# Save a plan for later replay
skforecast-ai plan data.csv --target sales --steps 24 --format json > plan.json

# Generate code from a saved plan
skforecast-ai generate-code --from-plan plan.json --data data.csv

# Execute a saved plan
skforecast-ai forecast --from-plan plan.json --data data.csv
```

##### Pipe Composition

```bash
# Chain commands via JSON piping
skforecast-ai profile data.csv --target sales --format json | \
  skforecast-ai plan --from-profile - --steps 24 --format json | \
  skforecast-ai generate-code --from-plan - --output script.py
```

##### Interactive Mode

```bash
# Start interactive session
skforecast-ai interactive data.csv --target sales

# Inside session:
# > profile
# > plan --steps 24
# > refine --estimator XGBRegressor
# > generate-code
# > forecast
# > ask "Why did you choose these lags?"
```

#### Acceptance Criteria

- [x] `--from-plan plan.json` accepts a previously saved plan JSON
- [x] `--from-profile -` reads JSON from stdin (pipe support)
- [x] Interactive mode maintains session state (profile, plan, results)
- [x] `refine` command in interactive mode wraps `assistant.refine_plan()`

---

## 3. Testing Strategy

### Framework

- **Test runner:** pytest with `typer.testing.CliRunner` (already scaffolded in `tests/test_cli.py`)
- **Fixtures:** Reuse CSV fixtures from `tests/fixtures_*.py`
- **Environment:** `conda activate skforecast_ai_py13`

### Test Categories

| Category | Scope | Example |
|----------|-------|---------|
| Unit | Each command in isolation | `test_profile_basic`, `test_plan_json_output` |
| Integration | Command chains | `test_profile_then_plan_pipe` |
| Error handling | Bad inputs, missing files | `test_missing_file_error`, `test_invalid_target` |
| Output format | Table vs JSON correctness | `test_json_output_valid_schema` |
| LLM (mocked) | `ask` command with mocked LLM | `test_ask_no_llm_configured_error` |

### Running Tests

```bash
conda activate skforecast_ai_py13

# All CLI tests
pytest tests/test_cli.py -vv

# Specific phase
pytest tests/test_cli.py -k "profile or plan or generate_code" -vv

# With coverage
pytest tests/test_cli.py --cov=skforecast_ai.cli --cov-report=term-missing
```

### Test Structure

```python
# tests/test_cli.py
from typer.testing import CliRunner
from skforecast_ai.cli import app

runner = CliRunner()

class TestProfile:
    def test_profile_basic(self, tmp_path):
        """Profile command prints table output."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("date,sales\n2020-01-01,100\n2020-01-02,110\n...")
        result = runner.invoke(app, ["profile", str(csv_file), "--target", "sales"])
        assert result.exit_code == 0
        assert "ForecasterRecursive" in result.output

    def test_profile_json_format(self, tmp_path):
        """Profile --format json outputs valid JSON."""
        ...
        result = runner.invoke(app, ["profile", str(csv_file), "--target", "sales", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "forecaster" in data

    def test_profile_missing_file(self):
        """Profile with non-existent file shows helpful error."""
        result = runner.invoke(app, ["profile", "nonexistent.csv", "--target", "y"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "does not exist" in result.output.lower()
```

---

## 4. Implementation Order

```
Phase 1 (Core)          ← START HERE
├── profile command
├── plan command
├── generate-code command
├── Common flags & error handling
└── Tests for Phase 1

Phase 2 (Execution)
├── forecast command
├── --output-predictions / --output-code flags
└── Tests for Phase 2

Phase 3 (LLM)
├── ask command
├── LLM env var detection
├── Streaming output
└── Tests for Phase 3 (mocked LLM)

Phase 4 (Config & Polish)
├── config subcommand
├── Config file read/write
├── Shell completion
└── Tests for Phase 4

Phase 5 (Advanced)
├── --from-plan / --from-profile flags
├── Stdin pipe support
├── Interactive mode (stretch goal)
└── Tests for Phase 5
```

---

## 5. Dependencies

Already declared in `pyproject.toml`:

```toml
[project.optional-dependencies]
cli = ["typer[all]"]
```

`typer[all]` includes `rich`, `shellingham`, and `click` — sufficient for all phases.

No additional dependencies needed for Phases 1–4. Phase 5 (interactive mode) may benefit from `prompt_toolkit` if readline-level UX is desired.
