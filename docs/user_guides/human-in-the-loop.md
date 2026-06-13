# Human-in-the-loop forecasting

The most powerful way to use skforecast-ai is as a loop, not a one-shot call. You get a baseline, ask *why* and *what could be better*, apply the change you agree with, and re-run, staying in control of every decision while the assistant handles the mechanics and keeps the result reproducible.

```
forecast()  →  ask("how could this be better?")  →  refine_plan(...)  →  forecast() / backtest()
   baseline        diagnosis & suggestions            your decision         measure the change
```

The LLM **advises**; it never changes the model or the numbers. Every override is yours, and every result still ships with the exact code that produced it.

## 1. Get a baseline

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")   # LLM enables step 2

result = assistant.forecast(data, target="y", steps=24, date_column="date")
print(result.metrics)
print(result.plan.forecaster, result.plan.estimator)
print(result.plan.forecaster_kwargs)   # lags and other forecaster settings
```

## 2. Ask what could be better

Pass the result straight to `ask()`. The assistant reuses its profile and plan, so nothing is recomputed, and the answer is grounded in the engine's real rules (see [How it works & trust](how-it-works-and-trust.md)).

```python
answer = assistant.ask(
    "These metrics look mediocre. What concrete changes would most likely improve accuracy?",
    forecast_result=result,
)
print(answer.explanation)
```

Typical suggestions: try a different estimator, add calendar/exogenous features, adjust lags, apply differentiation, or validate more rigorously. The point is that you read the reasoning and decide; the model can't silently act on it.

!!! note "Step 2 is the only part that needs an LLM"
    Without a configured model, `ask()` raises `LLMRequiredError`. The rest of the loop is fully deterministic, so if you already know what to change, skip straight to step 3.

## 3. Apply the change you agree with

Turn a suggestion into a concrete override with `refine_plan()`. It returns a new plan with your change applied and everything else (lags, metric, preprocessing) preserved:

```python
profile = result.profile
plan    = result.plan

plan = assistant.refine_plan(
    profile, plan,
    estimator="LGBMRegressor",
    estimator_kwargs={"n_estimators": 300, "learning_rate": 0.05},
)
print(plan.estimator, plan.estimator_kwargs)   # inspect before running
```

The override keys are the same everywhere: `forecaster`, `estimator`, `estimator_kwargs`, `steps`, `interval`. A `forecaster` override must be one of `profile.forecaster_candidates`, a model the engine already judged compatible with your data. See [Customizing the model](customizing-the-model.md) for the full list.

## 4. Re-run and measure

Re-run with the refined plan, passing the existing `profile`/`plan` so nothing is recomputed:

```python
improved = assistant.forecast(
    data, target="y", steps=24, date_column="date",
    profile=profile, plan=plan,
)
print(improved.metrics)
```

Compare metrics against the baseline. A single forecast can be noisy, so for a decision you trust, validate with [backtesting](backtesting.md) instead:

```python
cv, _ = assistant.create_cv(profile, plan)
bt = assistant.backtest(
    data, target="y", date_column="date", cv=cv,
    profile=profile, plan=plan,
)
print(bt.metrics)
```

## 5. Iterate or ship

Loop back to step 2 as many times as you like, then export the winner as a standalone script ([Reproducible code](reproducible-code.md)) and run it in production with plain `skforecast`. Because the loop is deterministic, anyone who runs that script gets exactly your numbers.

## Why this is safe

- **The LLM is advisory only.** It reads state and explains; `refine_plan()` and `forecast()` are the only things that change a model, and you call them.
- **Overrides are constrained.** Forecaster choices are limited to candidates the engine vetted for your data.
- **Every step is auditable.** `result.code` is the literal script that ran, so inspect it before you trust it.

## Next steps

- **[Using the AI assistant](using-the-ai-assistant.md)**: configure a provider and the four `ask()` modes.
- **[Customizing the model](customizing-the-model.md)**: the complete set of overrides.
- **[Backtesting & validation](backtesting.md)**: confirm an improvement is real, not noise.
