# Unit test ask ForecastingAssistant

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast_ai import (
    DataSentToLLMWarning,
    ForecastingAssistant,
    LLMCallError,
    LLMRequiredError,
)
from skforecast_ai.schemas import (
    AskResult,
    BacktestResult,
    CodeGenerationResult,
    ForecastResult,
)

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


def test_ask_TypeError_when_data_keyword_is_used(monkeypatch):
    """
    Test that ask() no longer profiles data on its own: the former `data`
    keyword is rejected, so the caller profiles first and passes the
    profile as `context`.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(monkeypatch, assistant, output="unused")

    with pytest.raises(TypeError, match="unexpected keyword argument 'data'"):
        assistant.ask(prompt="What should I do?", data=df_single)


def test_ask_TypeError_when_plan_passed_as_context(monkeypatch):
    """
    Test that a bare ForecastPlan is rejected as `context` with a message
    pointing to `context=profile, plan=plan`, since a plan does not carry
    the dataset it was derived from.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    patch_agent(monkeypatch, assistant, output="unused")

    with pytest.raises(TypeError, match=re.escape("`context=profile, plan=plan`")):
        assistant.ask(prompt="Explain this", context=plan)


def test_ask_TypeError_when_plan_accompanies_a_result_context(monkeypatch):
    """
    Test that `plan` is rejected next to a context that already carries
    its own plan, so the returned plan and code can never describe
    different states.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    comparison = make_comparison_result(assistant)
    other_plan = assistant.plan(comparison.profile, steps=99)
    patch_agent(monkeypatch, assistant, output="unused")

    with pytest.raises(TypeError, match="only accompanies a `ForecastingProfile`"):
        assistant.ask(prompt="Why did it win?", context=comparison, plan=other_plan)


# =============================================================================
# Tests: basic output: Q&A mode
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


def test_ask_records_the_auto_routed_skills(monkeypatch):
    """
    Test that the skills chosen by the router are reported on the
    result, so a poor answer can be traced back to a routing miss.
    """
    from skforecast_ai.llm.skills import select_skills

    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(monkeypatch, assistant, output="answer")

    prompt = "How do I detect drift in my deployed model?"
    result = assistant.ask(prompt=prompt)

    assert result.skills == select_skills(task_type=None, question=prompt)
    assert result.skills


def test_ask_records_the_skills_when_given_explicitly(monkeypatch):
    """
    Test that a caller-supplied skill list is reported unchanged, since
    it bypasses the router.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(monkeypatch, assistant, output="answer")

    result = assistant.ask(
        prompt="What is skforecast?", skills=["backtesting-configuration"]
    )

    assert result.skills == ["backtesting-configuration"]


def test_ask_records_no_skills_when_selection_is_empty(monkeypatch):
    """
    Test that an explicit empty selection is preserved rather than
    reported as a routed one.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(monkeypatch, assistant, output="answer")

    result = assistant.ask(prompt="What is skforecast?", skills=[])

    assert result.skills == []


# =============================================================================
# Tests: profile and plan as context
# =============================================================================
def test_ask_output_when_profile_and_plan_provided(monkeypatch):
    """
    Test that a profile passed as `context` together with a `plan` is
    explained through the script the two produce: the LLM receives the
    dataset and plan sections and the returned code is that script.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    capture = {}
    patch_agent(
        monkeypatch,
        assistant,
        output="This plan uses ForecasterRecursive with LGBMRegressor.",
        capture=capture,
    )

    result = assistant.ask(prompt="Explain this plan", context=profile, plan=plan)

    # Context message carries the dataset, plan, and question sections.
    assert "<dataset>" in capture["message"]
    assert "<forecast_plan>" in capture["message"]
    assert "<question>\nExplain this plan\n</question>" in capture["message"]

    assert isinstance(result, AskResult)
    assert result.profile is profile
    assert result.plan is plan
    assert result.code == assistant.forecast_code(profile=profile, plan=plan).code
    assert result.explanation == "This plan uses ForecasterRecursive with LGBMRegressor."


def test_ask_output_when_profile_provided_alone(monkeypatch):
    """
    Test that a profile passed as `context` on its own is explained
    without building a plan: the LLM receives the dataset and profile
    sections only, and no plan or code is echoed back.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model", send_data_to_llm=False)
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    capture = {}
    patch_agent(monkeypatch, assistant, output="A recursive forecaster.", capture=capture)

    with warnings.catch_warnings():
        warnings.simplefilter("error", DataSentToLLMWarning)
        result = assistant.ask(prompt="Why this forecaster?", context=profile)

    assert "<dataset>" in capture["message"]
    assert "<profile_decision>" in capture["message"]
    assert "<forecast_plan>" not in capture["message"]
    assert result.profile is profile
    assert result.plan is None
    assert result.code is None
    assert result.explanation == "A recursive forecaster."


def test_ask_strips_code_blocks_when_context_carries_code(monkeypatch):
    """
    Test that ask() strips code blocks from the LLM output when the
    explained context carries a validated script (result.code).
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
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
        prompt="Explain the forecasting strategy", context=profile, plan=plan
    )

    assert "```" not in result.explanation
    assert "result.code" in result.explanation
    assert "The strategy uses LightGBM." in result.explanation
    assert result.code is not None


