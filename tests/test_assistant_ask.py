# Unit test ask ForecastingAssistant

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import IgnoredArgumentWarning

from skforecast_ai import (
    DataSentToLLMWarning,
    ForecastingAssistant,
    LLMRequiredError,
)
from skforecast_ai.schemas import AskResult, ForecastResult, BacktestResult

from tests.fixtures_assistant import df_single, make_comparison_result, patch_agent


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
    assert "<dataset>" in capture["message"]
    assert "<forecast_plan>" in capture["message"]
    assert "<question>\nExplain this plan\n</question>" in capture["message"]

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
# Tests: results mode (result provided)
# =============================================================================
def test_ask_DataSentToLLMWarning_when_send_data_to_llm_is_false(monkeypatch):
    """
    Test that overriding `send_data_to_llm=False` in results mode is
    announced. The override is deliberate, but a user who disabled data
    sharing for privacy reasons would otherwise ship predicted values off
    the machine without being told.
    """
    assistant = ForecastingAssistant(
        llm="openai:fake-model", send_data_to_llm=False
    )
    comparison = make_comparison_result(assistant)
    patch_agent(monkeypatch, assistant, output="ForecasterRecursive won.")

    err_msg = re.escape(
        "`send_data_to_llm=False` does not apply to `result`: the predicted "
        "values it carries are sent to the LLM"
    )
    with pytest.warns(DataSentToLLMWarning, match=err_msg):
        assistant.ask(prompt="Why did it win?", result=comparison)


def test_ask_no_DataSentToLLMWarning_when_send_data_to_llm_is_true(monkeypatch):
    """
    Test that the override warning is silent when data sharing is already
    enabled, since nothing is being overridden.
    """
    assistant = ForecastingAssistant(
        llm="openai:fake-model", send_data_to_llm=True
    )
    comparison = make_comparison_result(assistant)
    patch_agent(monkeypatch, assistant, output="ForecasterRecursive won.")

    with warnings.catch_warnings():
        warnings.simplefilter("error", DataSentToLLMWarning)
        assistant.ask(prompt="Why did it win?", result=comparison)


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
        result=mock_forecast_result,
    )

    # Context message carries the results sections and metric values.
    assert "<predictions>" in capture["message"]
    assert "<evaluation_metrics>" in capture["message"]
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
        result=mock_forecast_result,
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
        result=mock_forecast_result,
    )

    # Large prediction tables are truncated in the context message.
    assert "rows omitted" in capture["message"]

    assert result.explanation == "The predictions show an upward trend."


# =============================================================================
# Tests: results mode validation and backtest results
# =============================================================================
def test_ask_TypeError_when_result_wrong_type():
    """
    Test that ask() raises TypeError when `result` is not an
    `ExplainableResult`.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")

    err_msg = re.escape(
        "`result` must be an `ExplainableResult` (for example "
        "`ForecastResult`, `BacktestResult`, or `ComparisonResult`), "
        "got str."
    )
    with pytest.raises(TypeError, match=err_msg):
        assistant.ask(prompt="Explain", result="not a result")


def test_ask_TypeError_when_result_is_dict():
    """
    Test that ask() raises TypeError when `result` is a plain dict
    rather than an `ExplainableResult`.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")

    err_msg = re.escape(
        "`result` must be an `ExplainableResult` (for example "
        "`ForecastResult`, `BacktestResult`, or `ComparisonResult`), "
        "got dict."
    )
    with pytest.raises(TypeError, match=err_msg):
        assistant.ask(prompt="Explain", result={"not": "a result"})


