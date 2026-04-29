# Phase 6 — LLM Provider Abstraction

## Goal

Implement the provider string parser and model factory so that
`ForecastingAssistant(llm="openai:gpt-4o-mini")` and
`ForecastingAssistant(llm="ollama:qwen2.5:7b-instruct")` resolve to the
correct Pydantic AI model. No agent logic yet — only model instantiation
and connectivity validation.

## Files to Create

```
skforecast_ai/llm/__init__.py     (re-exports)
skforecast_ai/llm/provider.py     (parse_model, create_model, check_connectivity)
tests/test_llm_provider.py
```

## Public API

```python
from skforecast_ai.llm.provider import create_model

model = create_model("openai:gpt-4o-mini")
model = create_model("anthropic:claude-sonnet-4-5")
model = create_model("ollama:qwen2.5:7b-instruct")
model = create_model("ollama:qwen2.5:14b-instruct", base_url="http://192.168.1.50:11434/v1")
model = create_model(None)  # Returns None → Tier 0
```

## Logic to Implement

| Function | Responsibility |
|----------|----------------|
| `parse_model_string(s)` | Split `"provider:model_name"` → `(provider, model_name)`. Handle Ollama's double-colon (`"ollama:qwen2.5:7b-instruct"` → provider=`"ollama"`, model=`"qwen2.5:7b-instruct"`) |
| `create_model(llm, base_url=None)` | Dispatch to correct Pydantic AI `Model` class. Return `None` for `llm=None` |
| `check_ollama_reachable(base_url)` | Quick HTTP check. Return actionable error if unreachable |

## Supported Provider Mapping

| Prefix | Pydantic AI class | Notes |
|--------|-------------------|-------|
| `openai:` | `OpenAIModel` | Uses `OPENAI_API_KEY` env var |
| `anthropic:` | `AnthropicModel` | Uses `ANTHROPIC_API_KEY` env var |
| `google:` | `GeminiModel` | Uses `GOOGLE_API_KEY` env var |
| `groq:` | `GroqModel` | Uses `GROQ_API_KEY` env var |
| `mistral:` | `MistralModel` | Uses `MISTRAL_API_KEY` env var |
| `ollama:` | `OpenAIModel` + custom `base_url` | Default `http://localhost:11434/v1`, key=`"ollama"` |
| `None` | `None` | Tier 0 mode |

## Tests (tests/test_llm_provider.py)

| Test | What it validates |
|------|-------------------|
| `test_parse_openai` | `"openai:gpt-4o-mini"` → `("openai", "gpt-4o-mini")` |
| `test_parse_ollama_with_tag` | `"ollama:qwen2.5:7b-instruct"` → `("ollama", "qwen2.5:7b-instruct")` |
| `test_parse_none` | `None` → `(None, None)` |
| `test_parse_invalid_format` | `"gpt-4o-mini"` (no prefix) raises `ValueError` |
| `test_create_model_openai` | Returns an `OpenAIModel` instance (mocked) |
| `test_create_model_ollama_default_url` | Uses `localhost:11434` |
| `test_create_model_ollama_custom_url` | Uses provided `base_url` |
| `test_create_model_none_returns_none` | `create_model(None)` → `None` |
| `test_unsupported_provider_error` | `"foobar:model"` raises `ValueError` |

## Done Criteria

- [ ] `from skforecast_ai.llm.provider import create_model` works
- [ ] All supported provider strings resolve to correct model type
- [ ] Ollama base_url is configurable
- [ ] `None` input returns `None` (Tier 0)
- [ ] Invalid inputs raise clear `ValueError` with guidance
- [ ] `pytest tests/test_llm_provider.py` passes (≥ 8 tests)