def test_ask_DeprecationWarning_when_result_alias_is_used(monkeypatch):
    """
    Test that the former `result` keyword still works as an alias of
    `context` with a DeprecationWarning, and that combining both is
    rejected.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model", send_data_to_llm=True)
    comparison = make_comparison_result(assistant)
    patch_agent(monkeypatch, assistant, output="Explanation.")

    with pytest.warns(DeprecationWarning, match="`result` is deprecated"):
        result = assistant.ask(prompt="Why did it win?", result=comparison)

    assert result.profile is comparison.profile
    assert result.plan is comparison.best_candidate.plan

    with pytest.warns(DeprecationWarning):
        with pytest.raises(TypeError, match="cannot be combined"):
            assistant.ask(prompt="Why?", context=comparison, result=comparison)


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
        "`send_data_to_llm=False` does not apply to `context`: the predicted "
        "values it carries are sent to the LLM"
    )
    with pytest.warns(DataSentToLLMWarning, match=err_msg):
        assistant.ask(prompt="Why did it win?", context=comparison)


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
        assistant.ask(prompt="Why did it win?", context=comparison)


def test_ask_output_when_forecast_result_provided(monkeypatch):
    """
    Test that ask() in Results mode passes predictions and metrics to the
    LLM context and extracts profile/plan/code from the ForecastResult.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model", send_data_to_llm=True)

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
        context=mock_forecast_result,
    )

    # Context message carries the results sections and metric values.
    assert "<predictions>" in capture["message"]
    assert "<evaluation_metrics>" in capture["message"]
    assert "MAE" in capture["message"]

    assert result.profile is profile
    assert result.plan is plan
    assert result.code == "# mock code"
    assert result.explanation == "Based on the predictions, values increase steadily."


def test_ask_output_when_code_generation_result_provided(monkeypatch):
    """
    Test that ask() in Results mode accepts a CodeGenerationResult: the
    context carries the dataset and plan sections but no predictions or
    metrics, and the returned profile, plan, and code are the result's own.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")

    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    code_result = CodeGenerationResult(profile=profile, plan=plan, code="# mock code")

    capture = {}
    patch_agent(
        monkeypatch,
        assistant,
        output="The plan uses a recursive forecaster.",
        capture=capture,
    )

    result = assistant.ask(prompt="Explain this script", context=code_result)

    assert "<forecast_plan>" in capture["message"]
    assert "<predictions>" not in capture["message"]
    assert "<evaluation_metrics>" not in capture["message"]

    assert result.profile is profile
    assert result.plan is plan
    assert result.code == "# mock code"
    assert result.explanation == "The plan uses a recursive forecaster."


def test_ask_no_DataSentToLLMWarning_when_code_generation_result_provided(monkeypatch):
    """
    Test that a CodeGenerationResult does not trigger DataSentToLLMWarning
    even with `send_data_to_llm=False`: it carries no predicted values, so
    there is nothing being sent against the setting.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model", send_data_to_llm=False)

    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    code_result = CodeGenerationResult(profile=profile, plan=plan, code="# mock code")
    patch_agent(monkeypatch, assistant, output="Explained.")

    with warnings.catch_warnings():
        warnings.simplefilter("error", DataSentToLLMWarning)
        assistant.ask(prompt="Explain this script", context=code_result)


def test_ask_output_when_forecast_result_with_intervals(monkeypatch):
    """
    Test that ask() in Results mode includes prediction interval columns
    in the context when they are present in the ForecastResult
    predictions.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model", send_data_to_llm=True)

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
        context=mock_forecast_result,
    )

    # Interval columns are surfaced in the context message.
    assert "lower_bound" in capture["message"]
    assert "upper_bound" in capture["message"]

    assert result.explanation == "Intervals are narrow, indicating high confidence."


# =============================================================================
# Tests: LLM failure
# =============================================================================
def test_ask_LLMCallError_when_llm_fails_with_context(monkeypatch):
    """
    Test that a failed LLM call raises LLMCallError instead of returning
    a result whose explanation is not an answer. The provider exception
    is chained and kept as `original_error`.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(
        monkeypatch, assistant, error=RuntimeError("Connection refused")
    )

    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    with pytest.raises(LLMCallError, match="'openai:fake-model' failed") as info:
        assistant.ask(
            prompt="What forecaster should I use?", context=profile, plan=plan
        )

    assert isinstance(info.value.original_error, RuntimeError)
    assert info.value.__cause__ is info.value.original_error
    assert "Connection refused" in str(info.value)