def test_ask_output_when_comparison_result_provided(monkeypatch):
    """
    Test that ask() accepts a ComparisonResult and echoes back the shared
    profile plus the winning candidate's plan and code.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    comparison = make_comparison_result(assistant)

    patch_agent(
        monkeypatch,
        assistant,
        output="ForecasterRecursive won on MAE.",
    )

    result = assistant.ask(prompt="Why did it win?", result=comparison)

    assert isinstance(result, AskResult)
    assert result.profile is comparison.profile
    assert result.plan is comparison.best_candidate.plan
    assert result.code == comparison.best_candidate.code
    assert result.explanation == "ForecasterRecursive won on MAE."


def test_ask_context_when_comparison_result_provided(monkeypatch):
    """
    Test that ask() sends the leaderboard, ranking metric, and winning
    candidate of a ComparisonResult to the LLM.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    comparison = make_comparison_result(assistant, with_failure=True)

    capture = {}
    patch_agent(
        monkeypatch,
        assistant,
        output="ForecasterRecursive won on MAE.",
        capture=capture,
    )

    assistant.ask(prompt="Why did it win?", result=comparison)

    message = capture["message"]
    assert "<leaderboard>" in message
    assert "- Ranking metric: MAE" in message
    assert "runner_up" in message
    assert "- broken: ImportError: No module named 'lightgbm'" in message
    assert "<winning_candidate>" in message
    assert "Name: winner" in message
    assert "<question>\nWhy did it win?\n</question>" in message
    assert message.index("</forecast_context>") < message.index("<question>")


# =============================================================================
# Tests: results mode supersedes the deterministic inputs
# =============================================================================
def test_ask_IgnoredArgumentWarning_when_result_and_plan_provided(monkeypatch):
    """
    Test that a `plan` passed together with a `result` is ignored with an
    IgnoredArgumentWarning, and that the returned plan and code are the
    result's own so they cannot describe different states.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    comparison = make_comparison_result(assistant)
    other_plan = assistant.plan(
        comparison.profile, steps=99, forecaster="ForecasterDirect"
    )

    patch_agent(monkeypatch, assistant, output="Explanation.")

    warn_msg = re.escape(
        "A `result` was provided, so the following argument(s) are "
        "ignored: ['plan']."
    )
    with pytest.warns(IgnoredArgumentWarning, match=warn_msg):
        result = assistant.ask(
            prompt="Why did it win?", result=comparison, plan=other_plan
        )

    assert result.plan is comparison.best_candidate.plan
    assert result.plan is not other_plan
    assert result.code == comparison.best_candidate.code


def test_ask_IgnoredArgumentWarning_when_result_and_data_provided(monkeypatch):
    """
    Test that every deterministic input passed together with a `result`
    is named in the IgnoredArgumentWarning, and that no profiling runs.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    comparison = make_comparison_result(assistant)

    patch_agent(monkeypatch, assistant, output="Explanation.")

    warn_msg = re.escape(
        "A `result` was provided, so the following argument(s) are "
        "ignored: ['data', 'target', 'date_column', 'steps']."
    )
    with pytest.warns(IgnoredArgumentWarning, match=warn_msg):
        result = assistant.ask(
            prompt      = "Why did it win?",
            result      = comparison,
            data        = df_single,
            target      = "sales",
            date_column = "date",
            steps       = 7,
        )

    assert result.profile is comparison.profile
    assert result.plan is comparison.best_candidate.plan


def test_ask_no_warning_when_result_provided_alone(monkeypatch):
    """
    Test that a result passed on its own does not warn, since nothing is
    superseded.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    comparison = make_comparison_result(assistant)

    patch_agent(monkeypatch, assistant, output="Explanation.")

    with warnings.catch_warnings():
        warnings.simplefilter("error", IgnoredArgumentWarning)
        result = assistant.ask(prompt="Why did it win?", result=comparison)

    assert isinstance(result, AskResult)


def test_ask_output_when_backtest_result_provided(monkeypatch):
    """
    Test that ask() in Results mode passes metrics, predictions, and
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
        "n_folds": 4,
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
        result=mock_backtest_result,
    )

    # Context message carries the backtest configuration and results.
    assert "<cross_validation>" in capture["message"]
    assert "initial_train_size" in capture["message"]
    assert "- n_folds: 4" in capture["message"]
    assert "<evaluation_metrics>" in capture["message"]
    assert "MAE" in capture["message"]

    # The deterministic explanation is forwarded so the LLM does not have
    # to re-derive facts that were already computed.
    assert "<deterministic_summary>" in capture["message"]
    assert "Backtest explanation" in capture["message"]

    assert result.profile is profile
    assert result.plan is plan
    assert result.code == "# backtest code"
    assert result.explanation == "The backtest shows consistent performance across folds."
