"""LLM provider abstraction: parse model strings and create Pydantic AI models."""

import urllib.error
import urllib.request

SUPPORTED_PROVIDERS = frozenset(
    {"openai", "anthropic", "google", "groq", "mistral", "ollama"}
)

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

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported provider '{provider}'. "
            f"Supported providers: {sorted(SUPPORTED_PROVIDERS)}."
        )

    return (provider, model_name)


def create_model(llm: str | None, base_url: str | None = None):
    """
    Create a Pydantic AI model from an LLM provider string.

    Parameters
    ----------
    llm : str, None
        Provider string in the format `'provider:model_name'`.
        If None, returns None (Tier 0 deterministic mode).
    base_url : str, default None
        Custom base URL for the provider. Only used for Ollama.
        Defaults to `'http://localhost:11434/v1'` for Ollama.

    Returns
    -------
    model : str, OllamaModel, None
        For cloud providers, returns the raw string (Pydantic AI resolves
        natively). For Ollama, returns an `OllamaModel` instance configured
        with the appropriate base URL. For None input, returns None.
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

    # Cloud providers: return string for Pydantic AI native resolution
    return llm


def check_ollama_reachable(base_url: str | None = None) -> bool:
    """
    Check if an Ollama instance is reachable.

    Parameters
    ----------
    base_url : str, default None
        Base URL of the Ollama instance. Defaults to
        `'http://localhost:11434'`. The `/v1` suffix used for the
        OpenAI-compatible API is stripped automatically.

    Returns
    -------
    reachable : bool
        True if the Ollama instance responds.
    """
    url = base_url or DEFAULT_OLLAMA_BASE_URL
    # Strip /v1 suffix — the health endpoint is at the root
    url = url.rstrip("/").removesuffix("/v1")

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5):
            return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        raise ConnectionError(
            f"Ollama is not reachable at '{url}'. "
            f"Make sure Ollama is running: `ollama serve`. "
            f"Original error: {exc}"
        ) from exc
