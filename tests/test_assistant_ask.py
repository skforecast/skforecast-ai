# Unit test ask ForecastingAssistant

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai import ForecastingAssistant, LLMRequiredError
from skforecast_ai.schemas import AskResult, ForecastResult, BacktestResult

from tests.fixtures_assistant import df_single, patch_agent


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_ask_LLMRequiredError_when_no_llm():
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


def test_ask_ValueError_when_data_provided_without_target(monkeypatch):
    """
    Test that ask() raises ValueError when data is provided but target
    is None.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(monkeypatch, assistant, output="unused")

    with pytest.raises(ValueError, match="`target` is required"):
        assistant.ask(prompt="What should I do?", data=df_single)


def test_ask_ValueError_when_profile_provided_without_steps(monkeypatch):
    """
    Test that ask() raises ValueError when profile is
    provided without steps.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    patch_agent(monkeypatch, assistant, output="unused")

    with pytest.raises(ValueError, match="`steps` is required"):
        assistant.ask(prompt="Explain this", profile=profile)


# =============================================================================
# Tests: basic output — Q&A mode
# =============================================================================
def test_ask_qa_mode_output_when_no_data(monkeypatch):
    """
    Test that ask() in Q&A mode (no data, no profile) calls the LLM
    with just the user question and returns a plain text explanation.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(
        monkeypatch,
        assistant,
        output="Skforecast is a Python library for time series.",
    )

    result = assistant.ask(prompt="What is skforecast?")

    assert isinstance(result, AskResult)
    assert result.explanation == "Skforecast is a Python library for time series."
    assert result.profile is None
    assert result.plan is None
    assert result.code is None


def test_ask_qa_mode_preserves_code_blocks(monkeypatch):
    """
    Test that ask() in Q&A mode (no data) preserves code blocks in the
    output since there is no validated code to reference.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(
        monkeypatch,
        assistant,
        output=(
            "Use ForecasterRecursive:\n\n"
            "```python\nfrom skforecast.recursive import ForecasterRecursive\n```"
        ),
    )

    result = assistant.ask(prompt="How do I create a recursive forecaster?")

    assert "```python" in result.explanation
    assert "ForecasterRecursive" in result.explanation
    assert result.code is None


# =============================================================================
# Tests: explain mode (data provided)
# =============================================================================
def test_ask_explain_mode_output_when_data_provided(monkeypatch):
    """
    Test that ask() in Explain mode (data provided) computes profile and
    plan deterministically, then passes context to the LLM.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    capture = {}
    patch_agent(
        monkeypatch,
        assistant,
        output="This plan uses ForecasterRecursive with LGBMRegressor.",
        capture=capture,
    )

    result = assistant.ask(
        prompt="Explain this plan",
        data=df_single,
        target="sales",
        date_column="date",
        steps=10,
    )

    # Context message carries the dataset, plan, and question sections.
    assert "## Dataset" in capture["message"]
    assert "## Forecast Plan" in capture["message"]
    assert "## Question" in capture["message"]

    assert isinstance(result, AskResult)
    assert result.profile is not None
    assert result.plan is not None
    assert result.code is not None
    assert result.explanation == "This plan uses ForecasterRecursive with LGBMRegressor."


def test_ask_explain_mode_strips_code_blocks(monkeypatch):
    """
    Test that ask() in Explain mode strips code blocks from the LLM
    output (since validated code exists in result.code).
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(
        monkeypatch,
        assistant,
        output=(
            "The strategy uses LightGBM.\n\n"
            "```python\nfrom skforecast.recursive import ForecasterRecursive\n```\n\n"
            "This is optimal for daily data."
        ),
    )

    result = assistant.ask(
        prompt="Explain the forecasting strategy",
        data=df_single,
        target="sales",
        date_column="date",
        steps=5,
    )

    assert "```" not in result.explanation
    assert "result.code" in result.explanation
    assert "The strategy uses LightGBM." in result.explanation
    assert result.code is not None