def test_ask_LLMCallError_when_llm_fails_without_context(monkeypatch):
    """
    Test that a failed LLM call raises LLMCallError in Q&A mode as well,
    where there is not even a plan explanation to show.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    patch_agent(
        monkeypatch, assistant, error=RuntimeError("Connection refused")
    )

    with pytest.raises(LLMCallError):
        assistant.ask(prompt="What forecaster should I use?")


def test_ask_LLMCallError_when_ollama_is_not_reachable(monkeypatch):
    """
    Test that a local model that cannot be reached is reported through
    the same LLMCallError as any other failed call.
    """
    import skforecast_ai.assistant as assistant_mod

    def _unreachable(base_url=None):
        raise ConnectionError("Ollama is not reachable at 'http://localhost:11434'.")

    monkeypatch.setattr(assistant_mod, "ensure_ollama_reachable", _unreachable)
    assistant = ForecastingAssistant(llm="ollama:qwen2.5:7b-instruct")

    with pytest.raises(LLMCallError, match="not reachable") as info:
        assistant.ask(prompt="What is skforecast?")

    assert isinstance(info.value.original_error, ConnectionError)


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
        context=mock_forecast_result,
    )

    # Large prediction tables are truncated in the context message.
    assert "rows omitted" in capture["message"]

    assert result.explanation == "The predictions show an upward trend."


# =============================================================================
# Tests: results mode validation and backtest results
# =============================================================================
def test_ask_TypeError_when_context_wrong_type():
    """
    Test that ask() raises TypeError when `context` is not explainable,
    naming the accepted kinds.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")

    err_msg = re.escape(
        "`context` must be a `ForecastingProfile` or a workflow result (for "
        "example `ForecastResult`, `BacktestResult`, `ComparisonResult`, "
        "`CodeGenerationResult`, or `CVResult`), got str."
    )
    with pytest.raises(TypeError, match=err_msg):
        assistant.ask(prompt="Explain", context="not a result")


def test_ask_TypeError_when_context_is_dict():
    """
    Test that ask() raises TypeError when `context` is a plain dict
    (e.g. a serialized result) rather than a result object.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")

    with pytest.raises(TypeError, match="got dict"):
        assistant.ask(prompt="Explain", context={"not": "a result"})


def test_ask_output_when_comparison_result_provided(monkeypatch):
    """
    Test that ask() accepts a ComparisonResult and echoes back the shared
    profile plus the winning candidate's plan and code.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model", send_data_to_llm=True)
    comparison = make_comparison_result(assistant)

    patch_agent(
        monkeypatch,
        assistant,
        output="ForecasterRecursive won on MAE.",
    )

    result = assistant.ask(prompt="Why did it win?", context=comparison)

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
    assistant = ForecastingAssistant(llm="openai:fake-model", send_data_to_llm=True)
    comparison = make_comparison_result(assistant, with_failure=True)

    capture = {}
    patch_agent(
        monkeypatch,
        assistant,
        output="ForecasterRecursive won on MAE.",
        capture=capture,
    )

    assistant.ask(prompt="Why did it win?", context=comparison)

    message = capture["message"]
    assert "<leaderboard>" in message
    assert "- Ranking metric: MAE" in message
    assert "runner_up" in message
    assert "- broken: ImportError: No module named 'lightgbm'" in message
    assert "<winning_candidate>" in message
    assert "Name: winner" in message
    assert "<question>\nWhy did it win?\n</question>" in message
    assert message.index("</forecast_context>") < message.index("<question>")


def test_ask_output_when_backtest_result_provided(monkeypatch):
    """
    Test that ask() in Results mode passes metrics, predictions, and
    CV config to the LLM context and extracts profile/plan/code from
    the BacktestResult.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model", send_data_to_llm=True)

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
        context=mock_backtest_result,
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


def test_ask_output_when_cv_result_provided(monkeypatch):
    """
    Test that ask() explains a CVResult: the context carries the plan and
    the cross-validation section but no predictions, no data warning is
    raised, and the echoed artifacts are the result's own.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model", send_data_to_llm=False)
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan, initial_train_size=60)

    capture = {}
    patch_agent(monkeypatch, assistant, output="Four folds, no refit.", capture=capture)

    with warnings.catch_warnings():
        warnings.simplefilter("error", DataSentToLLMWarning)
        result = assistant.ask(prompt="Why this strategy?", context=cv_result)

    assert "<cross_validation>" in capture["message"]
    assert "n_folds" in capture["message"]
    assert "<predictions>" not in capture["message"]
    assert result.profile is profile
    assert result.plan is plan
    assert result.code == cv_result.code
    assert result.explanation == "Four folds, no refit."
