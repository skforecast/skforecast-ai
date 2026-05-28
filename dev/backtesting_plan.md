# Backtesting Implementation Plan

## Approach

Two new public methods on `ForecastingAssistant`:

1. **`create_cv(profile, plan, *, prompt=None, **kwargs)`** — Produces a `TimeSeriesFold` object. Two modes:
   - **LLM mode** (prompt provided, LLM configured): The user describes their deployment/evaluation scenario in natural language. The LLM deduces the `TimeSeriesFold` parameters. Explicit kwargs override LLM-deduced values.
   - **Deterministic mode** (no prompt or no LLM): Smart defaults derived from the profile and plan (initial_train_size=70% of data, refit=True, fixed_train_size=False, steps from plan).

2. **`backtest(data, target, ..., cv)`** — Same signature as `forecast()` minus `exog_future` and `steps`, plus a **mandatory** `cv` argument. `steps` is inferred from `cv.steps`. Purely deterministic execution: profile → plan → run backtesting with the provided cv.

### Design Principles

- `cv` is mandatory in `backtest()` — no hidden defaults during execution, the user must have an intentional evaluation strategy.
- `steps` is NOT a parameter of `backtest()` — it is always inferred from `cv.steps`. When `plan` is also provided, `cv.steps == plan.steps` is validated.
- `create_cv()` absorbs all the complexity (LLM or deterministic). Output is always an inspectable `TimeSeriesFold` object.
- Priority: explicit kwarg > LLM-deduced > deterministic default.
- Return type of `create_cv()` is `tuple[TimeSeriesFold, str]` — the cv object (zero lock-in, usable with skforecast directly) plus a human-readable explanation.
- `create_cv` only sets: `steps`, `initial_train_size`, `refit`, `fixed_train_size`, `gap`, `fold_stride`, `skip_folds`, `allow_incomplete_fold`. The remaining TimeSeriesFold params (`window_size`) is left as `None` — skforecast's backtesting functions auto-resolve them from the forecaster at runtime. The `differentiation` must be set from `plan.forecaster_kwargs.get('differentiation')` if present, to enable accurate fold visualization via `cv.split()` before running backtesting.
- Validation: call `cv.split(X=pd.RangeIndex(n_observations), as_pandas=False)` and count folds. Must produce ≥2 folds. When `initial_train_size` is a date string, skip this validation (requires actual DatetimeIndex, which will be validated at `backtest()` time).
- `n_observations` is always sourced from `profile.data_profile.n_observations`.
- `metric` for backtesting is sourced from `plan.metrics_to_compute`.
- Exogenous variables are extracted from `data` using `profile.data_profile.exog_columns` and passed as `exog=` to the backtesting function.

### Reference

- TimeSeriesFold API: https://skforecast.org/0.22.0/api/model_selection#skforecast.model_selection._split.TimeSeriesFold
- Backtesting functions API: https://skforecast.org/0.22.0/api/model_selection

### Testing

```bash
conda activate skforecast_ai_py13
pytest tests/ -vv
```

---

## Phase 1: `create_cv` — Deterministic Path

Implement the deterministic (no-LLM) `create_cv` method with smart defaults.

### Tasks

- [ ] Add `create_cv` method to `ForecastingAssistant` with signature:
  ```python
  def create_cv(
      self,
      profile: ForecastingProfile,
      plan: ForecastPlan,
      *,
      prompt: str | None = None,
      # TimeSeriesFold kwargs (all optional, override defaults)
      initial_train_size: int | float | str | None = None,
      refit: bool | int | None = None,
      fixed_train_size: bool | None = None,
      gap: int | None = None,
      fold_stride: int | None = None,
      skip_folds: int | list[int] | None = None,
      allow_incomplete_fold: bool | None = None,
  ) -> tuple[TimeSeriesFold, str]:
  ```
