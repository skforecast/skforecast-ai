# Unit test cli check-llm skforecast_ai

import json

import pytest
from typer.testing import CliRunner

from skforecast_ai.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch, tmp_path):
    """
    Isolate the command from the user's environment and config file.
    """
    for name in ("SKFORECAST_AI_LLM", "SKFORECAST_AI_BASE_URL",
                 "SKFORECAST_AI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("skforecast_ai.cli.load_config", lambda: {})


def _mock_ask_agent(monkeypatch, response_text="OK"):
    """Patch the LLM agent to return a fixed response without API calls."""
    import skforecast_ai.llm.agent as agent_mod

    class _FakeResult:
        output = response_text

    def _mock_create_agent(*args, **kwargs):
        class _FakeAgent:
            async def run(self, msg, **kw):
                return _FakeResult()
        return _FakeAgent()

    monkeypatch.setattr(agent_mod, "create_forecasting_agent", _mock_create_agent)


def test_check_llm_exit_1_when_no_llm_configured():
    """
    Test that check-llm without any LLM source prints the configuration
    hint and exits with code 1.
    """
    result = runner.invoke(app, ["check-llm", "--quiet"])

    assert result.exit_code == 1
    assert "no llm configured" in result.output.lower()


def test_check_llm_exit_0_when_env_var_set(monkeypatch):
    """
    Test that a provider whose environment variable is set passes and
    prints the provider and model.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "key-marker")

    result = runner.invoke(app, ["check-llm", "--llm", "openai:gpt-5.5", "--quiet"])

    assert result.exit_code == 0
    assert "openai" in result.output
    assert "gpt-5.5" in result.output
    assert "OPENAI_API_KEY (set)" in result.output


def test_check_llm_exit_1_when_env_var_not_set():
    """
    Test that a missing environment variable is reported and the command
    exits with code 1.
    """
    result = runner.invoke(app, ["check-llm", "--llm", "openai:gpt-5.5", "--quiet"])

    assert result.exit_code == 1
    assert "OPENAI_API_KEY (not set)" in result.output
    assert "not ok" in result.output


def test_check_llm_json_format(monkeypatch):
    """
    Test that --format json prints the result dump with the computed
    `ok` field.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "key-marker")

    result = runner.invoke(
        app, ["check-llm", "--llm", "openai:gpt-5.5", "--format", "json", "--quiet"]
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["provider"] == "openai"
    assert data["env_var_set"] is True
    assert data["call_ok"] is None


def test_check_llm_test_call(monkeypatch):
    """
    Test that --test-call runs the round-trip and reports it in JSON.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "key-marker")
    _mock_ask_agent(monkeypatch)

    result = runner.invoke(
        app,
        ["check-llm", "--llm", "openai:gpt-5.5", "--test-call", "--format", "json",
         "--quiet"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["call_ok"] is True


def test_check_llm_flag_beats_env_var(monkeypatch):
    """
    Test that --llm takes precedence over SKFORECAST_AI_LLM.
    """
    monkeypatch.setenv("SKFORECAST_AI_LLM", "anthropic:claude-sonnet-5")
    monkeypatch.setenv("OPENAI_API_KEY", "key-marker")

    result = runner.invoke(
        app, ["check-llm", "--llm", "openai:gpt-5.5", "--format", "json", "--quiet"]
    )

    assert json.loads(result.output)["provider"] == "openai"


def test_check_llm_never_prints_the_key():
    """
    Test that an explicit --api-key passes the check and never appears
    in the output.
    """
    result = runner.invoke(
        app,
        ["check-llm", "--llm", "openai:gpt-5.5", "--api-key", "sk-secret-marker",
         "--quiet"],
    )

    assert result.exit_code == 0
    assert "explicit api_key" in result.output
    assert "sk-secret-marker" not in result.output
