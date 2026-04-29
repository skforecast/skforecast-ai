# Phase 1 — Package Skeleton & Schemas

## Goal

Create an installable Python package with all Pydantic schemas defined and
validated. No business logic yet — only the data contracts that every other
module will import.

## Files to Create

```
pyproject.toml
README.md                          (minimal, install + what-is-this)
skforecast_ai/__init__.py          (version, top-level imports)
skforecast_ai/schemas.py           (DataProfile, ForecastPlan, Warning, etc.)
skforecast_ai/profiling/__init__.py
skforecast_ai/recommendation/__init__.py
skforecast_ai/generation/__init__.py
skforecast_ai/execution/__init__.py
skforecast_ai/llm/__init__.py
tests/__init__.py
tests/test_schemas.py
```

## Schema Definitions (schemas.py)

```python
class DataProfile(BaseModel):
    n_observations: int
    n_series: int
    index_type: Literal["datetime", "range", "other"]
    frequency: str | None
    target: str
    date_column: str | None
    series_id_column: str | None
    exog_columns: list[str]
    categorical_exog: list[str]
    missing_values: dict[str, int]
    inferred_seasonalities: list[int]
    warnings: list[str]

class ForecastPlan(BaseModel):
    task_type: Literal[
        "single_series", "multi_series", "multivariate",
        "statistical", "foundation", "classification", "baseline",
    ]
    forecaster: str
    estimator: str | None
    horizon: int
    frequency: str | None
    lags: int | list[int] | None
    metric: str
    backtesting_strategy: str
    interval_method: str | None
    use_exog: bool
    data_requirements: list[str]
    warnings: list[str]
    rationale: str
```

## pyproject.toml Key Decisions

- `requires-python = ">=3.10"`
- Core dependencies: `pydantic>=2.0`, `pandas>=2.1`, `skforecast>=0.22`
- Optional groups: `[llm]` → `pydantic-ai`, `[cli]` → `typer[all]`, `[dev]` → `pytest`, `ruff`
- Entry point: `[project.scripts] skforecast-ai = "skforecast_ai.cli:app"`

## Tests (tests/test_schemas.py)

| Test | What it validates |
|------|-------------------|
| `test_data_profile_minimal` | Minimal valid DataProfile (required fields only) |
| `test_data_profile_full` | All fields populated |
| `test_data_profile_invalid_index_type` | Rejects unknown `index_type` |
| `test_forecast_plan_minimal` | Minimal valid ForecastPlan |
| `test_forecast_plan_invalid_task_type` | Rejects unknown `task_type` |
| `test_schemas_json_roundtrip` | `.model_dump_json()` → `.model_validate_json()` |

## Done Criteria

- [ ] `pip install -e ".[dev]"` succeeds
- [ ] `python -c "from skforecast_ai.schemas import DataProfile, ForecastPlan"` works
- [ ] `pytest tests/test_schemas.py` passes (≥ 6 tests)
- [ ] `ruff check skforecast_ai/` reports 0 issues