def test_ask_output_when_precomputed_profile(monkeypatch):
    """
    Test that ask() skips profiling when a pre-computed
    ForecastingProfile is provided directly.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    patch_agent(monkeypatch, assistant, output="Great plan for daily data.")

    result = assistant.ask(
        prompt="Is this a good plan?",
        profile=profile,
        steps=5,
    )

    assert result.profile is profile
    assert result.plan is not None
    assert result.plan.steps == 5
    assert result.explanation == "Great plan for daily data."


# =============================================================================
# Tests: results mode (forecast_result provided)
# =============================================================================
def test_ask_output_when_forecast_result_provided(monkeypatch):
    """
    Test that ask() in Results mode passes predictions and metrics to the
    LLM context and extracts profile/plan/code from the ForecastResult.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")

    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    predictions = pd.DataFrame({"pred": [10.0, 11.0, 12.0, 13.0, 14.0]})
    metrics = pd.DataFrame(
        {"series": ["sales"], "MAE": [1.5], "MSE": [3.2], "MASE": [0.8]}
    )
    mock_forecast_result = ForecastResult(
        profile=profile,
        plan=plan,
        code="# mock code",
        metrics=metrics,
        predictions=predictions,
    )

    capture = {}
    patch_agent(
        monkeypatch,
        assistant,
        output="Based on the predictions, values increase steadily.",
        capture=capture,
    )

    result = assistant.ask(
        prompt="Explain the predictions",
        forecast_result=mock_forecast_result,
    )

    # Context message carries the results sections and metric values.
    assert "## Forecast Results" in capture["message"]
    assert "Predictions" in capture["message"]
    assert "Evaluation Metrics" in capture["message"]
    assert "MAE" in capture["message"]

    assert result.profile is profile
    assert result.plan is plan
    assert result.code == "# mock code"
    assert result.explanation == "Based on the predictions, values increase steadily."


def test_ask_output_when_forecast_result_with_intervals(monkeypatch):
    """
    Test that ask() in Results mode includes prediction interval columns
    in the context when they are present in the ForecastResult
    predictions.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")

    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, interval=[0.1, 0.9])

    predictions = pd.DataFrame({
        "pred": [10.0, 11.0, 12.0, 13.0, 14.0],
        "lower_bound": [8.0, 9.0, 10.0, 11.0, 12.0],
        "upper_bound": [12.0, 13.0, 14.0, 15.0, 16.0],
    })
    metrics = pd.DataFrame({"series": ["sales"], "MAE": [1.5], "MSE": [3.2], "MASE": [0.8]})
    mock_forecast_result = ForecastResult(
        profile=profile,
        plan=plan,
        code="# mock code",
        metrics=metrics,
        predictions=predictions,
    )

    capture = {}
    patch_agent(
        monkeypatch,
        assistant,
        output="Intervals are narrow, indicating high confidence.",
        capture=capture,
    )

    result = assistant.ask(
        prompt="Explain the intervals",
        forecast_result=mock_forecast_result,
    )

    # Interval columns are surfaced in the context message.
    assert "lower_bound" in capture["message"]
    assert "upper_bound" in capture["message"]

    assert result.explanation == "Intervals are narrow, indicating high confidence."


# =============================================================================
# Tests: LLM fallback
# =============================================================================
def test_ask_fallback_when_llm_fails_with_data(monkeypatch):
    """
    Test that ask() falls back to deterministic mode and returns an
    AskResult with a warning when the LLM call fails.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(
        monkeypatch, assistant, error=RuntimeError("Connection refused")
    )

    with pytest.warns(UserWarning, match="LLM call failed"):
        result = assistant.ask(
            prompt="What forecaster should I use?",
            data=df_single,
            target="sales",
            date_column="date",
            steps=10,
        )

    assert isinstance(result, AskResult)
    assert "LLM unavailable" in result.explanation
    assert result.plan is not None
    assert result.profile is not None


