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
    Test that create_model with a cloud provider string returns the
    raw string for Pydantic AI native resolution.
    """
    result = create_model("openai:gpt-4o-mini")
    assert result == "openai:gpt-4o-mini"


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
