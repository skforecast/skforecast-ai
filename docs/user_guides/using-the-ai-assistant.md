---
title: Using the AI assistant
status: draft
---

# Using the AI assistant (optional)

!!! note "Draft — outline"
    This guide will cover turning on a language model and asking it questions about your forecast. Everything else in skforecast-ai works without it. Outline below.

The LLM is an **explainer**, not a decision-maker: it reads the deterministic pipeline's state and answers questions in plain language. It never changes the forecast. See [How it works & trust](how-it-works-and-trust.md).

## Configure a provider

- Enable it at construction with `llm="provider:model"`:

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")
```

- Built-in providers: `openai`, `google`, `anthropic`, `groq`, `ollama`. Any other prefix is treated as an OpenAI-compatible endpoint (set `base_url`).
- Credentials: pass `api_key=` / `base_url=` to the constructor, or rely on the provider's environment variables.
- The model string is `provider:model_name`; model names may themselves contain colons (e.g. `ollama:qwen2.5:7b-instruct`).
- Persistent settings can be stored via the CLI (`skforecast-ai config set ...`).

## Ask questions

- `ask(prompt, ...)` returns an `AskResult` with `.explanation` (the answer) and, when relevant, `.profile`, `.plan`, and `.code`.
- Answers are grounded in the assistant's rule-based **skills**, so explanations match engine behavior.
- Without a configured model, `ask()` raises `LLMRequiredError`.

```python
result = assistant.forecast(data, target="y", steps=12, date_column="date")
answer = assistant.ask("Why was this estimator chosen?", forecast_result=result)
print(answer.explanation)
```

## Privacy

- By default the model receives the structural profile and decisions, **not** your raw data.
- Opt in with `ForecastingAssistant(llm=..., send_data_to_llm=True)`.

---

<!-- To expand later: per-provider env vars, Ollama local setup, include_reference, selecting skills explicitly, create_cv(prompt=...).
  Seed: dev/demo_ask.ipynb; skforecast_ai/llm/{provider,agent,skills}.py; config.py.
  API to cover: ForecastingAssistant(llm/base_url/api_key/send_data_to_llm), ask(), AskResult. -->