def test_ask_fallback_when_llm_fails_no_data(monkeypatch):
    """
    Test that ask() falls back gracefully when LLM fails and no data is
    provided — returns an error explanation without crashing.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(
        monkeypatch, assistant, error=RuntimeError("Connection refused")
    )

    with pytest.warns(UserWarning, match="LLM call failed"):
        result = assistant.ask(prompt="What forecaster should I use?")

    assert isinstance(result, AskResult)
    assert "LLM unavailable" in result.explanation
    assert result.plan is None
    assert result.profile is None


def test_ask_output_when_large_predictions_truncated(monkeypatch):
    """
    Test that predictions with more than 30 rows are truncated in context
    when send_data_to_llm=True.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model", send_data_to_llm=True)

    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    predictions = pd.DataFrame({"pred": np.arange(50, dtype=float)})
    metrics = pd.DataFrame({"series": ["sales"], "MAE": [2.0], "MSE": [4.0], "MASE": [1.0]})
    mock_forecast_result = ForecastResult(
        profile=profile,
        plan=plan,
        code="# mock code",
        metrics=metrics,
        predictions=predictions,
        intervals=None,
    )

    capture = {}
    patch_agent(
        monkeypatch,
        assistant,
        output="The predictions show an upward trend.",
        capture=capture,
    )

    result = assistant.ask(
        prompt="Summarize the predictions",
        forecast_result=mock_forecast_result,
    )

    # Large prediction tables are truncated in the context message.
    assert "rows omitted" in capture["message"]

    assert result.explanation == "The predictions show an upward trend."


# =============================================================================
# Tests: backtest mode (backtest_result provided)
# =============================================================================
def test_ask_ValueError_when_both_results_provided():
    """
    Test that ask() raises ValueError when both forecast_result and
    backtest_result are provided (mutually exclusive).
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")

    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    predictions = pd.DataFrame({"pred": [10.0, 11.0]})
    metrics = pd.DataFrame({"series": ["sales"], "MAE": [1.0]})

    forecast_res = ForecastResult(
        profile=profile, plan=plan, code="# fc",
        metrics=metrics, predictions=predictions, intervals=None,
    )
    backtest_res = BacktestResult(
        profile=profile, plan=plan, cv_config={"steps": 5},
        metrics=metrics, predictions=predictions,
        code="# bt", explanation="test",
    )

    with pytest.raises(ValueError, match="mutually exclusive"):
        assistant.ask(
            prompt="Explain",
            forecast_result=forecast_res,
            backtest_result=backtest_res,
        )


def test_ask_output_when_backtest_result_provided(monkeypatch):
    """
    Test that ask() in Backtest mode passes metrics, predictions, and
    CV config to the LLM context and extracts profile/plan/code from
    the BacktestResult.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")

    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    predictions = pd.DataFrame({"pred": [10.0, 11.0, 12.0, 13.0, 14.0]})
    metrics = pd.DataFrame(
        {"series": ["sales"], "MAE": [1.5], "MSE": [3.2], "MASE": [0.8]}
    )
    cv_config = {
        "steps": 5,
        "initial_train_size": 80,
        "refit": False,
        "fixed_train_size": True,
    }
    mock_backtest_result = BacktestResult(
        profile=profile,
        plan=plan,
        cv_config=cv_config,
        code="# backtest code",
        metrics=metrics,
        predictions=predictions,
        explanation="Backtest explanation",
    )

    capture = {}
    patch_agent(
        monkeypatch,
        assistant,
        output="The backtest shows consistent performance across folds.",
        capture=capture,
    )

    result = assistant.ask(
        prompt="Explain the backtest results",
        backtest_result=mock_backtest_result,
    )

    # Context message carries the backtest configuration and results.
    assert "## Backtesting Configuration" in capture["message"]
    assert "initial_train_size" in capture["message"]
    assert "## Forecast Results" in capture["message"]
    assert "MAE" in capture["message"]

    assert result.profile is profile
    assert result.plan is plan
    assert result.code == "# backtest code"
    assert result.explanation == "The backtest shows consistent performance across folds."
