################################################################################
#                               llm: provider                                  #
#                                                                              #
# LLM provider abstraction: parse model strings and create Pydantic AI models. #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

import urllib.error
import urllib.request
import warnings

from .._constants import OLLAMA_MAX_CONTEXT_TOKENS, RESERVED_RESPONSE_TOKENS

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"

# Environment variable pydantic-ai reads for each built-in provider when no
# explicit `api_key` is given. Bedrock uses the AWS credential chain and
# Ollama needs no credentials, so both map to None. `check_llm_config()`
# and the "Configuring the LLM" guide are written from this table.
PROVIDER_ENV_VARS: dict[str, str | None] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "bedrock": None,
    "ollama": None,
}

# Any of these set in the environment means boto3 has somewhere to start
# resolving Bedrock credentials. None set is not a failure: a shared
# credentials file or an instance role may still work.
BEDROCK_CREDENTIAL_ENV_VARS: tuple[str, ...] = (
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_ACCESS_KEY_ID",
    "AWS_PROFILE",
)

# Importable modules each provider needs on top of the base install.
# Providers not listed need only pydantic-ai.
PROVIDER_REQUIRED_MODULES: dict[str, tuple[str, ...]] = {
    "bedrock": ("pydantic_ai", "boto3"),
}
DEFAULT_REQUIRED_MODULES: tuple[str, ...] = ("pydantic_ai",)

# Providers whose pydantic-ai client takes no endpoint, so `base_url` has
# no effect on them.
PROVIDERS_IGNORING_BASE_URL: frozenset[str] = frozenset(
    {"google", "anthropic", "groq"}
)


def parse_model_string(llm: str | None) -> tuple[str | None, str | None]:
    """
    Parse an LLM provider string into provider and model name.

    Parameters
    ----------
    llm : str, None
        Provider string in the format `'provider:model_name'`.
        If None, returns `(None, None)` indicating Tier 0 mode.

    Returns
    -------
    provider : str, None
        Provider identifier (e.g. `'openai'`, `'ollama'`).
    model_name : str, None
        Model name (e.g. `'gpt-5.5'`, `'qwen3:8b'`).
    """
    if llm is None:
        return (None, None)

    if ":" not in llm:
        raise ValueError(
            f"Invalid LLM string '{llm}'. Expected format 'provider:model_name' "
            f"(e.g. 'openai:gpt-5.5', 'ollama:qwen3:8b')."
        )

    provider, model_name = llm.split(":", 1)

    if not model_name:
        raise ValueError(
            f"Model name is empty in '{llm}'. Expected format 'provider:model_name' "
            f"(e.g. 'openai:gpt-5.5', 'ollama:qwen3:8b')."
        )

    return (provider, model_name)


