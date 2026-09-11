# Unit test check_llm ForecastingAssistant

import re

import pytest

from skforecast_ai import ForecastingAssistant, LLMRequiredError
from skforecast_ai.schemas import LLMCheckResult

from tests.fixtures_assistant import patch_agent


@pytest.fixture(autouse=True)
def _openai_key(monkeypatch):
    """
    Give the static checks a set OPENAI_API_KEY so they pass by default.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "key-marker")


def test_check_llm_LLMRequiredError_when_no_llm():
    """
    Test that check_llm() without an LLM raises LLMRequiredError naming
    the method.
    """
    assistant = ForecastingAssistant()
    msg = re.escape(
        "`check_llm()` requires an LLM. Pass `llm=...` when creating "
        "ForecastingAssistant."
    )
    with pytest.raises(LLMRequiredError, match=msg):
        assistant.check_llm()


def test_check_llm_output_without_test_call():
    """
    Test that the static checks run without creating the agent and
    report the call as skipped.
    """
    assistant = ForecastingAssistant(llm="openai:gpt-5.5")

    result = assistant.check_llm()

    assert isinstance(result, LLMCheckResult)
    assert result.provider == "openai"
    assert result.model_name == "gpt-5.5"
    assert result.env_var_set is True
    assert result.call_ok is None
    assert result.ok is True
    assert assistant._agent is None


def test_check_llm_output_when_test_call_succeeds(monkeypatch):
    """
    Test that test_call=True sends the fixed one-line prompt through the
    ask agent, without skills, and reports the call as ok.
    """
    assistant = ForecastingAssistant(llm="openai:gpt-5.5")
    capture = {}
    patch_agent(monkeypatch, assistant, output="OK", capture=capture)

    result = assistant.check_llm(test_call=True)

    assert capture["message"] == "Reply with the single word OK."
    assert result.call_ok is True
    assert result.error is None
    assert result.ok is True


def test_check_llm_output_when_test_call_fails(monkeypatch):
    """
    Test that a failing call is reported with the provider error, not
    raised.
    """
    assistant = ForecastingAssistant(llm="openai:gpt-5.5")
    patch_agent(monkeypatch, assistant, error=RuntimeError("Error code: 401"))

    result = assistant.check_llm(test_call=True)

    assert result.call_ok is False
    assert result.ok is False
    assert "The call to the LLM 'openai:gpt-5.5' failed." in result.error
    assert "RuntimeError: Error code: 401" in result.error


def test_check_llm_output_when_agent_cannot_be_built(monkeypatch):
    """
    Test that an error while building the model or the agent (a provider
    error at construction, a missing SDK) is reported as a failed call.
    """
    assistant = ForecastingAssistant(llm="openai:gpt-5.5")

    def _boom():
        raise ValueError("Unknown model")

    monkeypatch.setattr(assistant, "_resolve_agent", _boom)

    result = assistant.check_llm(test_call=True)

    assert result.call_ok is False
    assert "ValueError: Unknown model" in result.error


def test_check_llm_skips_test_call_when_static_checks_fail(monkeypatch):
    """
    Test that no call is attempted when a static check already failed.
    """
    monkeypatch.delenv("OPENAI_API_KEY")
    assistant = ForecastingAssistant(llm="openai:gpt-5.5")

    def _boom():
        raise AssertionError("the agent must not be built")

    monkeypatch.setattr(assistant, "_resolve_agent", _boom)

    result = assistant.check_llm(test_call=True)

    assert result.env_var_set is False
    assert result.call_ok is None
    assert result.ok is False


def test_check_llm_uses_assistant_base_url_and_api_key(monkeypatch):
    """
    Test that the assistant's own base_url and api_key are what the
    check reports on.
    """
    import skforecast_ai.llm.diagnostics as diagnostics

    monkeypatch.setattr(diagnostics, "ensure_ollama_reachable", lambda url: None)
    assistant = ForecastingAssistant(
        llm="ollama:qwen3:8b", base_url="http://gpu-box:11434/v1", api_key="ignored"
    )

    result = assistant.check_llm()

    assert result.base_url == "http://gpu-box:11434/v1"
    assert result.credential_source == "none"
    assert result.reachable is True


def test_check_llm_rendering_never_shows_the_key():
    """
    Test that the rendered result names the variable but never the key.
    """
    assistant = ForecastingAssistant(llm="openai:gpt-5.5", api_key="sk-explicit-marker")

    rendered = str(assistant.check_llm())

    assert "Provider" in rendered
    assert "explicit api_key" in rendered
    assert "sk-explicit-marker" not in rendered
