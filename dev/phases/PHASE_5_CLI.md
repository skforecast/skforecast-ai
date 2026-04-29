# Phase 5 — CLI (Tier 0 Complete)

## Goal

Expose `inspect`, `recommend`, and `generate-code` as CLI commands.
Completes the Tier 0 (no-LLM) user experience end to end.

## Files to Create

```
skforecast_ai/cli.py              (Typer app with 3 commands)
tests/test_cli.py
```

## Commands

```bash
# Inspect: profile the dataset
skforecast-ai inspect data.csv --target sales --date date

# Recommend: profile + recommend
skforecast-ai recommend data.csv --target sales --date date --horizon 30

# Generate code: profile + recommend + generate
skforecast-ai generate-code data.csv --target sales --date date --horizon 30 \
    --output forecast_script.py
```

## CLI Implementation Details

| Command | Internal flow | Output |
|---------|--------------|--------|
| `inspect` | Load CSV → `create_data_profile()` → print profile as formatted table/JSON | DataProfile (stdout or `--json`) |
| `recommend` | `inspect` flow → `recommend_plan()` → print plan | ForecastPlan (stdout or `--json`) |
| `generate-code` | `recommend` flow → `generate_code()` → write to file or stdout | Python script |

Common options: `--target`, `--date`, `--series-id`, `--json` (machine-readable output), `--output` (file path).

## Tests (tests/test_cli.py)

| Test | What it validates |
|------|-------------------|
| `test_inspect_csv` | `inspect` on a sample CSV prints valid JSON profile |
| `test_inspect_missing_target_error` | Missing `--target` gives clear error |
| `test_recommend_csv` | `recommend` prints valid JSON plan |
| `test_generate_code_to_stdout` | `generate-code` prints Python code |
| `test_generate_code_to_file` | `generate-code --output` writes a file |
| `test_nonexistent_file_error` | Clear error message for bad path |

## Done Criteria

- [ ] `pip install -e ".[cli]"` installs the CLI
- [ ] `skforecast-ai inspect sample.csv --target y --date ds` works end to end
- [ ] `skforecast-ai generate-code sample.csv --target y --date ds --horizon 10` produces valid Python
- [ ] `--json` flag produces machine-parseable output
- [ ] `pytest tests/test_cli.py` passes (≥ 6 tests)
- [ ] **Tier 0 is fully usable**: no LLM, no API key, no network needed
