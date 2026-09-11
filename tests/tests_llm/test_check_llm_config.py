# Unit test check_llm_config skforecast_ai.llm

import re

import pytest

from skforecast_ai.llm import diagnostics
from skforecast_ai.llm.diagnostics import check_llm_config
from skforecast_ai.schemas import LLMCheckResult


CLOUD_PROVIDERS = [
    ("openai:gpt-5.5", "openai", "gpt-5.5", "OPENAI_API_KEY"),
    ("anthropic:claude-sonnet-5", "anthropic", "claude-sonnet-5", "ANTHROPIC_API_KEY"),
    ("google:gemini-3.5-flash", "google", "gemini-3.5-flash", "GOOGLE_API_KEY"),
    ("groq:some-model", "groq", "some-model", "GROQ_API_KEY"),
]

AWS_ENV_VARS = (
    "AWS_BEARER_TOKEN_BEDROCK", "AWS_ACCESS_KEY_ID", "AWS_PROFILE",
    "AWS_SECRET_ACCESS_KEY",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    """
    Remove every provider variable so each test controls what is set.
    """
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
                 "GROQ_API_KEY", "OPENAI_BASE_URL", *AWS_ENV_VARS):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("llm, provider, model_name, env_var", CLOUD_PROVIDERS)
def test_check_llm_config_output_when_env_var_set(
    monkeypatch, llm, provider, model_name, env_var
):
    """
    Test that a built-in cloud provider whose environment variable is set
    reports the variable, that it is set, and no error.
    """
    monkeypatch.setenv(env_var, "key-marker")

    result = check_llm_config(llm)

    assert isinstance(result, LLMCheckResult)
    assert result.provider == provider
    assert result.model_name == model_name
    assert result.credential_source == "env_var"
    assert result.env_var == env_var
    assert result.env_var_set is True
    assert result.credential_note == f"pydantic-ai reads {env_var}."
    assert result.error is None
    assert result.ok is True


@pytest.mark.parametrize("llm, provider, model_name, env_var", CLOUD_PROVIDERS)
def test_check_llm_config_output_when_env_var_not_set(
    llm, provider, model_name, env_var
):
    """
    Test that a built-in cloud provider without its environment variable
    and without api_key is reported as not ok with the variable named.
    """
    result = check_llm_config(llm)

    assert result.credential_source == "env_var"
    assert result.env_var == env_var
    assert result.env_var_set is False
    assert result.error == f"{env_var} is not set and no api_key was given."
    assert result.ok is False


def test_check_llm_config_output_when_api_key_given():
    """
    Test that an explicit api_key makes the environment irrelevant: the
    variable is named but not consulted, and the check passes.
    """
    result = check_llm_config("openai:gpt-5.5", api_key="explicit-marker")

    assert result.credential_source == "api_key"
    assert result.env_var == "OPENAI_API_KEY"
    assert result.env_var_set is None
    assert result.credential_note == (
        "Explicit api_key given; the environment is not consulted."
    )
    assert result.ok is True


def test_check_llm_config_output_when_ollama_default_url(monkeypatch):
    """
    Test that Ollama needs no credentials, gets the default server URL
    and is reported reachable when the server answers.
    """
    monkeypatch.setattr(diagnostics, "ensure_ollama_reachable", lambda url: None)

    result = check_llm_config("ollama:qwen3:8b")

    assert result.provider == "ollama"
    assert result.model_name == "qwen3:8b"
    assert result.credential_source == "none"
    assert result.env_var is None
    assert result.env_var_set is None
    assert result.credential_note == "Ollama needs no credentials; api_key is ignored."
    assert result.base_url == "http://localhost:11434/v1"
    assert result.base_url_note == "Ollama server URL (default)."
    assert result.reachable is True
    assert result.ok is True


def test_check_llm_config_output_when_ollama_custom_url(monkeypatch):
    """
    Test that a custom Ollama base_url is used as given and passed to the
    reachability check.
    """
    seen = {}
    monkeypatch.setattr(
        diagnostics, "ensure_ollama_reachable", lambda url: seen.setdefault("url", url)
    )

    result = check_llm_config("ollama:qwen3:8b", base_url="http://gpu-box:11434/v1")

    assert result.base_url == "http://gpu-box:11434/v1"
    assert result.base_url_note == "Ollama server URL."
    assert seen["url"] == "http://gpu-box:11434/v1"
    assert result.reachable is True


def test_check_llm_config_output_when_ollama_unreachable(monkeypatch):
    """
    Test that an Ollama server that does not answer is reported, not
    raised, with the message of the connection error.
    """
    def _fail(url):
        raise ConnectionError(
            "Ollama is not reachable at 'http://localhost:11434'. "
            "Make sure Ollama is running: `ollama serve`."
        )

    monkeypatch.setattr(diagnostics, "ensure_ollama_reachable", _fail)

    result = check_llm_config("ollama:qwen3:8b")

    assert result.reachable is False
    assert result.error == (
        "Ollama is not reachable at 'http://localhost:11434'. "
        "Make sure Ollama is running: `ollama serve`."
    )
    assert result.ok is False


