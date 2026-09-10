# Unit test provider skforecast_ai.llm

import re


import pytest

from skforecast_ai.llm.provider import (
    create_model,
    parse_model_string,
)


def test_parse_model_string_output_when_openai():
    """
    Test that an OpenAI provider string is correctly parsed into provider
    and model name.
    """
    result = parse_model_string("openai:gpt-4o-mini")
    assert result == ("openai", "gpt-4o-mini")


def test_parse_model_string_output_when_anthropic():
    """
    Test that an Anthropic provider string is correctly parsed.
    """
    result = parse_model_string("anthropic:claude-sonnet-4-5")
    assert result == ("anthropic", "claude-sonnet-4-5")


def test_parse_model_string_output_when_ollama_with_tag():
    """
    Test that an Ollama provider string with a model tag (double colon)
    splits only on the first colon, preserving the tag.
    """
    result = parse_model_string("ollama:qwen2.5:7b-instruct")
    assert result == ("ollama", "qwen2.5:7b-instruct")


def test_parse_model_string_output_when_none():
    """
    Test that None input returns (None, None) indicating Tier 0 mode.
    """
    result = parse_model_string(None)
    assert result == (None, None)


def test_parse_model_string_ValueError_when_no_prefix():
    """
    Test that a model string without a provider prefix raises ValueError
    with guidance on the expected format.
    """
    msg = re.escape(
        "Invalid LLM string 'gpt-4o-mini'. Expected format 'provider:model_name'"
    )
    with pytest.raises(ValueError, match=msg):
        parse_model_string("gpt-4o-mini")


def test_parse_model_string_output_when_unknown_provider():
    """
    Test that an unknown provider string is parsed without error,
    delegating validation to Pydantic AI at runtime.
    """
    result = parse_model_string("deepseek:deepseek-chat")
    assert result == ("deepseek", "deepseek-chat")


def test_create_model_output_when_none():
    """
    Test that create_model(None) returns None for Tier 0 mode.
    """
    result = create_model(None)
    assert result is None


def test_create_model_output_when_cloud_provider():
    """
    Test that create_model with an OpenAI provider string returns the
    'openai-chat:' prefixed string, pinning the Chat Completions API for
    Pydantic AI native resolution.
    """
    result = create_model("openai:gpt-4o-mini")
    assert result == "openai-chat:gpt-4o-mini"


def test_create_model_output_when_ollama_default_url():
    """
    Test that create_model with an Ollama string returns an OllamaModel
    configured with the default localhost base URL.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.ollama import OllamaModel

    result = create_model("ollama:qwen2.5:7b-instruct")
    assert isinstance(result, OllamaModel)
    assert result.model_name == "qwen2.5:7b-instruct"


def test_create_model_output_when_ollama_custom_url():
    """
    Test that create_model with an Ollama string and custom base_url
    returns an OllamaModel configured with the provided URL.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.ollama import OllamaModel

    custom_url = "http://192.168.1.50:11434/v1"
    result = create_model("ollama:qwen2.5:14b-instruct", base_url=custom_url)
    assert isinstance(result, OllamaModel)
    assert result.model_name == "qwen2.5:14b-instruct"


def test_create_model_output_when_unknown_provider():
    """
    Test that create_model with an unknown cloud provider returns the
    raw string, delegating resolution to Pydantic AI.
    """
    result = create_model("deepseek:deepseek-chat")
    assert result == "deepseek:deepseek-chat"


# =============================================================================
# Tests: create_model with api_key
# =============================================================================
def test_create_model_output_when_openai_with_api_key():
    """
    Test that create_model with an OpenAI string and api_key returns an
    OpenAIChatModel instance (not a raw string).
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.openai import OpenAIChatModel

    result = create_model("openai:gpt-4o-mini", api_key="sk-test-key")
    assert isinstance(result, OpenAIChatModel)
    assert result.model_name == "gpt-4o-mini"


def test_create_model_output_when_google_with_api_key():
    """
    Test that create_model with a Google string and api_key returns a
    GoogleModel instance.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.google import GoogleModel

    result = create_model("google:gemini-2.5-flash", api_key="test-key")
    assert isinstance(result, GoogleModel)


def test_create_model_output_when_anthropic_with_api_key():
    """
    Test that create_model with an Anthropic string and api_key returns
    an AnthropicModel instance.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.anthropic import AnthropicModel

    result = create_model("anthropic:claude-sonnet-4-5", api_key="sk-ant-test")
    assert isinstance(result, AnthropicModel)


def test_create_model_output_when_groq_with_api_key():
    """
    Test that create_model with a Groq string and api_key returns an
    OpenAIChatModel configured with GroqProvider.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.openai import OpenAIChatModel

    result = create_model("groq:llama-3.3-70b-versatile", api_key="gsk-test")
    assert isinstance(result, OpenAIChatModel)
    assert result.model_name == "llama-3.3-70b-versatile"


