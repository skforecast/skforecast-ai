# CLI Module Evaluation — `skforecast_ai/cli.py`

> Evaluation date: 2025-05-21  
> Environment: `skforecast_ai_py13` (Python 3.13.13)  
> Version evaluated: `skforecast-ai 0.1.0`

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Overall rating** | **B+** (solid, production-ready foundation with notable gaps) |
| **Test coverage** | 93% (309 stmts, 23 missed) |
| **Lint violations** | 0 (ruff clean) |
| **Tests** | 60/60 passing |
| **LOC** | 646 |
| **Commands** | 6 + 3 config subcommands |

**Key strengths:**
- Clean architecture — well-separated concerns (commands → assistant → execution)
- Excellent pipe composition support (JSON stdin/stdout chaining)
- Comprehensive error handling via context manager pattern
- Config resolution chain (flag > env > config > default) is intuitive
- All commands support `--format json` and `--quiet` for scripting

**Key weaknesses:**
- No `--estimator-kwargs` flag (assistant supports it, CLI doesn't expose it)
- Missing env var for privacy-critical `send_data_to_llm` setting
- No early LLM validation in `ask` command
- Interval bounds not validated (reversed bounds accepted silently)
- ~~No `refine-plan` command (API gap)~~ (FIXED)

---

## Architecture Review

### Module Structure

```
cli.py (646 LOC)
├── Entry point: app = typer.Typer()
├── Config subcommand: config_app (show, set, path)
├── Helpers (private):
│   ├── _version_callback()       # Eager --version flag
│   ├── _resolve()                # Flag > env > config > None
│   ├── _read_json_input()        # File or stdin ('-')
│   ├── _parse_target()           # Comma-separated targets
│   ├── _parse_interval()         # "10,90" → [10, 90]
│   ├── _write_output()           # File or stdout
│   ├── _error_handler()          # Context manager for user-friendly errors
│   ├── _render_profile_table()   # Rich table output
│   ├── _render_plan_panel()      # Rich panel output
│   ├── _render_forecast_results()# Rich metrics table
│   └── _forecast_result_to_json()# DataFrame serialization
└── Commands:
    ├── profile()       → assistant.profile()
    ├── plan()          → assistant.generate_plan()
    ├── generate_code() → assistant.generate_code() / generate_code_from_plan()
    ├── forecast()      → assistant.forecast()
    └── ask()           → assistant.ask()
```

### Command Dispatch Pattern

Each command follows the same pattern:
1. Parse/validate CLI inputs
2. Resolve config (flag > env > config file)
3. Instantiate `ForecastingAssistant`
4. Call assistant method inside `_error_handler()` context
5. Render output (table/json/code)

This is clean and consistent. The `_error_handler()` context manager centralizes error translation, mapping internal exceptions to user-friendly exit codes.

### Config Resolution Chain

```
CLI flag → Environment variable → Config file (~/.config/skforecast-ai/config.toml) → None
```

Implemented via `_resolve(flag, env_var, config_key)`. Only applied to `ask` command's `--llm` and `--base-url` options.

---

## Code Quality

### Convention Adherence

| Convention | Status | Notes |
|-----------|--------|-------|
| Ruff clean | ✅ | Zero violations |
| Double quotes | ✅ | Consistent throughout |
| Relative imports | ✅ | `from .assistant import ...` |
| Type hints | ✅ | All function signatures annotated via `Annotated[...]` |
| PEP 8 (88 chars) | ✅ | No line length violations |
| NumPy-style docstrings | ⚠️ | Only basic one-liners; helpers lack full docstrings |

### DRY Analysis

**Good DRY compliance:**
- `_error_handler()` centralizes all exception→exit-code mapping
- `_resolve()` avoids repeating the flag/env/config precedence logic
- `_parse_target()` and `_parse_interval()` are reused across commands

**DRY violations (minor):**
- The `if quiet: ... else: with console.status(...)` pattern is repeated 9 times across commands. Could be factored into a helper like `_with_spinner(label, quiet, fn, **kwargs)`, but the current approach is explicit and readable — not a priority fix.

### Complexity

McCabe complexity is low. The most complex function is `forecast()` at ~50 LOC within the handler, mostly due to the `from_plan` vs fresh-profile branching. This is acceptable.

---

## Test Coverage

### Quantitative Results

```
Name                   Stmts   Miss  Cover   Missing
----------------------------------------------------
skforecast_ai/cli.py     309     23    93%   85, 155, 185-189, 248-251, 340-341,
                                             352-353, 460-462, 508-512, 530-531,
                                             568, 639, 641, 643
```

### Uncovered Lines Analysis

| Lines | Code Path | Risk |
|-------|-----------|------|
| 85 | `config_show` — iterating config table rows | Low (display logic) |
| 155 | `_parse_interval` — `BadParameter` for non-2 parts | Low (error path) |
| 185-189 | `_error_handler` — `LLMRequiredError` branch | Medium (important error path) |
| 248-251 | `_render_plan_panel` — preprocessing steps rendering | Low (display) |
| 340-341 | `plan` — `from_profile` without quiet | Low (spinner variant) |
| 352-353 | `plan` — `generate_plan` without quiet | Low (spinner variant) |
| 460-462 | `_render_forecast_results` — predictions ≤10 rows branch | Low (display) |
| 508-512 | `forecast` — `from_plan` without quiet | Low (spinner variant) |
| 530-531 | `forecast` — non-quiet forecast | Low (spinner variant) |
| 568 | `forecast` — `exog_future` file not found | Medium (error path) |
| 639, 641, 643 | `ask` — profile/plan/code in JSON output | Low (optional fields) |

### Qualitative Gaps

| Gap | Risk Level | Recommendation |
|-----|-----------|----------------|
| `LLMRequiredError` path not tested via CLI integration | Medium | Add test: invoke `ask` without LLM configured |
| `ForecastExecutionError` path untested | Medium | Add test with a failing script |
| `--exog-future` with missing file not tested | Low | Add test for nonexistent exog CSV |
| Interval with wrong format (e.g., "10,20,30") | Low | Add test for 3-part interval string |
| Large JSON on stdin (stress test) | Low | Not critical for unit tests |
| Non-quiet paths (spinners) | Low | Cosmetic-only; skipping is acceptable |

### Test Structure Notes

Tests use class-based grouping (`TestProfile`, `TestPlan`, etc.) which contradicts the repo convention of module-level functions. This is a pre-existing pattern in the CLI tests — not a blocking issue but worth harmonizing in a future refactor.

---

## Security Audit

### Assessment: LOW RISK (for a local CLI tool)

| Concern | Status | Impact | Recommendation |
|---------|--------|--------|----------------|
| **Config file permissions** | ⚠️ Default umask | API keys world-readable on shared systems | Create config with `mode=0o600` |
| **Stdin size limit** | ⚠️ None | OOM on malicious pipe input | Add `MAX_STDIN_BYTES` check (e.g., 50MB) |
| **Path traversal** | ✅ Safe | `.is_file()` used before reads | — |
| **Code execution** | ✅ Safe | `forecast` runs generated code via controlled `exec_runner` | — |
| **LLM key exposure** | ✅ Safe | Keys in env vars, not in CLI output | — |
| **eval/exec** | ✅ Safe | No direct eval/exec in CLI module | — |
| **Deserialization** | ✅ Safe | `json.loads()` + Pydantic validation | — |

### Details

**Config file permissions (Medium):**  
`config.py` creates config with `open(CONFIG_FILE, "w")` using the system default umask. On multi-user systems, this means `~/.config/skforecast-ai/config.toml` (which may contain `llm.provider` with API keys) is world-readable. Fix: `os.open(str(CONFIG_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)`.

**Stdin size limit (Low):**  
`_read_json_input("-")` calls `sys.stdin.read()` without any size cap. In a pipe scenario, a malicious upstream process could exhaust memory. Fix: read in chunks with a size limit (e.g., 50MB) and raise `ValueError` if exceeded. Real-world risk is minimal since this is a local CLI tool.

---

## UX & Ergonomics

### Strengths

1. **Consistent `--format` flag** — All commands support `table`/`json` output
2. **Pipe-friendly** — JSON output + `--from-profile`/`--from-plan` + stdin (`-`) support
3. **Short flags** — `-t`, `-d`, `-s`, `-o`, `-q` for common options
4. **Helpful error messages** — `_error_handler()` translates exceptions to human-readable text with tips
5. **Progress feedback** — `console.status()` spinners when not in quiet mode
6. **Exit codes** — 0 (success), 1 (user error) are consistent and documented

### Issues

| Issue | Impact | Fix |
|-------|--------|-----|
| No `--help` examples in command docstrings | Users can't discover usage patterns from `--help` | Add `rich_help_panel` or epilog examples |
| `--format` accepts any string (no validation) | Silently produces no output if typo ("jsn") | Use `Literal["table", "json"]` or Typer choice |
| No shell completion installation instructions | Typer supports completion but users don't know | Add `skforecast-ai --install-completion` note in docs |
| `--interval` error says "e.g. '10,90'" but doesn't validate bounds | Confusing output if `90,10` is passed | Add `lower < upper` check |
| `ask` error for missing LLM appears after spinner delay | User waits for nothing | Validate LLM before spinner |

### Output Formatting

- **Table mode**: Rich tables with borders, panels with explanations — professional look
- **JSON mode**: Pretty-printed (indent=2), consistent schema per command
- **Code mode**: Syntax-highlighted with Monokai theme

---

## API Completeness

### Assistant Methods vs CLI Commands

| Assistant Method | CLI Command | Status |
|-----------------|-------------|--------|
| `profile()` | `skforecast-ai profile` | ✅ Complete |
| `generate_plan()` | `skforecast-ai plan` | ⚠️ Missing `estimator_kwargs` |
| `refine_plan()` | `skforecast-ai refine-plan` | ✅ Complete |
| `generate_code_from_plan()` | `skforecast-ai generate-code --from-plan` | ✅ Complete |
| `generate_code()` | `skforecast-ai generate-code` | ✅ Complete |
| `forecast()` | `skforecast-ai forecast` | ⚠️ Missing `estimator_kwargs` |
| `ask()` | `skforecast-ai ask` | ✅ Complete |

### Parameter Gaps

| Parameter | Assistant | CLI | Impact |
|-----------|-----------|-----|--------|
| `estimator_kwargs` (dict) | ✅ `generate_plan()`, `forecast()` | ❌ Not exposed | Can't tune hyperparams from CLI |
| `send_data_to_llm` (env var) | ✅ Constructor param | ⚠️ Flag only, no env var | Scripts can't set privacy via env |
| `suppress_warnings` | ✅ Some methods | ❌ Not exposed | No way to suppress skforecast warnings |

---

## Issues Found

### 🔴 Critical

#### C1: No `--estimator-kwargs` flag (FIXED)

**Location:** `plan` and `forecast` commands  
**Impact:** Advanced users cannot customize estimator hyperparameters via CLI. The assistant API accepts `estimator_kwargs: dict | None` but the CLI provides no way to pass this.  
**Recommended fix:** Add `--estimator-kwargs` flag accepting JSON string:
```python
estimator_kwargs: Annotated[str | None, typer.Option(...)] = None
# Parse with: json.loads(estimator_kwargs) if estimator_kwargs else None
```
**Effort:** S

#### C2: Missing env var for `send_data_to_llm` (FIXED)

**Location:** `ask` command (line ~327)  
**Impact:** Other LLM settings (`SKFORECAST_AI_LLM`, `SKFORECAST_AI_BASE_URL`) are resolvable via environment variables. The privacy-critical `send_data_to_llm` setting has only a CLI flag, making it impossible to set organization-wide via env.  
**Recommended fix:** Add `SKFORECAST_AI_SEND_DATA_TO_LLM` env var support using `_resolve()`.  
**Effort:** S

#### C3: No early LLM validation in `ask` command (FIXED)

**Location:** `ask` command (lines 600-645)  
**Impact:** Users see a "Thinking..." spinner and then get an error if the LLM is unreachable or not configured. Wastes time and confuses users.  
**Recommended fix:** Validate LLM connectivity (or at least configuration existence) before starting the spinner. Call a lightweight check (e.g., verify model string is parseable and provider is reachable).  
**Effort:** M

---

### 🟡 Medium

#### M1: Interval bounds not validated (SKIPED)

**Location:** `_parse_interval()` (line 148)  
**Impact:** `--interval "90,10"` (reversed bounds) is accepted silently, producing confusing prediction intervals.  
**Recommended fix:** Add `if parts[0] >= parts[1]: raise typer.BadParameter(...)`.  
**Effort:** S

#### M2: `--format` accepts any string without validation (SKIPED)

**Location:** All commands with `--format` option  
**Impact:** `--format jsn` (typo) silently skips output rendering (falls through to default branch).  
**Recommended fix:** Use `typer.Option(..., case_sensitive=False)` with an enum or add explicit validation.  
**Effort:** S

#### M3: Config file created with default umask (FIXED)

**Location:** `config.py` — `save_config()`  
**Impact:** On multi-user systems, `~/.config/skforecast-ai/config.toml` may be world-readable, exposing LLM provider strings and potentially base URLs.  
**Recommended fix:** Use `os.open(..., 0o600)` or `Path.chmod(0o600)` after creation.  
**Effort:** S

#### M4: No stdin size limit in `_read_json_input("-")` (SKIPED)

**Location:** `_read_json_input()` (line ~118)  
**Impact:** Potential OOM if piped unlimited input. Low real-world risk for a local CLI.  
**Recommended fix:** Read up to a limit (e.g., `sys.stdin.read(50 * 1024 * 1024)`) and raise if more exists.  
**Effort:** S

#### M5: `_error_handler` doesn't catch `json.JSONDecodeError` from `_read_json_input`

**Location:** `_error_handler()` (line 170)  
**Impact:** `_read_json_input` raises `ValueError` for invalid JSON (wrapping JSONDecodeError), which IS caught. However, if Pydantic `model_validate` fails with `ValidationError`, this is NOT caught by the handler.  
**Recommended fix:** Add `except pydantic.ValidationError as e` to `_error_handler()`.  
**Effort:** S

---

### 🟢 Low

#### L1: No `refine-plan` command (FIXED)

**Location:** N/A (missing command)  
**Impact:** Users must manually edit JSON plan files. The assistant supports `refine_plan()` for iterative plan adjustment.  
**Recommended fix:** Add `skforecast-ai refine-plan --from-plan plan.json --instruction "..."` command.  
**Effort:** M

#### L2: No `--verbose` flag

**Location:** All commands  
**Impact:** No way to see internal decision-making (forecaster selection reasons, lag calculation, etc.) for debugging.  
**Recommended fix:** Add `--verbose/-v` flag that sets logging level to DEBUG.  
**Effort:** S

#### L3: Shell completion not documented

**Location:** CLI help / README  
**Impact:** Users don't know Typer provides `--install-completion`.  
**Recommended fix:** Document in `cli_usage.md`.  
**Effort:** S

#### L4: Test structure uses classes (convention mismatch)

**Location:** `tests/test_cli.py`, `tests/test_cli_config.py`, `tests/test_cli_pipe.py`  
**Impact:** Repo conventions specify module-level functions, not test classes.  
**Recommended fix:** Refactor to module-level functions in a future pass. Non-blocking.  
**Effort:** L

#### L5: Non-quiet code paths largely untested

**Location:** Coverage lines 340-341, 352-353, 508-512, 530-531  
**Impact:** Spinner display code isn't exercised by tests. Very low risk since it's presentation-only.  
**Recommended fix:** Not critical. Could add a few tests without `--quiet` if desired.  
**Effort:** S

---

## Recommendations (Prioritized)

| Priority | Item | Effort | Issue |
|----------|------|--------|-------|
| 1 | Add `--estimator-kwargs` JSON flag to `plan` and `forecast` | S | C1 |
| 2 | Add `SKFORECAST_AI_SEND_DATA_TO_LLM` env var support | S | C2 |
| 3 | Validate interval bounds in `_parse_interval()` | S | M1 |
| 4 | Validate `--format` values (reject unknown strings) | S | M2 |
| 5 | Add `pydantic.ValidationError` to `_error_handler()` | S | M5 |
| 6 | Config file permissions (`0o600`) | S | M3 |
| 7 | Early LLM reachability check in `ask` | M | C3 |
| 8 | Add stdin size limit | S | M4 |
| 9 | Add `refine-plan` command | M | L1 |
| 10 | Add `--verbose` flag with logging | S | L2 |
| 11 | Document shell completion | S | L3 |
| 12 | Refactor tests to module-level functions | L | L4 |

---

## Appendix: Reproducing This Evaluation

```bash
# Activate environment
conda activate skforecast_ai_py13

# Run tests (60 tests)
python -c "
import pytest
pytest.main([
    'tests/test_cli.py', 'tests/test_cli_config.py', 'tests/test_cli_pipe.py',
    '-v', '--tb=short'
])
"

# Coverage (use coverage CLI to avoid numpy double-load with pytest-cov)
coverage run --source=skforecast_ai -m pytest tests/test_cli.py tests/test_cli_config.py tests/test_cli_pipe.py -q --tb=no
coverage report --include="skforecast_ai/cli.py" --show-missing

# Lint
ruff check skforecast_ai/cli.py

# Smoke test
python -c "
from skforecast_ai.cli import app
from typer.testing import CliRunner
runner = CliRunner()
r = runner.invoke(app, ['profile', 'dev/h2o_exog.csv', '-t', 'y', '-d', 'fecha', '--format', 'json', '-q'])
assert r.exit_code == 0
print('OK')
"
```

**Note:** `pytest-cov` plugin triggers a `numpy: cannot load module more than once per process` error on Python 3.13 with NumPy 2.4+. Use `coverage run` directly as shown above.