- [ ] Implement default derivation logic in a new `recommendation/backtesting.py` module:
  - `initial_train_size`: 70% of `profile.data_profile.n_observations` (int).
    - Floor by task_type:
      - ML tasks (`single_series`, `multi_series`, `multivariate`): at least 2× max lag from `plan.forecaster_kwargs.get('lags')`. Lags type handling:
        - `int` → max_lag = lags
        - `list[int]` → max_lag = max(lags)
        - `None` → fall through to `2 * plan.steps`
      - `statistical`: at least `2 * plan.steps` (model needs enough history to fit seasonal patterns).
      - `foundation`: at least `2 * plan.steps` (context window is handled by the model internally).
  - `refit`: `True`
  - `fixed_train_size`: `False` (expanding window)
  - `gap`: `0`
  - `fold_stride`: `None` (defaults to steps in TimeSeriesFold)
  - `skip_folds`: `None`
  - `allow_incomplete_fold`: `True`
  - `differentiation`: from `plan.forecaster_kwargs.get('differentiation')` if present, else `None`.
  - `steps`: from `plan.steps`
- [ ] Add validation: instantiate the `TimeSeriesFold`, then call `cv.split(X=pd.RangeIndex(n_observations), as_pandas=False)`. Count the returned folds. If fewer than 2, raise `ValueError` with a message showing the resolved parameters and how many folds were produced. When `initial_train_size` is a date string, skip this validation (deferred to `backtest()` time).
- [ ] Support `initial_train_size` as:
  - `int` → absolute number of observations
  - `float` → fraction of `profile.data_profile.n_observations`. Must satisfy `0 < value < 1`; raise `ValueError` otherwise.
  - `str` → date string (passed directly to TimeSeriesFold)
  - `None` → 70% default
- [ ] `create_cv` returns a tuple `(TimeSeriesFold, str)` where the string is a human-readable explanation of the chosen configuration (e.g. "Using 70% of data (140 observations) for initial training, expanding window, refit every fold, 10-step horizon, 7 folds"). For both, LLM and deterministic paths, the explanation should clearly state the resolved parameters and the rationale.
- [ ] Unit tests for `create_cv` deterministic path.

---

## Phase 2: `backtest` Method — Execution

Implement the `backtest()` method that runs backtesting with the provided cv.

### Tasks

- [ ] Add `backtest` method to `ForecastingAssistant` with signature:
  ```python
  def backtest(
      self,
      data: pd.DataFrame | str | Path,
      target: str | list[str],
      cv: TimeSeriesFold,
      date_column: str | None = None,
      series_id_column: str | None = None,
      forecaster: str | None = None,
      estimator: str | None = None,
      estimator_kwargs: dict | None = None,
      interval: list[int] | None = None,
      profile: ForecastingProfile | None = None,
      plan: ForecastPlan | None = None,
  ) -> BacktestResult:
  ```
  - `steps` is inferred from `cv.steps`. When `plan=None`, the internal `plan()` call receives `steps=cv.steps`.
  - When both `cv` and `plan` are provided, validate `cv.steps == plan.steps`. Raise `ValueError` if they differ (critical for `ForecasterDirect`/`ForecasterDirectMultiVariate` where model architecture depends on steps).
  - **Exog handling**: exogenous variables are extracted from `data` using `profile.data_profile.exog_columns` (same pattern as `forecast()`). Worth noting in the docstring that `data` must include exog columns if the plan uses them.
- [ ] Define `BacktestResult` schema in `schemas/results.py`:
  ```python
  class BacktestResult(BaseModel):
      model_config = ConfigDict(arbitrary_types_allowed=True)

      profile: ForecastingProfile
      plan: ForecastPlan
      cv_config: dict         # resolved TimeSeriesFold parameters for traceability
      metrics: Any            # pd.DataFrame — metric values
      predictions: Any        # pd.DataFrame — full backtest predictions
      code: str               # generated backtesting script (inspectable/reproducible)
      explanation: str        # human-readable explanation of the backtesting configuration and results
  ```
