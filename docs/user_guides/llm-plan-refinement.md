# AI-guided plan refinement

skforecast-ai computes the core features of your model (lags and rolling windows) deterministically, using statistical tests (like PACF) and frequency analysis. This guarantees a mathematically sound baseline. However, sometimes the math alone misses the *business context* behind your data.

If your dataset represents retail sales, you might know that the day of the week and the season are critical drivers, even if the series is too noisy for PACF to pick up a clean 7-day lag. **LLM-guided plan refinement** allows you to inject this domain knowledge into the forecasting plan using natural language.

This guide covers the two feature-engineering knobs that refinement touches, `lags` and `window_features`, both by natural-language prompt and by hand. The other override keys (`forecaster`, `estimator`, `estimator_kwargs`, `steps`, `interval`) are covered in [Customizing the model](customizing-the-model.md).

!!! note "Requires an LLM"
    Because this feature interprets natural language, you must have an LLM configured and the optional extras installed (`pip install "skforecast-ai[llm]"`). See [Using the AI assistant](using-the-ai-assistant.md).

## How it works

When you provide a `prompt` describing your domain knowledge, the assistant passes it to a specialized agent acting as an expert time series feature engineer. 

The agent analyzes your prompt alongside:
1. The structural facts of your data (observations, frequency), including the exact maximum lag/window size your dataset can support.
2. The current forecasting plan (horizon, current lags).
3. Hardcoded rules from skforecast-ai's skills (e.g., ensuring lags don't consume too much training data).

It then outputs a structured, deterministic update to your `lags` and `window_features`, returning a new `ForecastPlan` with its reasoning appended to the plan's `explanation`.

!!! note "Not applicable to statistical or foundation forecasters"
    `ForecasterStats` and foundation-model plans (`task_type` `'statistical'` / `'foundation'`) don't use `lags` or `window_features`, so there is nothing for the LLM to refine. Passing a `prompt` for such a plan ignores it (with a `UserWarning`) and returns the deterministic plan.

## Using the API

The entry point is `refine_plan()` with a `prompt` argument. It takes your existing profile, your existing plan, and your domain knowledge prompt. Without a `prompt`, `refine_plan()` applies only the explicit overrides deterministically.

```python
from skforecast_ai import ForecastingAssistant

# 1. Configure the assistant with an LLM
assistant = ForecastingAssistant(
    llm="openai:gpt-4o-mini", api_key="your_api_key_here"
)

# 2. Get the deterministic baseline
profile = assistant.profile(data, target="y", date_column="date")
plan = assistant.plan(profile, steps=14)

print(f"Original lags: {plan.forecaster_kwargs.get('lags')}")

# 3. Refine the plan using domain knowledge
prompt = "This is daily foot traffic data. We see strong weekly cycles and we care heavily about the 14-day trend."

refined_plan = assistant.refine_plan(
    profile=profile,
    plan=plan,
    prompt=prompt
)

print(f"Refined lags: {refined_plan.forecaster_kwargs.get('lags')}")
print(f"Refined windows: {refined_plan.forecaster_kwargs.get('window_features')}")
print(f"Reasoning:\n{refined_plan.explanation}")
```

Once you have the `refined_plan`, you can pass it to `forecast()` or `backtest()` exactly as you would a normal plan. Provide the same `profile` and `plan` so the assistant skips re-profiling and re-planning:

```python
# 4. Run the forecast with the refined plan
result = assistant.forecast(
    data=data,
    target="y",
    date_column="date",
    steps=14,
    profile=profile,
    plan=refined_plan,
)

print(result.predictions.head())
```


## Using the CLI

You can trigger this refinement directly from the terminal using the `refine-plan` command and the `--prompt` flag. 

You must first save a plan to JSON so the CLI has a baseline to work from.

```bash
URL="https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv"

# 1. Save the baseline plan
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 --format json > plan.json

# 2. Refine the plan with an LLM prompt (and save the new plan)
skforecast-ai refine-plan \
  --from-plan plan.json \
  --llm openai:gpt-4o-mini \
  --prompt "This is monthly data, make sure we capture the annual cycle and a smooth quarterly trend." \
  --format json > refined_plan.json
```

You can then pass `refined_plan.json` directly into `forecast` or `forecast-code`:

```bash
skforecast-ai forecast-code --from-plan refined_plan.json --output script.py
```

## Explicit manual overrides

If you already know the exact lags or window features you want, you don't need
the LLM: pass them directly to `plan()` or `refine_plan()`. (For the other
override keys, `forecaster`, `estimator`, `estimator_kwargs`, `steps`,
`interval`, see [Customizing the model](customizing-the-model.md).)

**In Python:**
```python
# During initial planning
plan = assistant.plan(
    profile=profile, 
    steps=14, 
    lags=[1, 7, 14], 
    window_features=[{'stats': ['mean', 'std'], 'window_sizes': 7}]
)

# Or refining an existing plan
refined_plan = assistant.refine_plan(
    profile=profile,
    plan=plan,
    lags=24 # Overrides previous lags
)
```

**In the CLI:**
```bash
skforecast-ai plan "$URL" --target y --date-column fecha --steps 24 \
  --lags "1,2,3,12" \
  --window-features '[{"stats": ["mean"], "window_sizes": 6}]'
```

Manual overrides are still checked against the same data budget as the
deterministic engine: the largest lag or window size cannot exceed ~33% of
the available observations. If you request something too large for your
dataset, `plan()`/`refine_plan()` raises a `ValueError` describing the
limit, rather than silently accepting it.

## Safety and Guardrails

Like all LLM features in `skforecast-ai`, LLM-guided `refine_plan()` operates within strict guardrails. The LLM is forced to output a structured JSON schema, which is parsed and validated by Pydantic before being applied to the plan.

When you supply a `prompt` together with explicit `lags` or `window_features`, the explicit overrides win (a `UserWarning` flags each shadowed field). If you set **both** `lags` and `window_features` explicitly, the LLM has nothing left to decide and is not called.

If the LLM suggests lags or window sizes that are too large for your dataset (violating the same data-budget check described above), the call is automatically retried: the assistant tells the model exactly which limit it violated and the maximum it must respect, up to 2 retries. This self-correction means a slightly-too-aggressive first suggestion (e.g. "capture the full year") usually still produces a usable plan on the next attempt.

If the LLM still can't produce a feasible suggestion after all retries (or a transient failure occurs, e.g. a network/provider error), the call fails gracefully: it emits a `UserWarning` and returns the deterministic plan (with no reasoning appended), so your workflow continues uninterrupted.

## Next steps

- **[Human-in-the-loop forecasting](human-in-the-loop.md)**: see how plan refinement fits into the broader iterative workflow.
- **[Customizing the model](customizing-the-model.md)**: explore the other overrides you can apply to a plan, like changing the estimator or interval.
- **[Using the AI assistant](using-the-ai-assistant.md)**: learn more about configuring LLM providers and the `ask()` command.