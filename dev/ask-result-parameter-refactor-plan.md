# Implementation Plan: Collapse `ask()` result parameters into a single `result`

## Problem

`ForecastingAssistant.ask()` currently accepts one named parameter per workflow
result type (`forecast_result`, `backtest_result`). Every new workflow (e.g. a
future `compare`, `tune`, ...) would add another parameter, plus its own
mutual-exclusivity check, type validation, and extraction branch. The signature
and method body grow linearly with the number of result types.

## Goal

Make `ask()` closed for modification with respect to new result types:

- One polymorphic `result` parameter replaces the per-type parameters.
- A thin shared base class (`WorkflowResult`) declares the superset of
  optional fields `ask()` consumes, so extraction is structural (attribute
  reads) — no `isinstance` dispatch and no per-type projection method.
- Adding a new workflow = create a `WorkflowResult` subclass. `ask()` never
  changes.

## Design decision (rationale)

Three options were considered:

1. **`isinstance` dispatch inside `ask()`** — rejected. Moves the ever-growing
   list from the signature into the method body; `ask()` still changes per type.
2. **Full `AskContext` + per-type `as_ask_context()` projection** — deferred.
   Correct Open/Closed pattern, but the existing result schemas already share
   the same field names, so a projection container + per-type method is ceremony
   for a problem we do not yet have (YAGNI). Adopt this later only if a result
   type needs genuinely different context shaping.
3. **Single `result` param + thin `WorkflowResult` base (chosen)** — minimal,
   type-safe, scales to N result types with zero changes to `ask()`.

## Affected files

- `skforecast_ai/schemas/results.py` — add `WorkflowResult` base; make
  `ForecastResult` and `BacktestResult` inherit from it.
- `skforecast_ai/schemas/__init__.py` — export `WorkflowResult`.
- `skforecast_ai/__init__.py` — re-export `WorkflowResult`.
- `skforecast_ai/assistant.py` — replace `forecast_result` / `backtest_result`
  parameters with `result`; simplify validation and extraction in `ask()`.
- `tests/` — update `ask()` tests that pass `forecast_result` /
  `backtest_result`; add tests for the new `result` path and validation.

## Step-by-step

### 1. Add `WorkflowResult` base in `schemas/results.py`

Declare the superset of optional fields that `ask()` reads. `AskContext` is not
introduced.

```python
class WorkflowResult(DisplayMixin, BaseModel):
    """Base for workflow results that `ask()` can explain."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: ForecastingProfile | None = None
    plan: ForecastPlan | None = None
    code: str | None = None
    predictions: Any = None   # pd.DataFrame | None
    metrics: Any = None       # pd.DataFrame | None
    cv_config: dict | None = None
```

### 2. Re-parent existing result schemas

- `ForecastResult(WorkflowResult)` — keep `profile`, `plan`, `code`, `metrics`,
  `predictions` (tighten required ones as today). `cv_config` inherits as
  `None`.
- `BacktestResult(WorkflowResult)` — keep existing required fields including
  `cv_config` and `explanation`.

Preserve each class's existing `_rich_body` rendering unchanged.

Note: `CodeGenerationResult` and `AskResult` are intentionally **not**
re-parented (they are not passed into `ask()` as context inputs).

### 3. Update `ask()` signature and body in `assistant.py`

Replace:

```python
forecast_result: ForecastResult | None = None,
backtest_result: BacktestResult | None = None,
```

with:

```python
result: WorkflowResult | None = None,
```

Replace the two validation blocks + mutual-exclusivity check + the
`if forecast_result ... elif backtest_result ...` extraction with:

```python
if result is not None and not isinstance(result, WorkflowResult):
    raise TypeError(
        f"`result` must be a `WorkflowResult` object, got "
        f"{type(result).__name__}."
    )

predictions = metrics = cv_config = None
if result is not None:
    profile = profile or result.profile
    plan = plan or result.plan
    predictions = result.predictions
    metrics = result.metrics
    cv_config = result.cv_config
```

Update the downstream `generated_code` selection and `send_data` logic to key
off `result is not None` instead of `forecast_result` / `backtest_result`.

### 4. Update docstring of `ask()`

- Collapse the "Results mode" and "Backtest mode" descriptions to a single
  "Results mode (`result` provided)" that covers any `WorkflowResult`.
- Replace the `forecast_result` / `backtest_result` parameter entries with a
  single `result : WorkflowResult, default None` entry.

### 5. Exports

- Add `WorkflowResult` to `schemas/__init__.py` imports and `__all__`.
- Re-export from `skforecast_ai/__init__.py`.

### 6. Tests

- Update existing `ask()` tests in `tests/` that pass `forecast_result=` or
  `backtest_result=` to use `result=`.
- Add tests:
  - `ask(result=<ForecastResult>)` extracts profile/plan/predictions/metrics.
  - `ask(result=<BacktestResult>)` additionally surfaces `cv_config`.
  - `ask(result=<invalid type>)` raises `TypeError`.
- Confirm the mutual-exclusivity test (`forecast_result` + `backtest_result`)
  is removed, since it no longer applies.

## Backward compatibility

**Decision: Option A (clean replacement).** Drop `forecast_result` /
`backtest_result` entirely; no deprecated aliases.

Rationale:

- This ships in `0.2.0`, pre-1.0, where the API is explicitly unstable and
  SemVer permits breaking changes in a minor bump.
- Low/no external adoption means deprecation-alias machinery (warnings,
  dual-parameter conflict checks, extra tests) would protect callers that do
  not exist.
- Aliases would clutter the very signature this refactor is meant to keep clean
  and add maintenance cost plus a future removal step.

Action: document the breaking change in the `0.2.0` release notes:
`ask(forecast_result=..., backtest_result=...)` becomes `ask(result=...)`.

Considered but rejected — **Option B (deprecated aliases):** keep both
parameters, map onto `result` with a `DeprecationWarning`, and raise if both an
alias and `result` are set. More code, smoother migration; unnecessary at this
adoption stage.

## Validation

- Run the assistant test suite:
  `pytest tests/test_assistant_ask.py -vv`
- Full suite for regressions:
  `pytest tests/ -q`
- Confirm no remaining references to `forecast_result` / `backtest_result`:
  grep the repo.

## Future extension (documented, not implemented now)

When a result type needs context shaping beyond "share the same field names"
(e.g. different summarization for a `CompareResult`), introduce an
`as_ask_context()` method on `WorkflowResult` and have `ask()` consume the
projected context. This is a non-breaking refactor from the shared-base design.
