# Using the AI assistant (optional)

Everything in skforecast-ai works **without** a language model. The optional LLM is a **reasoning layer**: it functions like a Senior Data Scientist looking over your shoulder, evaluating backtesting metrics, diagnosing execution errors, and suggesting concrete modeling improvements. It reads the pipeline's state and advises you, while leaving every decision and all execution to the deterministic core. The principle behind this separation is described in [How it works & trust](how-it-works-and-trust.md).

This guide covers turning a model on and asking it questions.

## Configure a provider

Enable the LLM at construction time with an `llm="provider:model"` string:

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")
```

The string is always `provider:model_name`. Because only the first colon is used to split, model names may themselves contain colons (e.g. `ollama:qwen2.5:7b-instruct`).

### Supported providers

| Provider prefix | Notes |
| --- | --- |
| `openai` | Uses the OpenAI Chat Completions API. |
| `google` | Google Gemini models. |
| `anthropic` | Anthropic Claude models. |
| `groq` | Groq-hosted open models. |
| `ollama` | Local models: see below. |
| *anything else* | Treated as an OpenAI-compatible endpoint; set `base_url`. |

### Credentials

For cloud providers, supply the API key in either way:

- **Environment variable** (recommended): the provider's standard variable, e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`. Set it once and the assistant picks it up automatically.
- **Constructor argument**: pass `api_key=` (and `base_url=` for custom or self-hosted endpoints) directly:

```python
assistant = ForecastingAssistant(
    llm="anthropic:claude-3-5-haiku-latest",
    api_key="sk-...",
)
```

### Local models with Ollama

`ollama` runs entirely on your machine: no key, no cloud. Make sure the daemon is running (`ollama serve`); the assistant checks reachability before each call and points you here if it can't connect. The default endpoint is `http://localhost:11434/v1`; override it with `base_url=` if Ollama runs elsewhere.

```python
assistant = ForecastingAssistant(llm="ollama:qwen2.5:7b-instruct")
```

## Ask questions

`ask(prompt, ...)` returns an `AskResult` with the answer in `.explanation`, plus `.profile`, `.plan`, and `.code` when the question involved a dataset or a forecast. Without a configured model it raises `LLMRequiredError`.

The most common pattern is to explain a forecast you've already run: pass the result straight through:

```python
result = assistant.forecast(data, target="y", steps=12, date_column="date")
answer = assistant.ask("Why was this estimator chosen?", forecast_result=result)
print(answer.explanation)
```

`ask()` operates in four modes, depending on what you give it:

| Mode | Trigger | What the model explains |
| --- | --- | --- |
| **Q&A** | prompt only | General forecasting or `skforecast` questions. |
| **Explain** | `data=` or `profile=` (+ `steps=`) | The profiling and planning decisions for your data. |
| **Results** | `forecast_result=` | Predictions, metrics, and intervals from a completed `forecast()`. |
| **Backtest** | `backtest_result=` | Metrics, predictions, and CV configuration from a completed `backtest()`. |

```python
# Explain mode: profile and plan are computed first, then explained
answer = assistant.ask(
    "Is my data suitable for forecasting?",
    data=data, target="y", date_column="date", steps=12,
)
```

!!! note "`forecast_result` and `backtest_result` are mutually exclusive"
    Pass one or the other, not both. In either case the assistant reuses the `profile` and `plan` from the result, so you don't recompute them.

## What grounds the answers

Answers are grounded in the assistant's rule-based **skills** (Markdown documents that mirror the engine's actual heuristics) so explanations stay consistent with what the deterministic engine did. Skill selection is automatic and rule-based (by task type and the keywords in your question); there's no fuzzy vector search. The mechanism is detailed in [How it works & trust](how-it-works-and-trust.md).

Two optional arguments give you manual control:

- `skills=[...]`: pin an explicit list of skills instead of letting the assistant choose. Valid names are in `skforecast_ai.ALL_SKILLS`.
- `include_reference=True`: also inject the `skforecast` API reference, useful for detailed code questions.

```python
answer = assistant.ask(
    "How do I add prediction intervals?",
    forecast_result=result,
    skills=["prediction-intervals"],
    include_reference=True,
)
```

## Privacy

By default the model receives only the **structural profile and the modeling decisions**, never your raw data. Opt in explicitly if you want it to see the underlying values:

```python
assistant = ForecastingAssistant(llm="openai:gpt-4o-mini", send_data_to_llm=True)
```

!!! note "Results and backtest modes are the exception"
    When you pass a `forecast_result` or `backtest_result`, the assistant sends the predictions, metrics, and intervals regardless of `send_data_to_llm` (the model needs them to discuss specific values. Your original training data is still governed by the setting.

## Persisting configuration

To avoid repeating the provider and credentials, store them once with the CLI:

```bash
skforecast-ai config set llm.provider "openai:gpt-4o-mini"
skforecast-ai config set llm.api_key "sk-..."
skforecast-ai config show
```

Settings are written to a TOML file (with restrictive permissions, since it may hold a key). Recognized keys include `llm.provider`, `llm.base_url`, `llm.api_key`, `llm.send_data_to_llm`, and `output.format`.

## Cost, tokens, and when to skip the LLM

The LLM is a paid, network-bound layer; the deterministic engine is neither. A few practical guidelines keep usage cheap and predictable:

- **The forecast itself never needs the LLM.** Predictions, metrics, and code come from the deterministic engine. Only `ask()` and `create_cv(prompt=...)` call the model. If you don't need an explanation, don't configure one, and you pay nothing.
- **Prompts are small by design.** Only the structural profile and modeling decisions are sent, not your raw data (see [Privacy](#privacy)). Skill grounding is selected by rule, not bulk-injected, so a typical `ask()` is on the order of a few thousand tokens.
- **Estimate before you send.** Use the skills layer to size a prompt without making a call:

  ```python
  from skforecast_ai.llm.skills import estimate_prompt_tokens, select_skills

  skills = select_skills(task_type="single_series", question="why this estimator?")
  print(estimate_prompt_tokens(skills))                       # grounding only
  print(estimate_prompt_tokens(skills, include_reference=True))  # + skforecast API reference
  ```

  `include_reference=True` (and `ask(..., include_reference=True)`) adds the full `skforecast` API reference, useful for detailed code questions, but it is the single largest contributor to prompt size. Leave it off for conceptual questions.
- **Pick a model that matches the question.** A small, fast model (e.g. `gpt-4o-mini`, `claude-3-5-haiku`, a local `ollama` model) is enough for most explanations. Reserve larger models for open-ended modeling advice.
- **Local and free.** `ollama` runs on your machine with no per-call cost; a good default when iterating.

!!! note "Retries"
    Each `ask()` call retries automatically (twice) on transient provider/parse errors before surfacing the failure. Persistent failures raise with the provider's error so you can see the cause.

## Next steps

- **[How it works & trust](how-it-works-and-trust.md)**: why enabling the LLM never changes your numbers.
- **[Human-in-the-loop](human-in-the-loop.md)**: use `ask()` suggestions to drive `refine_plan()` and re-run.
- **[Backtesting & validation](backtesting.md)**: let the model translate a deployment scenario into fold parameters with `create_cv(prompt=...)`.
- **[Troubleshooting](troubleshooting.md)**: fixes for `LLMRequiredError` and provider connection issues.