def create_model(
    llm: str | None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str | None:
    """
    Create a Pydantic AI model from an LLM provider string.

    Parameters
    ----------
    llm : str, None
        Provider string in the format `'provider:model_name'`.
        If None, returns None (Tier 0 deterministic mode).
    base_url : str, default None
        Custom endpoint for the provider. Its meaning depends on the
        prefix: the Ollama server URL (defaults to
        `'http://localhost:11434/v1'`), the AWS region for `bedrock`, and
        the endpoint of an OpenAI-compatible server for `openai` or any
        prefix not built in. Ignored by `google`, `anthropic` and `groq`,
        whose clients take no endpoint.
    api_key : str, default None
        Explicit API key for the provider. When None, Pydantic AI
        resolves credentials from environment variables (e.g.
        `OPENAI_API_KEY`, `GOOGLE_API_KEY`). When provided, the
        appropriate provider is instantiated with the key. Not needed
        for Ollama, nor for an OpenAI-compatible server reached through
        `base_url` that does not authenticate.

    Returns
    -------
    model : str, Model, None
        For cloud providers without `api_key` or `base_url`, returns the
        raw string (Pydantic AI resolves natively). When `api_key` or an
        applicable `base_url` is provided, returns a fully configured
        model instance. For Ollama, always returns an `OllamaModel`. For
        None input, returns None.
    """
    if llm is None:
        return None

    provider, model_name = parse_model_string(llm)

    if provider == "ollama":
        from pydantic_ai.models.ollama import OllamaModel
        from pydantic_ai.providers.ollama import OllamaProvider

        return OllamaModel(
            model_name=model_name,
            provider=OllamaProvider(
                base_url=base_url or DEFAULT_OLLAMA_BASE_URL,
                api_key="ollama",
            ),
        )

    if provider == "bedrock":
        from pydantic_ai.models.bedrock import BedrockConverseModel
        from pydantic_ai.providers.bedrock import BedrockProvider

        provider_kwargs = {}
        if base_url is not None:
            provider_kwargs["region_name"] = base_url
        if api_key is not None:
            provider_kwargs["api_key"] = api_key
        return BedrockConverseModel(
            model_name=model_name, provider=BedrockProvider(**provider_kwargs)
        )

    if api_key is None:
        if base_url is not None and provider not in PROVIDERS_IGNORING_BASE_URL:
            # An endpoint without a key: an OpenAI-compatible server (a
            # proxy, vLLM, LM Studio...). pydantic-ai reads OPENAI_API_KEY
            # when set and otherwise sends a placeholder key, which local
            # servers accept. Returning the bare string here would drop
            # the endpoint silently.
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            return OpenAIChatModel(
                model_name, provider=OpenAIProvider(base_url=base_url)
            )
        # Cloud providers: return string for Pydantic AI native resolution.
        # Pin the OpenAI prefix to 'openai-chat:' so the Chat Completions API
        # is used. From pydantic-ai v2.0 the bare 'openai:' prefix resolves to
        # the Responses API, which would silently change behavior.
        if provider == "openai":
            return f"openai-chat:{model_name}"
        return llm

    return _create_model_with_api_key(provider, model_name, api_key, base_url)


def _create_model_with_api_key(
    provider: str,
    model_name: str,
    api_key: str,
    base_url: str | None,
):
    """
    Instantiate a Pydantic AI model with an explicit API key.

    Parameters
    ----------
    provider : str
        Provider identifier (e.g. `'openai'`, `'google'`, `'anthropic'`).
    model_name : str
        Model name (e.g. `'gpt-5.5'`, `'gemini-3.5-flash'`).
    api_key : str
        API key for the provider.
    base_url : str, None
        Custom base URL. Used for OpenAI-compatible fallback providers.

    Returns
    -------
    model : Model
        Configured Pydantic AI model instance.
    """
    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        provider_kwargs = {"api_key": api_key}
        if base_url is not None:
            provider_kwargs["base_url"] = base_url
        return OpenAIChatModel(
            model_name, provider=OpenAIProvider(**provider_kwargs)
        )

    if provider == "google":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(
            model_name, provider=GoogleProvider(api_key=api_key)
        )

    if provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(
            model_name, provider=AnthropicProvider(api_key=api_key)
        )

    if provider == "groq":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.groq import GroqProvider

        return OpenAIChatModel(
            model_name, provider=GroqProvider(api_key=api_key)
        )

    # Unknown provider: assume OpenAI-compatible API
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider_kwargs = {"api_key": api_key}
    if base_url is not None:
        provider_kwargs["base_url"] = base_url
    return OpenAIChatModel(
        model_name, provider=OpenAIProvider(**provider_kwargs)
    )


def ensure_ollama_reachable(base_url: str | None = None) -> None:
    """
    Verify that an Ollama instance is reachable; raise on failure.

    Parameters
    ----------
    base_url : str, default None
        Base URL of the Ollama instance. Defaults to
        `'http://localhost:11434'`. The `/v1` suffix used for the
        OpenAI-compatible API is stripped automatically.

    Raises
    ------
    ConnectionError
        If the Ollama instance is not reachable.
    """
    url = base_url or DEFAULT_OLLAMA_BASE_URL
    # Strip /v1 suffix: the health endpoint is at the root
    url = url.rstrip("/").removesuffix("/v1")

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5):
            pass
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        raise ConnectionError(
            f"Ollama is not reachable at '{url}'. "
            f"Make sure Ollama is running: `ollama serve`. "
            f"Original error: {exc}"
        ) from exc


def build_ollama_settings(
    llm: str | None,
    estimated_prompt_tokens: int,
    user_message: str,
) -> dict | None:
    """
    Build Ollama-specific model settings with dynamic context sizing.

    Uses the pre-computed token estimate for system prompt content
    plus the user message length to determine the appropriate
    `num_ctx`. Clamps between 4096 and `OLLAMA_MAX_CONTEXT_TOKENS`.
    Warns when the prompt approaches the hard maximum. Returns None
    for non-Ollama providers.

    Parameters
    ----------
    llm : str, None
        LLM provider string in format `'provider:model_name'`, or None.
    estimated_prompt_tokens : int
        Estimated tokens for the system prompt (skills + reference).
    user_message : str
        The user message to send.

    Returns
    -------
    settings : dict, None
        Model settings dict or None for cloud providers.
    """
    if llm is None or not llm.startswith("ollama:"):
        return None

    user_tokens = len(user_message) // 4
    estimated_tokens = estimated_prompt_tokens + user_tokens
    requested_ctx = estimated_tokens + RESERVED_RESPONSE_TOKENS
    num_ctx = max(4096, min(requested_ctx, OLLAMA_MAX_CONTEXT_TOKENS))

    # The clamp is what causes truncation: the prompt plus the space
    # reserved for the answer no longer fits the window.
    if requested_ctx > OLLAMA_MAX_CONTEXT_TOKENS:
        warnings.warn(
            f"Estimated prompt size (~{estimated_tokens} tokens) exceeds "
            f"the Ollama context limit ({OLLAMA_MAX_CONTEXT_TOKENS}) once "
            f"room for the answer is reserved. Output may be truncated. "
            f"Consider using `skills=[]` or `include_reference=False`.",
            UserWarning,
            stacklevel=3,
        )

    return {
        "extra_body": {
            "keep_alive": "10m",
            "options": {"num_ctx": num_ctx},
        }
    }
