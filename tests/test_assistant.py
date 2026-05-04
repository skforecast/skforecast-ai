# Unit test ForecastingAssistant

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from skforecast_ai import ForecastingAssistant, LLMRequiredError
from skforecast_ai.schemas import (
    DataProfile,
    ForecastPlan,
    GenerateResult,
    RecommendResult,
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
    Test that profile() returns a DataProfile from a pandas DataFrame
    without requiring an LLM.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_fixture, target="sales", date_column="date")

    assert isinstance(profile, DataProfile)
    assert profile.target == "sales"
    assert profile.n_observations == 100
    assert profile.n_series == 1
    assert profile.index_type == "datetime"
    assert "promo" in profile.exog_columns


def test_assistant_accept_csv_path(tmp_path):
    """
    Test that profile() accepts a string path to a CSV file.
    """
    csv_path = _write_csv(tmp_path)
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=str(csv_path), target="sales", date_column="date"
    )

    assert isinstance(profile, DataProfile)
    assert profile.target == "sales"
    assert profile.n_observations == 100


# ---------------------------------------------------------------------------
# Tests: Tier 0 — recommend
# ---------------------------------------------------------------------------
def test_tier0_recommend_output_when_valid_dataframe():
    """
    Test that recommend() returns a RecommendResult without an LLM.
    """
    assistant = ForecastingAssistant()
    result = assistant.recommend(
        data=df_fixture, target="sales", date_column="date", horizon=10
    )

    assert isinstance(result, RecommendResult)
    assert isinstance(result.profile, DataProfile)
    assert isinstance(result.plan, ForecastPlan)
    assert result.plan.horizon == 10
    assert result.plan.task_type == "single_series"


# ---------------------------------------------------------------------------
# Tests: Tier 0 — generate_code
# ---------------------------------------------------------------------------
def test_tier0_generate_code_output_when_valid_dataframe():
    """
    Test that generate_code() returns a GenerateResult without an LLM.
    """
    assistant = ForecastingAssistant()
    result = assistant.generate_code(
        data=df_fixture, target="sales", date_column="date", horizon=10
    )

    assert isinstance(result, GenerateResult)
    assert isinstance(result.profile, DataProfile)
    assert isinstance(result.plan, ForecastPlan)
    assert isinstance(result.code, str)
    assert "import" in result.code
    assert "ForecasterRecursive" in result.code or "Forecaster" in result.code


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


def test_tier0_explain_LLMRequiredError_when_no_llm():
    """
    Test that explain() raises LLMRequiredError when llm=None.
    """
    assistant = ForecastingAssistant()
    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        estimator="Ridge",
        horizon=10,
        lags=[1, 2, 3, 4, 5, 6, 7],
        metric="mean_absolute_error",
        backtesting_strategy="TimeSeriesFold",
        rationale="Single series with daily frequency.",
    )
    err_msg = re.escape(
        "`explain()` requires an LLM. "
        "Pass `llm=...` when creating ForecastingAssistant."
    )
    with pytest.raises(LLMRequiredError, match=err_msg):
        assistant.explain(plan=plan)


# ---------------------------------------------------------------------------
# Tests: Tier 1/2 — with mocked LLM
# ---------------------------------------------------------------------------
def test_assistant_with_llm_recommend_output(tmp_path):
    """
    Test that recommend() works with a TestModel mock.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.test import TestModel

    assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")
    # Override the _model with TestModel to avoid real API calls
    assistant._model = TestModel()

    result = assistant.recommend(
        data=df_fixture, target="sales", date_column="date", horizon=10
    )

    assert isinstance(result, RecommendResult)
    assert isinstance(result.plan, ForecastPlan)
    assert result.plan.horizon == 10


# ---------------------------------------------------------------------------
# Tests: LLM fallback to Tier 0
# ---------------------------------------------------------------------------
def test_ask_fallback_when_llm_fails(monkeypatch):
    """
    Test that ask() falls back to deterministic mode and returns an AskResult
    with a warning when the LLM call fails, instead of crashing.
    """
    from skforecast_ai.schemas import AskResult

    assistant = ForecastingAssistant(llm="openai:fake-model")

    # Force _resolve_model to raise when the agent tries to run
    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    # Mock create_forecasting_agent to raise an error
    import skforecast_ai.llm.agent as agent_mod

    def _mock_create_agent(*args, **kwargs):
        class _FakeAgent:
            def run_sync(self, *a, **kw):
                raise RuntimeError("Connection refused")
        return _FakeAgent()

    monkeypatch.setattr(agent_mod, "create_forecasting_agent", _mock_create_agent)

    with pytest.warns(UserWarning, match="LLM call failed"):
        result = assistant.ask(
            question="What forecaster should I use?",
            data=df_fixture,
        )

    assert isinstance(result, AskResult)
    assert "LLM unavailable" in result.explanation
    assert result.plan is not None


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
        result = assistant.ask(question="What forecaster should I use?")

    assert isinstance(result, AskResult)
    assert "LLM unavailable" in result.explanation
    assert result.plan is None


def test_explain_fallback_when_llm_fails(monkeypatch):
    """
    Test that explain() falls back to plan.rationale when LLM fails,
    emitting a UserWarning instead of crashing.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")

    def _mock_resolve_model(self_=None):
        raise ConnectionError("Cannot reach LLM provider")

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        estimator="Ridge",
        horizon=10,
        lags=[1, 2, 3, 4, 5, 6, 7],
        metric="mean_absolute_error",
        backtesting_strategy="TimeSeriesFold",
        rationale="Single series with daily frequency.",
    )

    with pytest.warns(UserWarning, match="LLM call failed"):
        result = assistant.explain(plan=plan)

    assert "[LLM unavailable]" in result
    assert "Single series with daily frequency." in result
