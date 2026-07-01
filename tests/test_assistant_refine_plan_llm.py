# Unit test refine_plan_with_llm ForecastingAssistant

import re
import warnings

import pytest

from skforecast_ai import ForecastingAssistant, LLMRequiredError
from skforecast_ai.schemas.plans import PlanOverrides, WindowFeature

from tests.fixtures_assistant import df_single


def _mock_resolve_model(self_=None):
    return "fake-model-string"


class _FakeResult:
    def __init__(self, output):
        self.output = output


def _make_fake_agent(outputs):
    """Build a fake agent whose `.run()` yields `outputs` in sequence."""
    call_count = {"n": 0}

    class _FakeAgent:
        async def run(self, msg, **kw):
            i = min(call_count["n"], len(outputs) - 1)
            call_count["n"] += 1
            return _FakeResult(outputs[i])

    return _FakeAgent(), call_count


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_refine_plan_with_llm_LLMRequiredError_when_no_llm():
    """
    Test that refine_plan_with_llm() raises LLMRequiredError when no LLM
    is configured.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "`refine_plan_with_llm()` requires an LLM. "
        "Pass `llm=...` when creating ForecastingAssistant."
    )
    with pytest.raises(LLMRequiredError, match=err_msg):
        assistant.refine_plan_with_llm(profile, plan, prompt="weekly seasonality")


def test_refine_plan_with_llm_skips_when_statistical_task_type(monkeypatch):
    """
    Test that refine_plan_with_llm() short-circuits for task_type
    'statistical' without calling the LLM, returning the original plan.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    plan = plan.model_copy(update={"task_type": "statistical"})

    # No agent/model mock set up: if the LLM were called, this would raise.
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        refined, reasoning = assistant.refine_plan_with_llm(
            profile, plan, prompt="weekly seasonality"
        )

    assert refined is plan
    assert reasoning.startswith("LLM refinement skipped:")
    skip_warnings = [x for x in w if "does not apply to task_type" in str(x.message)]
    assert len(skip_warnings) == 1


# =============================================================================
# Tests: success path
# =============================================================================
def test_refine_plan_with_llm_success(monkeypatch):
    """
    Test that refine_plan_with_llm() applies LLM-suggested lags/window
    features and appends the LLM's reasoning to the plan explanation.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    overrides = PlanOverrides(
        lags=[1, 2, 7],
        window_features=[WindowFeature(stats=["mean"], window_sizes=7)],
        reasoning="Weekly seasonality drives the 7-lag and 7-window choice.",
    )
    agent, call_count = _make_fake_agent([overrides])
    monkeypatch.setattr(assistant, "_plan_refinement_agent", agent)
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    refined, reasoning = assistant.refine_plan_with_llm(
        profile, plan, prompt="Strong weekly cycles."
    )

    assert refined.forecaster_kwargs["lags"] == [1, 2, 7]
    assert refined.forecaster_kwargs["window_features"] == [
        {"stats": ["mean"], "window_sizes": 7}
    ]
    assert reasoning == overrides.reasoning
    assert "Weekly seasonality drives" in refined.explanation
    assert call_count["n"] == 1


# =============================================================================
# Tests: retry-with-feedback loop
# =============================================================================
def test_refine_plan_with_llm_retry_then_success(monkeypatch):
    """
    Test that refine_plan_with_llm() retries with concrete feedback when
    the LLM's first suggestion exceeds the data budget, then succeeds.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    # 100 observations -> budget is int(100 * 0.33) = 33.
    bad_overrides = PlanOverrides(
        lags=50, window_features=None, reasoning="First (infeasible) attempt."
    )
    good_overrides = PlanOverrides(
        lags=[1, 2, 7], window_features=None, reasoning="Fixed after retry."
    )
    agent, call_count = _make_fake_agent([bad_overrides, good_overrides])
    monkeypatch.setattr(assistant, "_plan_refinement_agent", agent)
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    refined, reasoning = assistant.refine_plan_with_llm(
        profile, plan, prompt="Strong weekly cycles."
    )

    assert refined.forecaster_kwargs["lags"] == [1, 2, 7]
    assert reasoning == "Fixed after retry."
    assert call_count["n"] == 2


def test_refine_plan_with_llm_all_retries_fail_returns_original_plan(monkeypatch):
    """
    Test that refine_plan_with_llm() falls back to the original plan after
    all retries are exhausted, emitting a UserWarning.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    # Always over budget (budget is 33 for this fixture).
    bad_overrides = PlanOverrides(
        lags=50, window_features=None, reasoning="Always infeasible."
    )
    agent, call_count = _make_fake_agent([bad_overrides])
    monkeypatch.setattr(assistant, "_plan_refinement_agent", agent)
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        refined, reasoning = assistant.refine_plan_with_llm(
            profile, plan, prompt="Strong weekly cycles."
        )

    assert refined is plan
    assert reasoning.startswith("LLM refinement failed:")
    assert call_count["n"] == 3
    fail_warnings = [
        x for x in w if "LLM plan refinement failed after" in str(x.message)
    ]
    assert len(fail_warnings) == 1


def test_refine_plan_with_llm_transient_failure_is_not_retried(monkeypatch):
    """
    Test that a transient/model error (e.g. network failure) returns the
    original plan immediately, without retrying with budget feedback.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    call_count = {"n": 0}

    class _FailingAgent:
        async def run(self, msg, **kw):
            call_count["n"] += 1
            raise RuntimeError("connection reset")

    monkeypatch.setattr(assistant, "_plan_refinement_agent", _FailingAgent())
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        refined, reasoning = assistant.refine_plan_with_llm(
            profile, plan, prompt="Strong weekly cycles."
        )

    assert refined is plan
    assert reasoning == "LLM refinement failed: connection reset"
    # No retries: only one call was made despite max_retries=2.
    assert call_count["n"] == 1
    fail_warnings = [x for x in w if "LLM plan refinement failed (" in str(x.message)]
    assert len(fail_warnings) == 1
