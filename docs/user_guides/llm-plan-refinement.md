# LLM-guided plan refinement

skforecast-ai computes the core features of your model—lags and rolling windows—deterministically, using statistical tests (like PACF) and frequency analysis. This guarantees a mathematically sound baseline. However, sometimes the math alone misses the *business context* behind your data.

If your dataset represents retail sales, you might know that the day of the week and the season are critical drivers, even if the series is too noisy for PACF to pick up a clean 7-day lag. **LLM-guided plan refinement** allows you to inject this domain knowledge into the forecasting plan using natural language.

!!! note "Requires an LLM"
    Because this feature interprets natural language, you must have an LLM configured and the optional extras installed (`pip install "skforecast-ai[llm]"`). See [Using the AI assistant](using-the-ai-assistant.md).

## How it works

When you provide a `prompt` describing your domain knowledge, the assistant passes it to a specialized agent acting as an expert time series feature engineer. 

The agent analyzes your prompt alongside:
1. The structural facts of your data (observations, frequency).
2. The current forecasting plan (horizon, current lags).
3. Hardcoded rules from skforecast-ai's skills (e.g., ensuring lags don't consume too much training data).

It then outputs a structured, deterministic update to your `lags` and `window_features`, returning a new `ForecastPlan` along with its reasoning.

## Using the API

The entry point is `refine_plan_with_llm()`. It takes your existing profile, your existing plan, and your domain knowledge prompt.

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

refined_plan, reasoning = assistant.refine_plan_with_llm(
    profile=profile,
    plan=plan,
    prompt=prompt
)

print(f"Refined lags: {refined_plan.forecaster_kwargs.get('lags')}")
print(f"Refined windows: {refined_plan.forecaster_kwargs.get('window_features')}")
print(f"Reasoning:\n{reasoning}")
```

Once you have the `refined_plan`, you can pass it to `forecast()` or `backtest()` exactly as you would a normal plan.

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

If you already know the exact lags or window features you want to use, you don't need the LLM. You can bypass the deterministic engine and set them explicitly using `plan()` or `refine_plan()`.

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

## Safety and Guardrails

Like all LLM features in `skforecast-ai`, `refine_plan_with_llm` operates within strict guardrails. The LLM is forced to output a structured JSON schema, which is parsed and validated by Pydantic before being applied to the plan. 

If the LLM suggests lags that are too large for your dataset, or formatting that `skforecast` cannot accept, the validation step will fail gracefully, emit a warning, and return your original plan untouched.

## Next steps

- **[Human-in-the-loop forecasting](human-in-the-loop.md)**: see how plan refinement fits into the broader iterative workflow.
- **[Customizing the model](customizing-the-model.md)**: explore the other overrides you can apply to a plan, like changing the estimator or interval.
- **[Using the AI assistant](using-the-ai-assistant.md)**: learn more about configuring LLM providers and the `ask()` command.