- [ ] Implement execution logic in a new `execution/backtesting_runner.py`:
  - Build forecaster programmatically from plan (import class, instantiate with kwargs — same logic as `forecast_code` but executed in-memory).
  - Dispatch to the appropriate backtesting function based on `plan.task_type`:

    | `task_type` | Function | `y`/`series` arg | Interval arg |
    |-------------|----------|-------------------|--------------|
    | `single_series` | `backtesting_forecaster` | `y=` | `interval=` |
    | `multi_series` | `backtesting_forecaster_multiseries` | `series=` | `interval=` |
    | `multivariate` | `backtesting_forecaster_multiseries` | `series=` | `interval=` |
    | `statistical` | `backtesting_stats` | `y=` | `interval=` |
    | `foundation` | `backtesting_foundation` | `series=` | `quantiles=` |

  - Pass `metric=plan.metrics_to_compute` to the backtesting function.
  - Return metrics + predictions.
  - **Phase 2 scope**: implement `single_series` and `multi_series` first. Add `statistical`, `foundation`, and `multivariate` incrementally (they have more signature differences).
- [ ] Code generation: add backtesting template to `generation/code_templates.py` so `BacktestResult.code` contains a runnable script. The generated code follows the same pattern as `forecast_code()`: imports, data loading, preprocessing, forecaster initialization (without fit), TimeSeriesFold creation, and the `backtesting_forecaster(...)` call.
- [ ] `BacktestResult.explanation`: concatenation of the CV explanation (from `create_cv`) + a post-execution summary (e.g. "Backtesting completed: 7 folds evaluated. Mean MAE: 0.42, Mean MSE: 0.31.").
- [ ] Unit tests for `backtest` method.

---

## Phase 3: `create_cv` — LLM Path

Add LLM-powered fold configuration from natural language prompts.

### Tasks

- [ ] Define structured output schema for LLM response (the cv parameters as a Pydantic model).
- [ ] Implement LLM call within `create_cv` when `prompt` is provided and `self.llm` is configured:
  - Build system prompt with TimeSeriesFold documentation + data context (frequency, n_observations, steps).
  - Send user prompt describing their deployment scenario.
  - Parse structured output into TimeSeriesFold kwargs.
  - Explicit kwargs override LLM-deduced values.
- [ ] Error handling — validate → up to two retries → deterministic fallback:
  1. LLM produces params → apply explicit kwargs overrides.
  2. Try `TimeSeriesFold(...)` instantiation. Can fail (e.g. invalid types, negative values).
  3. If instantiation succeeds, try `cv.split(X=pd.RangeIndex(n_observations), as_pandas=False)`. Can fail (e.g. `initial_train_size` > data length, not enough data for steps).
  4. If split succeeds, count folds. If <2 folds, treat as failure.
  5. **On any failure**: up to TWO retries — send the error message back to the LLM with context: `"Your configuration failed: {error}. The data has {n_observations} observations and steps={steps}. Fix it."` Re-validate each retry output.
  6. **If both retries fail**: fall back to deterministic defaults. Emit a warning with:
     - The LLM's attempted params.
     - The error message from skforecast.
     - The deterministic defaults being used instead.
     - Hint: "You can override with explicit kwargs."
- [ ] Add a skill file (`skills/backtesting-configuration/SKILL.md`) with TimeSeriesFold parameter documentation and examples of business-to-parameter mapping.
- [ ] Unit tests for LLM path (mocked): success, retry-then-success, retry-then-fallback.

---

## Phase 4: Integration & Polish

- [ ] Integration tests: full workflow `profile → plan → create_cv → backtest`.
- [ ] CLI integration: add `backtest` subcommand if applicable.
- [ ] Documentation: update docstrings, add usage examples in `dev/`.
- [ ] Ensure `ask()` can explain backtest results (pass `BacktestResult` to ask similarly to `ForecastResult`).