def test_create_model_output_when_ollama_with_api_key_ignored():
    """
    Test that create_model with Ollama ignores the api_key parameter
    and returns an OllamaModel with the dummy 'ollama' key.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.ollama import OllamaModel

    result = create_model("ollama:qwen2.5:7b-instruct", api_key="ignored-key")
    assert isinstance(result, OllamaModel)
    assert result.model_name == "qwen2.5:7b-instruct"


def test_create_model_output_when_unknown_provider_with_api_key():
    """
    Test that create_model with an unknown provider and api_key returns
    an OpenAIChatModel (OpenAI-compatible fallback).
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.openai import OpenAIChatModel

    result = create_model(
        "custom:my-model", api_key="key-123", base_url="http://my-api.com/v1"
    )
    assert isinstance(result, OpenAIChatModel)
    assert result.model_name == "my-model"


# =============================================================================
# Tests: ensure_ollama_reachable
# =============================================================================
def test_ensure_ollama_reachable_output_when_server_answers(monkeypatch):
    """
    Test that a reachable Ollama server passes silently and that the
    `/v1` suffix of the OpenAI-compatible base URL is stripped before
    the health check.
    """
    import urllib.request

    from skforecast_ai.llm.provider import ensure_ollama_reachable

    seen = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    ensure_ollama_reachable("http://localhost:11434/v1")

    assert seen["url"] == "http://localhost:11434"


def test_ensure_ollama_reachable_ConnectionError_when_server_is_down(monkeypatch):
    """
    Test that a server that does not answer is reported as
    ConnectionError with the URL and the hint to start Ollama.
    """
    import urllib.error
    import urllib.request

    from skforecast_ai.llm.provider import ensure_ollama_reachable

    def _fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    with pytest.raises(ConnectionError, match="ollama serve"):
        ensure_ollama_reachable()


# =============================================================================
# Tests: build_ollama_settings
# =============================================================================
def test_build_ollama_settings_output_when_cloud_provider():
    """
    Test that no model settings are built for a hosted provider.
    """
    from skforecast_ai.llm.provider import build_ollama_settings

    assert build_ollama_settings("openai:gpt-4o-mini", 1000, "hi") is None
    assert build_ollama_settings(None, 1000, "hi") is None


def test_build_ollama_settings_sizes_the_context_window():
    """
    Test that the Ollama context window covers the prompt, the message
    and the reserved answer, with a floor of 4096 tokens.
    """
    from skforecast_ai._constants import RESERVED_RESPONSE_TOKENS
    from skforecast_ai.llm.provider import build_ollama_settings

    small = build_ollama_settings("ollama:qwen2.5:7b-instruct", 100, "hi")
    assert small["extra_body"]["options"]["num_ctx"] == 4096

    message = "x" * 4000  # about 1000 tokens
    large = build_ollama_settings("ollama:qwen2.5:7b-instruct", 6000, message)
    assert large["extra_body"]["options"]["num_ctx"] == (
        6000 + 1000 + RESERVED_RESPONSE_TOKENS
    )
    assert large["extra_body"]["keep_alive"] == "10m"


def test_build_ollama_settings_warns_and_clamps_when_prompt_exceeds_window():
    """
    Test that a prompt larger than the Ollama window is clamped to the
    maximum and reported with a warning that suggests trimming skills.
    """
    from skforecast_ai._constants import OLLAMA_MAX_CONTEXT_TOKENS
    from skforecast_ai.llm.provider import build_ollama_settings

    with pytest.warns(UserWarning, match="skills=\\[\\]"):
        settings = build_ollama_settings(
            "ollama:qwen2.5:7b-instruct", OLLAMA_MAX_CONTEXT_TOKENS, "hi"
        )

    assert settings["extra_body"]["options"]["num_ctx"] == OLLAMA_MAX_CONTEXT_TOKENS


def test_create_model_output_when_openai_with_api_key_and_base_url():
    """
    Test that an OpenAI provider string with an explicit api_key and
    base_url is built as an OpenAI chat model pointing at that endpoint.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.openai import OpenAIChatModel

    result = create_model(
        "openai:gpt-4o-mini", api_key="test-key", base_url="http://proxy.local/v1"
    )

    assert isinstance(result, OpenAIChatModel)
    assert result.model_name == "gpt-4o-mini"
    assert "proxy.local" in str(result.base_url)
