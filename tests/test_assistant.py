# Unit test ForecastingAssistant

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from skforecast_ai import ForecastingAssistant, LLMRequiredError
from skforecast_ai.schemas import (
    DataProfile,
    ForecasterProfile,
    ForecastPlan,
    GenerateResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_daily_index = pd.date_range("2023-01-01", periods=100, freq="D")
df_fixture = pd.DataFrame(
    {
        "date": _daily_index,
        "sales": np.arange(100, dtype=float),
        "promo": np.tile([0.0, 1.0], 50),
    }
)


def _write_csv(tmp_path: Path) -> Path:
    """Write the fixture DataFrame to a temporary CSV file."""
    csv_path = tmp_path / "data.csv"
    df_fixture.to_csv(csv_path, index=False)
    return csv_path


# ---------------------------------------------------------------------------
# Tests: constructor
# ---------------------------------------------------------------------------
def test_init_stores_attributes():
    """
    Test that ForecastingAssistant stores llm, base_url, and send_data_to_llm
    attributes correctly.
    """
    assistant = ForecastingAssistant(
        llm="openai:gpt-4o-mini",
        base_url="http://localhost:8080/v1",
        send_data_to_llm=True,
    )
    assert assistant.llm == "openai:gpt-4o-mini"
    assert assistant.base_url == "http://localhost:8080/v1"
    assert assistant.send_data_to_llm is True


def test_send_data_to_llm_default_false():
    """
    Test that send_data_to_llm defaults to False.
    """
    assistant = ForecastingAssistant()
    assert assistant.send_data_to_llm is False


# ---------------------------------------------------------------------------
# Tests: Tier 0 — profile
# ---------------------------------------------------------------------------
def test_tier0_profile_output_when_valid_dataframe():
    """
    Test that profile() returns a ForecasterProfile (with embedded
    DataProfile) from a pandas DataFrame without requiring an LLM.
    """
    assistant = ForecastingAssistant()
    forecaster_profile = assistant.profile(
        data=df_fixture, target="sales", date_column="date"
    )

    assert isinstance(forecaster_profile, ForecasterProfile)
    assert isinstance(forecaster_profile.data_profile, DataProfile)
    assert forecaster_profile.data_profile.target == "sales"
    assert forecaster_profile.data_profile.n_observations == 100
    assert forecaster_profile.data_profile.n_series == 1
    assert forecaster_profile.data_profile.index_type == "datetime"
    assert "promo" in forecaster_profile.data_profile.exog_columns
    assert forecaster_profile.forecaster_candidates
    assert forecaster_profile.forecaster == forecaster_profile.forecaster_candidates[0]


def test_assistant_accept_csv_path(tmp_path):
    """
    Test that profile() accepts a string path to a CSV file.
    """
    csv_path = _write_csv(tmp_path)
    assistant = ForecastingAssistant()
    forecaster_profile = assistant.profile(
        data=str(csv_path), target="sales", date_column="date"
    )

    assert isinstance(forecaster_profile, ForecasterProfile)
    assert forecaster_profile.data_profile.target == "sales"
    assert forecaster_profile.data_profile.n_observations == 100


# ---------------------------------------------------------------------------
# Tests: Tier 0 — generate_plan
# ---------------------------------------------------------------------------
def test_tier0_generate_plan_output_when_valid_dataframe():
    """
    Test that generate_plan() takes a ForecasterProfile and returns a
    ForecastPlan without an LLM.
    """
    assistant = ForecastingAssistant()
    forecaster_profile = assistant.profile(
        data=df_fixture, target="sales", date_column="date",
    )
    plan = assistant.generate_plan(forecaster_profile, steps=10)

    assert isinstance(plan, ForecastPlan)
    assert plan.steps == 10
    assert plan.task_type == "single_series"
    assert plan.forecaster == forecaster_profile.forecaster


def test_tier0_generate_plan_output_when_forecaster_selected():
    """
    Test that profile() + generate_plan() honor an explicit forecaster.
    """
    assistant = ForecastingAssistant()
    forecaster_profile = assistant.profile(
        data=df_fixture,
        target="sales",
        date_column="date",
    )
    plan = assistant.generate_plan(
        forecaster_profile, steps=10, forecaster="ForecasterDirect",
    )

    assert plan.forecaster == "ForecasterDirect"
    assert "ForecasterDirect" in forecaster_profile.forecaster_candidates


# ---------------------------------------------------------------------------
# Tests: Tier 0 — generate_code
# ---------------------------------------------------------------------------
def test_tier0_generate_code_output_when_valid_dataframe():
    """
    Test that generate_code() returns a GenerateResult without an LLM.
    """
    assistant = ForecastingAssistant()
    result = assistant.generate_code(
        data=df_fixture, target="sales", date_column="date", steps=10
    )

    assert isinstance(result, GenerateResult)
    assert isinstance(result.forecaster_profile, ForecasterProfile)
    assert isinstance(result.plan, ForecastPlan)
    assert isinstance(result.code, str)
    assert "import" in result.code
    assert "ForecasterRecursive" in result.code or "Forecaster" in result.code


def test_tier0_generate_code_output_when_forecaster_selected():
    """
    Test that generate_code() generates code for an explicitly selected
    forecaster.
    """
    assistant = ForecastingAssistant()
    result = assistant.generate_code(
        data=df_fixture,
        target="sales",
        date_column="date",
        steps=10,
        forecaster="ForecasterDirect",
    )

    assert result.plan.forecaster == "ForecasterDirect"
    assert "ForecasterDirect" in result.code


# ---------------------------------------------------------------------------
# Tests: Tier 0 — LLMRequiredError
# ---------------------------------------------------------------------------
def test_tier0_ask_LLMRequiredError_when_no_llm():
    """
    Test that ask() raises LLMRequiredError when llm=None.
    """
    assistant = ForecastingAssistant()
    err_msg = re.escape(
        "`ask()` requires an LLM. "
        "Pass `llm=...` when creating ForecastingAssistant."
    )
    with pytest.raises(LLMRequiredError, match=err_msg):
        assistant.ask("Forecast 30 days ahead")


# ---------------------------------------------------------------------------
# Tests: Tier 1/2 — with mocked LLM
# ---------------------------------------------------------------------------
def test_assistant_with_llm_generate_code_output(tmp_path):
    """
    Test that generate_code() works with a TestModel mock (deterministic
    path is unaffected by the presence of an LLM).
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.test import TestModel

    assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")
    assistant._model = TestModel()

    result = assistant.generate_code(
        data=df_fixture, target="sales", date_column="date", steps=10
    )

    assert isinstance(result, GenerateResult)
    assert result.plan.steps == 10


# ---------------------------------------------------------------------------
# Tests: LLM fallback and ask modes
# ---------------------------------------------------------------------------
def test_ask_fallback_when_llm_fails_with_data(monkeypatch):
    """
    Test that ask() falls back to deterministic mode and returns an AskResult
    with a warning when the LLM call fails, providing data context.
    """
    from skforecast_ai.schemas import AskResult

    assistant = ForecastingAssistant(llm="openai:fake-model")

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    import skforecast_ai.llm.agent as agent_mod

    def _mock_create_agent(*args, **kwargs):
        class _FakeAgent:
            def run_sync(self, *a, **kw):
                raise RuntimeError("Connection refused")
        return _FakeAgent()

    monkeypatch.setattr(agent_mod, "create_forecasting_agent", _mock_create_agent)

    with pytest.warns(UserWarning, match="LLM call failed"):
        result = assistant.ask(
            prompt="What forecaster should I use?",
            data=df_fixture,
            target="sales",
            date_column="date",
            steps=10,
        )

    assert isinstance(result, AskResult)
    assert "LLM unavailable" in result.explanation
    assert result.plan is not None
    assert result.forecaster_profile is not None


def test_ask_fallback_when_llm_fails_no_data(monkeypatch):
    """
    Test that ask() falls back gracefully when LLM fails and no data is
    provided — returns an error explanation without crashing.
    """
    from skforecast_ai.schemas import AskResult

    assistant = ForecastingAssistant(llm="openai:fake-model")

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    import skforecast_ai.llm.agent as agent_mod

    def _mock_create_agent(*args, **kwargs):
        class _FakeAgent:
            def run_sync(self, *a, **kw):
                raise RuntimeError("Connection refused")
        return _FakeAgent()

    monkeypatch.setattr(agent_mod, "create_forecasting_agent", _mock_create_agent)

    with pytest.warns(UserWarning, match="LLM call failed"):
        result = assistant.ask(prompt="What forecaster should I use?")

    assert isinstance(result, AskResult)
    assert "LLM unavailable" in result.explanation
    assert result.plan is None
    assert result.forecaster_profile is None


def test_ask_qa_mode_no_data(monkeypatch):
    """
    Test that ask() in Q&A mode (no data, no profile) calls the LLM
    with just the user question and returns a plain text explanation.
    """
    from skforecast_ai.schemas import AskResult

    assistant = ForecastingAssistant(llm="openai:fake-model")

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    import skforecast_ai.llm.agent as agent_mod

    class _FakeResult:
        output = "Skforecast is a Python library for time series."

    def _mock_create_agent(*args, **kwargs):
        class _FakeAgent:
            def run_sync(self, msg, **kw):
                assert "## Question" not in msg  # No context prefix
                return _FakeResult()
        return _FakeAgent()

    monkeypatch.setattr(agent_mod, "create_forecasting_agent", _mock_create_agent)

    result = assistant.ask(prompt="What is skforecast?")

    assert isinstance(result, AskResult)
    assert result.explanation == "Skforecast is a Python library for time series."
    assert result.forecaster_profile is None
    assert result.plan is None


def test_ask_explain_mode_with_data(monkeypatch):
    """
    Test that ask() in Explain mode (data provided) computes profile and
    plan deterministically, then passes context to the LLM.
    """
    from skforecast_ai.schemas import AskResult

    assistant = ForecastingAssistant(llm="openai:fake-model")

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    import skforecast_ai.llm.agent as agent_mod

    class _FakeResult:
        output = "This plan uses ForecasterRecursive with LGBMRegressor."

    def _mock_create_agent(*args, **kwargs):
        class _FakeAgent:
            def run_sync(self, msg, **kw):
                assert "## Data & Profile Summary" in msg
                assert "## Forecast Plan" in msg
                assert "## Question" in msg
                return _FakeResult()
        return _FakeAgent()

    monkeypatch.setattr(agent_mod, "create_forecasting_agent", _mock_create_agent)

    result = assistant.ask(
        prompt="Explain this plan",
        data=df_fixture,
        target="sales",
        date_column="date",
        steps=10,
    )

    assert isinstance(result, AskResult)
    assert result.forecaster_profile is not None
    assert result.plan is not None
    assert result.explanation == "This plan uses ForecasterRecursive with LGBMRegressor."


def test_ask_with_precomputed_profile(monkeypatch):
    """
    Test that ask() skips profiling when a pre-computed
    ForecasterProfile is provided directly.
    """
    from skforecast_ai.schemas import AskResult

    assistant = ForecastingAssistant(llm="openai:fake-model")

    # Pre-compute profile
    profile = assistant.profile(data=df_fixture, target="sales", date_column="date")

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    import skforecast_ai.llm.agent as agent_mod

    class _FakeResult:
        output = "Great plan for daily data."

    def _mock_create_agent(*args, **kwargs):
        class _FakeAgent:
            def run_sync(self, msg, **kw):
                return _FakeResult()
        return _FakeAgent()

    monkeypatch.setattr(agent_mod, "create_forecasting_agent", _mock_create_agent)

    result = assistant.ask(
        prompt="Is this a good plan?",
        forecaster_profile=profile,
        steps=5,
    )

    assert isinstance(result, AskResult)
    assert result.forecaster_profile is profile
    assert result.plan is not None
    assert result.plan.steps == 5
    assert result.explanation == "Great plan for daily data."