def test_check_llm_config_output_when_bedrock_with_region(monkeypatch):
    """
    Test that Bedrock reports the AWS credential chain, base_url as the
    region, and env_var_set True when an AWS variable is present.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "aws-marker")

    result = check_llm_config(
        "bedrock:eu.anthropic.claude-sonnet-4-6", base_url="eu-west-1"
    )

    assert result.credential_source == "aws_credential_chain"
    assert result.env_var is None
    assert result.env_var_set is True
    assert result.base_url == "eu-west-1"
    assert result.base_url_note == "AWS region."
    assert result.ok is True


def test_check_llm_config_output_when_bedrock_without_aws_variables():
    """
    Test that Bedrock without any AWS variable is not a failure: the
    credential chain may still resolve a profile or an instance role.
    """
    result = check_llm_config("bedrock:eu.anthropic.claude-sonnet-4-6")

    assert result.credential_source == "aws_credential_chain"
    assert result.env_var_set is None
    assert result.base_url is None
    assert result.base_url_note == (
        "AWS region; AWS_DEFAULT_REGION or the AWS profile when None."
    )
    assert result.ok is True


def test_check_llm_config_output_when_bedrock_missing_boto3(monkeypatch):
    """
    Test that a missing boto3 is reported for Bedrock with the extra that
    installs it.
    """
    monkeypatch.setattr(
        diagnostics, "_is_importable", lambda module: module != "boto3"
    )

    result = check_llm_config("bedrock:eu.anthropic.claude-sonnet-4-6")

    assert result.dependencies_ok is False
    assert result.missing_dependencies == ['boto3 (pip install "skforecast-ai[bedrock]")']
    assert result.error == (
        'Missing dependencies: boto3 (pip install "skforecast-ai[bedrock]")'
    )
    assert result.ok is False


def test_check_llm_config_output_when_pydantic_ai_missing(monkeypatch):
    """
    Test that a missing pydantic-ai is reported with the `llm` extra and
    fails the check, while the other fields are still filled.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "key-marker")
    monkeypatch.setattr(diagnostics, "_is_importable", lambda module: False)

    result = check_llm_config("openai:gpt-5.5")

    assert result.provider == "openai"
    assert result.env_var_set is True
    assert result.dependencies_ok is False
    assert result.missing_dependencies == [
        'pydantic_ai (pip install "skforecast-ai[llm]")'
    ]
    assert result.ok is False


def test_check_llm_config_output_when_openai_with_base_url(monkeypatch):
    """
    Test that a base_url for openai is reported as an OpenAI-compatible
    endpoint, with or without api_key.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "key-marker")

    result = check_llm_config("openai:gpt-5.5", base_url="http://proxy.local/v1")

    assert result.base_url == "http://proxy.local/v1"
    assert result.base_url_note == "OpenAI-compatible endpoint."
    assert result.ok is True


def test_check_llm_config_output_when_openai_without_base_url(monkeypatch):
    """
    Test that openai without base_url reports the provider default and
    names the environment variable that can override it.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "key-marker")

    result = check_llm_config("openai:gpt-5.5")

    assert result.base_url is None
    assert result.base_url_note == "Provider default (OPENAI_BASE_URL when set)."


@pytest.mark.parametrize(
    "llm", ["google:gemini-3.5-flash", "anthropic:claude-sonnet-5", "groq:some-model"]
)
def test_check_llm_config_output_when_base_url_ignored(llm):
    """
    Test that google, anthropic and groq drop base_url and say so.
    """
    provider = llm.split(":", 1)[0]

    result = check_llm_config(llm, base_url="http://ignored.local", api_key="k")

    assert result.base_url is None
    assert result.base_url_note == (
        f"base_url is ignored for '{provider}'; its client takes no endpoint."
    )
    assert result.ok is True


def test_check_llm_config_output_when_unknown_provider():
    """
    Test that a prefix that is not built in is reported as resolved by
    pydantic-ai at call time, without failing the static check.
    """
    result = check_llm_config("mistral:mistral-large")

    assert result.provider == "mistral"
    assert result.credential_source == "unknown"
    assert result.env_var is None
    assert result.env_var_set is None
    assert "not a built-in provider" in result.credential_note
    assert result.base_url is None
    assert result.base_url_note is None
    assert result.ok is True


def test_check_llm_config_output_when_unknown_provider_with_base_url():
    """
    Test that a prefix that is not built in, combined with base_url, is
    reported as an OpenAI-compatible endpoint.
    """
    result = check_llm_config("vllm:my-model", base_url="http://localhost:8000/v1")

    assert result.base_url == "http://localhost:8000/v1"
    assert result.base_url_note == "OpenAI-compatible endpoint."
    assert result.ok is True


@pytest.mark.parametrize(
    "llm, message",
    [
        ("gpt-5.5", "Invalid LLM string 'gpt-5.5'. Expected format 'provider:model_name'"),
        ("openai:", "Model name is empty in 'openai:'. Expected format 'provider:model_name'"),
    ],
)
def test_check_llm_config_output_when_invalid_string(llm, message):
    """
    Test that an invalid provider string is reported, not raised, with
    the message `parse_model_string` would have raised.
    """
    result = check_llm_config(llm)

    assert result.provider is None
    assert result.model_name is None
    assert re.match(re.escape(message), result.error)
    assert result.ok is False


def test_check_llm_config_never_exposes_credentials(monkeypatch):
    """
    Test that neither the environment value nor the explicit api_key
    appears in the rendered result or in its JSON dump.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-env-marker")

    for result in (
        check_llm_config("openai:gpt-5.5"),
        check_llm_config("openai:gpt-5.5", api_key="sk-explicit-marker"),
    ):
        rendered = str(result)
        dumped = result.model_dump_json()
        assert "sk-secret-env-marker" not in rendered
        assert "sk-secret-env-marker" not in dumped
        assert "sk-explicit-marker" not in rendered
        assert "sk-explicit-marker" not in dumped
