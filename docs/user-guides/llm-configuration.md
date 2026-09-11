# Configuring the LLM

The LLM layer of **skforecast-ai** is optional. It explains decisions, refines lags and window features on request, and translates a deployment scenario into a cross-validation strategy, but it never changes a forecast: every number comes from the deterministic engine, whether or not a model is configured. This page covers everything needed to connect one: the model string, the credentials of each provider, what `base_url` means, local models, what leaves your machine, and what to do when a call fails.

The whole configuration is the four arguments of `ForecastingAssistant`: `llm`, `base_url`, `api_key` and `send_data_to_llm`. It needs the LLM extra:

```bash
pip install "skforecast-ai[llm]"
```

See [How to install](../quick-start/how-to-install.md#optional-dependencies) for the provider-specific extras.

---

## Quickstart

```bash
export OPENAI_API_KEY="sk-..."
```

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant(llm="openai:gpt-5.5")
answer = assistant.ask("When should I prefer a direct strategy over a recursive one?")
answer
```

Nothing is validated when the assistant is created. The provider string, the credentials and the model name are checked on the first call that needs the LLM: `ask()`, `refine_plan(prompt=...)` or `create_cv(prompt=...)`. To find out before that whether the configuration works, use [`check_llm()`](#check-your-configuration).

---

## Model strings

`llm` is a string in the format `provider:model`, split on the first colon. A model name can therefore contain colons of its own, as Ollama tags do: `ollama:qwen3:8b` names the provider `ollama` and the model `qwen3:8b`. The separator is a colon, as in pydantic-ai and LangChain, not the slash used by LiteLLM or DSPy.

A string without a colon, or with nothing after it, raises `ValueError` as soon as the LLM is first used:

```
Invalid LLM string 'gpt-5.5'. Expected format 'provider:model_name' (e.g. 'openai:gpt-5.5', 'ollama:qwen3:8b').
```

One valid string per provider is listed in the table of the next section.

!!! note "Other pydantic-ai providers"
    A prefix that is not built in and has no `base_url` is handed to [pydantic-ai](https://pydantic.dev/docs/ai/models/overview/) unchanged, so its other providers (`mistral:`, `cohere:`, `openrouter:`, ...) work when their own environment variable is set. `check_llm()` reports these as resolved at call time. `openai:` is pinned to the Chat Completions API rather than the Responses API that pydantic-ai 2 would pick for the bare prefix.

---

## Providers and credentials

When `api_key` is None, the credentials are resolved by pydantic-ai from the environment variable of the provider. skforecast-ai never reads a key itself and never stores one in a result.

| Prefix | Example | Credentials when `api_key` is None | What `base_url` means | Extra | Docs |
|---|---|---|---|---|---|
| `openai:` | `openai:gpt-5.5` | `OPENAI_API_KEY` | Endpoint of an OpenAI-compatible server. When None, `OPENAI_BASE_URL` if set | `[llm]` | [pydantic-ai](https://pydantic.dev/docs/ai/models/openai/) |
| `anthropic:` | `anthropic:claude-sonnet-5` | `ANTHROPIC_API_KEY` | Ignored | `[llm]` | [pydantic-ai](https://pydantic.dev/docs/ai/models/anthropic/) |
| `google:` | `google:gemini-3.5-flash` | `GOOGLE_API_KEY` (`GEMINI_API_KEY` still accepted) | Ignored | `[llm]` | [pydantic-ai](https://pydantic.dev/docs/ai/models/google/) |
| `groq:` | `groq:<model>` ([model list](https://console.groq.com/docs/models)) | `GROQ_API_KEY` | Ignored | `[llm]` | [pydantic-ai](https://pydantic.dev/docs/ai/models/groq/) |
| `bedrock:` | `bedrock:eu.anthropic.claude-sonnet-4-6` | AWS credential chain: `AWS_BEARER_TOKEN_BEDROCK`, or `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, or a profile or instance role | AWS region. When None, `AWS_DEFAULT_REGION` or the profile | `[bedrock]` | [pydantic-ai](https://pydantic.dev/docs/ai/models/bedrock/) |
| `ollama:` | `ollama:qwen3:8b` | None needed; `api_key` is ignored | Server URL, default `http://localhost:11434/v1` | `[llm]` | [pydantic-ai](https://pydantic.dev/docs/ai/models/ollama/) |
| other | `vllm:my-model` with `base_url` | With `base_url`: none needed (`OPENAI_API_KEY` if set). Without: the provider's own variable, read by pydantic-ai | Endpoint of an OpenAI-compatible server, see [below](#any-openai-compatible-endpoint) | `[llm]` | [pydantic-ai](https://pydantic.dev/docs/ai/models/openai/#openai-compatible-models) |

=== "Cloud provider"

    The same pattern for OpenAI, Anthropic, Google and Groq: export the variable of the provider, pass the string.

    ```bash
    export OPENAI_API_KEY="sk-..."
    ```

    ```python
    assistant = ForecastingAssistant(llm="openai:gpt-5.5")
    ```

=== "Bedrock"

    ```bash
    pip install "skforecast-ai[bedrock]"
    export AWS_ACCESS_KEY_ID="..."
    export AWS_SECRET_ACCESS_KEY="..."
    ```

    ```python
    assistant = ForecastingAssistant(
        llm      = "bedrock:eu.anthropic.claude-sonnet-4-6",
        base_url = "eu-west-1",   # the AWS region
    )
    ```

=== "Ollama"

    ```bash
    ollama pull qwen3:8b
    ollama serve
    ```

    ```python
    assistant = ForecastingAssistant(llm="ollama:qwen3:8b")
    ```

!!! note "Credential resolution order"
    1. An explicit `api_key` passed to `ForecastingAssistant` (or `--api-key` in the CLI). The environment is not consulted.
    2. The environment variable of the provider, read by pydantic-ai.
    3. For Bedrock only, the rest of the AWS credential chain: shared credentials file, profile, instance role.
    4. Otherwise the first LLM call fails: `ask()` raises `LLMCallError`, `refine_plan()` and `create_cv()` warn and return their deterministic result.

    Passing `api_key` explicitly is the right choice in notebooks and multi-tenant code; environment variables are the right choice for scripts and the CLI.

The model and its agents are created on the first call and cached in the assistant. To switch provider, model or credentials, create a new `ForecastingAssistant`.

---

## What base_url means

!!! warning "base_url is overloaded"
    The prefix decides what the argument means: the endpoint of an OpenAI-compatible server (`openai:` and prefixes that are not built in), the server URL for `ollama:` (default `http://localhost:11434/v1`; `OLLAMA_BASE_URL` is not consulted), or the AWS region for `bedrock:`. For `google:`, `anthropic:` and `groq:` it is ignored, because their clients take no endpoint; `check_llm()` says so when a value is given.

---

## Local models with Ollama

Ollama runs models on your machine, so nothing leaves it. Three steps before the first call:

```bash
ollama pull qwen3:8b                          # download the model once
ollama serve                                  # start the server (if not running as a service)
curl http://localhost:11434/v1/models         # verify: lists the models available
```

```python
assistant = ForecastingAssistant(llm="ollama:qwen3:8b")
assistant.check_llm()
```

Facts worth knowing:

- `api_key` is ignored; the server does not authenticate. To reach an Ollama server on another machine pass `base_url="http://<host>:11434/v1"`. A `404` from the server usually means the `/v1` suffix is missing.
- Before each `ask()` the assistant contacts the server (a 5 second `GET`). If it does not answer, `ask()` raises `LLMCallError` wrapping a `ConnectionError` that says `Make sure Ollama is running: ollama serve`. `refine_plan()` and `create_cv()` have no pre-flight check: with the server down they fall back to their deterministic result with a `UserWarning`.
- The context window is sized per call: the prompt plus 2048 tokens reserved for the answer, between 4096 and 32768 tokens (`num_ctx`), and the model is kept loaded for ten minutes between calls. When a prompt does not fit, a `UserWarning` says `Estimated prompt size ... exceeds the Ollama context limit ... Output may be truncated` and suggests `skills=[]` or `include_reference=False` in `ask()`.

!!! tip "Small models and structured output"
    `refine_plan(prompt=...)` and `create_cv(prompt=...)` require the model to answer with a JSON object that matches a schema, and validate it. A model that cannot do so reliably is sent the validation error, and after three attempts the assistant returns the deterministic result with a `UserWarning`. Models of 7B parameters or more, instruction tuned, are a safe starting point for local use; `ask()` is less demanding than the two structured steps.

---

## Any OpenAI-compatible endpoint

Any prefix that is not built in, combined with `base_url`, is routed to the OpenAI client at that endpoint. The prefix is a label of your choice; `api_key` is optional (`OPENAI_API_KEY` is used when set, and a placeholder otherwise, which local servers accept).

```python
# vLLM
assistant = ForecastingAssistant(llm="vllm:my-model", base_url="http://localhost:8000/v1")

# LM Studio
assistant = ForecastingAssistant(llm="lmstudio:my-model", base_url="http://localhost:1234/v1")

# OpenRouter
assistant = ForecastingAssistant(
    llm      = "openrouter:google/gemini-3.5-flash",
    base_url = "https://openrouter.ai/api/v1",
    api_key  = os.environ["OPENROUTER_API_KEY"],
)

# LiteLLM proxy
assistant = ForecastingAssistant(llm="litellm:gpt-5.5", base_url="http://localhost:4000")
```

`openai:` with `base_url` behaves the same way, so a proxy in front of OpenAI can keep the `openai:` prefix.

---

## Check your configuration

`check_llm()` reports how the configuration resolves, without calling the model, and never prints a credential value:

```python
assistant = ForecastingAssistant(llm="openai:gpt-5.5")
assistant.check_llm()
```

```
                       LLM Configuration Check
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Check        ┃ Value                                               ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Status       │ not ok                                              │
│ Provider     │ openai                                              │
│ Model        │ gpt-5.5                                             │
│ Credentials  │ OPENAI_API_KEY (not set)                            │
│              │ pydantic-ai reads OPENAI_API_KEY.                   │
│ Base URL     │ None                                                │
│              │ Provider default (OPENAI_BASE_URL when set).        │
│ Dependencies │ installed                                           │
│ Test call    │ skipped                                             │
│ Error        │ OPENAI_API_KEY is not set and no api_key was given. │
└──────────────┴─────────────────────────────────────────────────────┘
```

The result is an `LLMCheckResult`: `result.ok` summarizes it, `result.error` holds the first failure, and the other attributes (`provider`, `model_name`, `credential_source`, `env_var`, `env_var_set`, `base_url`, `base_url_note`, `dependencies_ok`, `missing_dependencies`, `reachable`, `call_ok`) are the rows of the table. With `test_call=True`, and only when the static checks pass, a one-line prompt is sent to the model through the same agent `ask()` uses, without skills or data, and the outcome is reported in `call_ok`:

```python
result = assistant.check_llm(test_call=True)
result.ok, result.call_ok, result.error
```

The CLI command does the same with the flags, environment variables and config file of the CLI, and exits with code 1 when the check fails:

```bash
skforecast-ai check-llm --llm openai:gpt-5.5
skforecast-ai check-llm --test-call --format json
```

---

## Skills and the API reference

`ask()` briefs the model with skill documents chosen for the question: skforecast know-how synced from the skforecast repository. With `skills=None`, the default, the selection starts from the task type of the context and adds the skills matched by keywords in the question; pass a list to choose them yourself, or `skills=[]` to send none. `include_reference=True` adds the skforecast API reference (about 8500 tokens) on top; it is off by default. The skill content of one request is capped at 20 000 tokens for every provider, and additionally budgeted against the 32768 token window for Ollama. `AskResult.skills` records what was actually sent. The names, the selection rules and examples are in [Skills: how the LLM is briefed](skills.md).

---

## What is sent to the LLM

`send_data_to_llm` is False by default. The lists below are what actually leaves your machine.

**Always sent**, whatever the flag:

- The dataset summary: number of observations and series, frequency, date range, per-series minimum, maximum, mean and standard deviation of the target, missing value counts, index irregularities.
- The profile decision: the deterministic explanation, the significant lags found by the partial autocorrelation, the suggested window and calendar features.
- The plan: steps, forecaster, estimator, lags, window features, interval, metric, preprocessing.
- The cross-validation configuration (`cv_config`), when the context has one.
- A description of the generated script (mode, files read, variables, imports, line count). The script itself is never sent; the model is told it is available to you as `result.code`.
- The metrics table of a result, and the leaderboard (top 15 rows) and failure reasons of a comparison.
- Your question and the selected skills.

**Sent only for results**, that is, when `context` is a `ForecastResult`, `BacktestResult` or `ComparisonResult`:

- The predictions of the result: in full when there are 30 rows or fewer, otherwise the first and last five plus per-column statistics. A question about a result cannot be answered from summary statistics alone, so these are sent even with `send_data_to_llm=False`; in that case `ask()` emits `DataSentToLLMWarning` to make it visible. Setting `send_data_to_llm=True` acknowledges it and silences the warning. A profile, a `CodeGenerationResult` or a `CVResult` never trigger it.

**Never sent**:

- The raw observations of your dataset, in any mode. A profile holds summary statistics only, and a result holds the model's output, not the data it was fitted on.
- The contents or path of your files.
- Credentials.
- The generated code.

`refine_plan(prompt=...)` and `create_cv(prompt=...)` send even less: observation count, frequency, date range, horizon, the current lags and window features, your prompt, and the skills the step needs.

If nothing may leave your machine at all, run a [local model with Ollama](#local-models-with-ollama): the same payloads go to `localhost`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `LLMRequiredError: ask() requires an LLM` | The assistant was created without `llm` | Pass `llm="provider:model"` (CLI: `--llm`, `SKFORECAST_AI_LLM` or `config set llm.provider`) |
| `ModuleNotFoundError: No module named 'pydantic_ai'` | The LLM extra is not installed | `pip install "skforecast-ai[llm]"` (`[bedrock]` for Bedrock) |
| `ValueError: Invalid LLM string ...` or `Model name is empty ...` | No colon, or nothing after it | Use `provider:model` |
| `LLMCallError` wrapping `ConnectionError: Ollama is not reachable` | The Ollama server is down or `base_url` is wrong | `ollama serve`; check the URL ends in `/v1` |
| `LLMCallError` wrapping a `401` or `UserError: Set the OPENAI_API_KEY environment variable` | Missing or wrong key, or the wrong variable name | Set the variable of the provider, or pass `api_key`; run `check_llm()` |
| `LLMCallError` wrapping a `404` | Unknown model name, or an OpenAI-compatible server without `/v1` in `base_url` | Check the model list of the provider and the URL |
| `LLMCallError` wrapping a `429` | Rate limit of the provider | Retry later, or use a smaller model |
| `UserWarning: LLM plan refinement failed ... Returning deterministic plan.` | The model could not produce valid lags or window features, or the call failed | The deterministic plan is valid; retry with a stronger model or give lags explicitly |
| `UserWarning: LLM CV configuration failed after 3 attempts ... Falling back to deterministic defaults.` | Same, for `create_cv(prompt=...)` | The deterministic strategy is valid; pass the fold parameters explicitly |
| `UserWarning: Estimated prompt size ... exceeds the Ollama context limit` | The prompt does not fit the 32768 token window | `skills=[]` or `include_reference=False` in `ask()` |

`LLMCallError` keeps the provider exception as `original_error`, so `except LLMCallError as exc: exc.original_error` gives the full detail. Every error and warning of the package is listed in [Exceptions and warnings](../api/exceptions.md).

---

## In the CLI

The same strings and arguments apply: `--llm`, `--base-url` and `--api-key` on `ask`, `refine-plan`, `backtest` and `check-llm`. Each one can also come from an environment variable (`SKFORECAST_AI_LLM`, `SKFORECAST_AI_BASE_URL`, `SKFORECAST_AI_API_KEY`) or from the config file (`llm.provider`, `llm.base_url`, `llm.api_key`); the flag wins over the variable, and the variable over the file. See [LLM resolution precedence](cli-usage.md#llm-resolution-precedence) for the full table. The CLI `ask` command only ever explains profiles, plans and generated scripts, so it never sends observations, whatever `--send-data-to-llm` says.
