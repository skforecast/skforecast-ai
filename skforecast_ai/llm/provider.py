"""LLM provider abstraction: parse model strings and create Pydantic AI models."""

import urllib.error
import urllib.request

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"


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
        Model name (e.g. `'gpt-4o-mini'`, `'qwen2.5:7b-instruct'`).
    """
    if llm is None:
        return (None, None)

    if ":" not in llm:
        raise ValueError(
            f"Invalid LLM string '{llm}'. Expected format 'provider:model_name' "
            f"(e.g. 'openai:gpt-4o-mini', 'ollama:qwen2.5:7b-instruct')."
        )

    provider, model_name = llm.split(":", 1)

    if not model_name:
        raise ValueError(
            f"Model name is empty in '{llm}'. Expected format 'provider:model_name' "
            f"(e.g. 'openai:gpt-4o-mini', 'ollama:qwen2.5:7b-instruct')."
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
        Custom base URL for the provider. Used for Ollama (defaults to
        `'http://localhost:11434/v1'`) and as the endpoint for unknown
        OpenAI-compatible providers when `api_key` is set.
    api_key : str, default None
        Explicit API key for the provider. When None, Pydantic AI
        resolves credentials from environment variables (e.g.
        `OPENAI_API_KEY`, `GOOGLE_API_KEY`). When provided, the
        appropriate provider is instantiated with the key.

    Returns
    -------
    model : str, Model, None
        For cloud providers without `api_key`, returns the raw string
        (Pydantic AI resolves natively). When `api_key` is provided,
        returns a fully configured model instance. For Ollama, always
        returns an `OllamaModel`. For None input, returns None.
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
        Model name (e.g. `'gpt-4o-mini'`, `'gemini-2.5-flash'`).
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
    # Strip /v1 suffix — the health endpoint is at the root
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
