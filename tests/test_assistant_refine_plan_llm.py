# Unit test refine_plan (LLM path) ForecastingAssistant

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
def test_refine_plan_LLMRequiredError_when_prompt_and_no_llm():
    """
    Test that refine_plan() raises LLMRequiredError when a prompt is passed
    but no LLM is configured.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "`refine_plan()` requires an LLM. "
        "Pass `llm=...` when creating ForecastingAssistant."
    )
    with pytest.raises(LLMRequiredError, match=err_msg):
        assistant.refine_plan(profile, plan, prompt="weekly seasonality")


def test_refine_plan_prompt_skips_when_statistical_task_type(monkeypatch):
    """
    Test that refine_plan() ignores the prompt for task_type 'statistical'
    without calling the LLM, emitting a UserWarning.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    plan = plan.model_copy(update={"task_type": "statistical"})

    # No agent/model mock set up: if the LLM were called, this would raise.
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        refined = assistant.refine_plan(
            profile, plan, prompt="weekly seasonality"
        )

    assert refined is not None
    assert "LLM Refinement Reasoning" not in refined.explanation
    skip_warnings = [x for x in w if "does not apply to task_type" in str(x.message)]
    assert len(skip_warnings) == 1


# =============================================================================
# Tests: success path
# =============================================================================
def test_refine_plan_prompt_success(monkeypatch):
    """
    Test that refine_plan() applies LLM-suggested lags/window features and
    appends the LLM's reasoning to the plan explanation.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    overrides = PlanOverrides(
        lags=[1, 2, 7],
        window_features=[WindowFeature(stats=["mean"], window_size=7)],
        reasoning="Weekly seasonality drives the 7-lag and 7-window choice.",
    )
    agent, call_count = _make_fake_agent([overrides])
    monkeypatch.setattr(assistant, "_plan_refinement_agent", agent)
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    refined = assistant.refine_plan(profile, plan, prompt="Strong weekly cycles.")

    assert refined.forecaster_kwargs["lags"] == [1, 2, 7]
    assert refined.forecaster_kwargs["window_features"] == [
        {"stats": ["mean"], "window_size": 7}
    ]
    assert "Weekly seasonality drives" in refined.explanation
    assert "LLM Refinement Reasoning" in refined.explanation
    # Nothing was shadowed, so no override note is appended.
    assert "took precedence over the LLM suggestion" not in refined.explanation
    # Both features came from the LLM and are flagged as such.
    assert refined.llm_refined_fields == ["lags", "window_features"]
    # The not-validated caveat is appended for LLM-sourced features.
    assert "are hypotheses, not" in refined.explanation
    assert "Confirm any expected accuracy" in refined.explanation
    assert call_count["n"] == 1


# =============================================================================
# Tests: Category-A conflict (explicit lags/window_features + prompt)
# =============================================================================
def test_refine_plan_prompt_explicit_lags_shadow_llm(monkeypatch):
    """
    Test that an explicit lags override wins over the LLM suggestion (with a
    UserWarning) while the LLM-suggested window_features are still applied.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    overrides = PlanOverrides(
        lags=[1, 2, 7],
        window_features=[WindowFeature(stats=["mean"], window_size=7)],
        reasoning="Weekly seasonality.",
    )
    agent, call_count = _make_fake_agent([overrides])
    monkeypatch.setattr(assistant, "_plan_refinement_agent", agent)
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        refined = assistant.refine_plan(
            profile, plan, prompt="Strong weekly cycles.", lags=[3, 4, 5]
        )

    # Explicit lags win; LLM window_features are applied.
    assert refined.forecaster_kwargs["lags"] == [3, 4, 5]
    assert refined.forecaster_kwargs["window_features"] == [
        {"stats": ["mean"], "window_size": 7}
    ]
    assert call_count["n"] == 1
    shadow = [x for x in w if "Explicit lags override shadowed" in str(x.message)]
    assert len(shadow) == 1
    # Only the LLM-sourced window_features is flagged as refined.
    assert refined.llm_refined_fields == ["window_features"]
    # The persisted explanation records which field the override replaced.
    assert (
        "explicit override(s) took precedence over the LLM suggestion for: lags"
        in refined.explanation
    )


def test_refine_plan_prompt_explicit_window_features_shadow_llm(monkeypatch):
    """
    Test that an explicit window_features override wins over the LLM
    suggestion (with a UserWarning) while LLM-suggested lags are applied.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    overrides = PlanOverrides(
        lags=[1, 2, 7],
        window_features=[WindowFeature(stats=["mean"], window_size=7)],
        reasoning="Weekly seasonality.",
    )
    agent, call_count = _make_fake_agent([overrides])
    monkeypatch.setattr(assistant, "_plan_refinement_agent", agent)
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    explicit_wf = [{"stats": ["std"], "window_size": 3}]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        refined = assistant.refine_plan(
            profile,
            plan,
            prompt="Strong weekly cycles.",
            window_features=explicit_wf,
        )

    # Explicit window_features win; LLM lags are applied.
    assert refined.forecaster_kwargs["lags"] == [1, 2, 7]
    assert refined.forecaster_kwargs["window_features"] == explicit_wf
    assert call_count["n"] == 1
    shadow = [
        x for x in w if "Explicit window_features override shadowed" in str(x.message)
    ]
    assert len(shadow) == 1
    # Only the LLM-sourced lags is flagged as refined.
    assert refined.llm_refined_fields == ["lags"]
    # The persisted explanation records which field the override replaced.
    assert (
        "explicit override(s) took precedence over the LLM suggestion for: "
        "window_features"
        in refined.explanation
    )


def test_refine_plan_prompt_ignored_when_both_lags_and_wf_explicit(monkeypatch):
    """
    Test that refine_plan() skips the LLM entirely (with a UserWarning) when
    both lags and window_features are supplied explicitly alongside a prompt.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    # An agent that must not be invoked.
    agent, call_count = _make_fake_agent(
        [PlanOverrides(lags=[9], window_features=None, reasoning="unused")]
    )
    monkeypatch.setattr(assistant, "_plan_refinement_agent", agent)
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    explicit_wf = [{"stats": ["std"], "window_size": 3}]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        refined = assistant.refine_plan(
            profile,
            plan,
            prompt="Strong weekly cycles.",
            lags=[3, 4, 5],
            window_features=explicit_wf,
        )

    assert refined.forecaster_kwargs["lags"] == [3, 4, 5]
    assert refined.forecaster_kwargs["window_features"] == explicit_wf
    assert "LLM Refinement Reasoning" not in refined.explanation
    assert call_count["n"] == 0
    ignored = [
        x
        for x in w
        if "Prompt ignored: both lags and window_features" in str(x.message)
    ]
    assert len(ignored) == 1


def test_refine_plan_prompt_no_shadow_warning_when_llm_field_absent(monkeypatch):
    """
    Test that no shadow warning is emitted for a field the LLM did not
    suggest, even when that field is overridden explicitly.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    # LLM suggests only lags; it returns no window_features.
    overrides = PlanOverrides(
        lags=[1, 2, 7], window_features=None, reasoning="Weekly seasonality."
    )
    agent, call_count = _make_fake_agent([overrides])
    monkeypatch.setattr(assistant, "_plan_refinement_agent", agent)
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    explicit_wf = [{"stats": ["std"], "window_size": 3}]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        refined = assistant.refine_plan(
            profile,
            plan,
            prompt="Strong weekly cycles.",
            window_features=explicit_wf,
        )

    # LLM lags applied; explicit window_features applied.
    assert refined.forecaster_kwargs["lags"] == [1, 2, 7]
    assert refined.forecaster_kwargs["window_features"] == explicit_wf
    assert call_count["n"] == 1
    # The LLM never suggested window_features, so nothing was shadowed.
    shadow = [x for x in w if "shadowed" in str(x.message)]
    assert len(shadow) == 0


def test_refine_plan_prompt_preserves_existing_lags_when_llm_omits_them(monkeypatch):
    """
    Test that a field the LLM omits (None) keeps the plan's existing value
    instead of re-running the deterministic selection.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    # Pin explicit, non-default lags so preservation is distinguishable from a
    # fresh PACF-based reselection.
    plan = assistant.refine_plan(profile, plan, lags=[1, 5, 9])
    assert plan.forecaster_kwargs["lags"] == [1, 5, 9]

    # LLM suggests only window_features; it returns no lags.
    overrides = PlanOverrides(
        lags=None,
        window_features=[WindowFeature(stats=["mean"], window_size=7)],
        reasoning="Only a rolling mean is needed.",
    )
    agent, call_count = _make_fake_agent([overrides])
    monkeypatch.setattr(assistant, "_plan_refinement_agent", agent)
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    refined = assistant.refine_plan(profile, plan, prompt="Rolling mean matters.")

    # Existing lags preserved; LLM window_features applied.
    assert refined.forecaster_kwargs["lags"] == [1, 5, 9]
    assert refined.forecaster_kwargs["window_features"] == [
        {"stats": ["mean"], "window_size": 7}
    ]
    assert "Only a rolling mean is needed." in refined.explanation
    assert call_count["n"] == 1


def test_refine_plan_prompt_over_budget_explicit_override_raises_before_llm(monkeypatch):
    """
    Test that an explicit lags override exceeding the data budget raises
    ValueError before any LLM call is made.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    class _RaisingAgent:
        async def run(self, msg, **kw):
            raise AssertionError("LLM should not be called")

    monkeypatch.setattr(assistant, "_plan_refinement_agent", _RaisingAgent())
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    # 100 observations -> budget is int(100 * 0.33) = 33; 50 exceeds it.
    with pytest.raises(ValueError, match=re.escape("exceeding the maximum")):
        assistant.refine_plan(
            profile, plan, prompt="Strong weekly cycles.", lags=50
        )


# =============================================================================
# Tests: retry-with-feedback loop
# =============================================================================
def test_refine_plan_prompt_retry_then_success(monkeypatch):
    """
    Test that refine_plan() retries with concrete feedback when the LLM's
    first suggestion exceeds the data budget, then succeeds.
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

    refined = assistant.refine_plan(profile, plan, prompt="Strong weekly cycles.")

    assert refined.forecaster_kwargs["lags"] == [1, 2, 7]
    assert "Fixed after retry." in refined.explanation
    assert call_count["n"] == 2


def test_refine_plan_prompt_all_retries_fail_returns_deterministic_plan(monkeypatch):
    """
    Test that refine_plan() falls back to the deterministic plan after all
    retries are exhausted, emitting a UserWarning and appending no reasoning.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    original_lags = plan.forecaster_kwargs.get("lags")

    # Always over budget (budget is 33 for this fixture).
    bad_overrides = PlanOverrides(
        lags=50, window_features=None, reasoning="Always infeasible."
    )
    agent, call_count = _make_fake_agent([bad_overrides])
    monkeypatch.setattr(assistant, "_plan_refinement_agent", agent)
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        refined = assistant.refine_plan(profile, plan, prompt="Strong weekly cycles.")

    # Deterministic fallback preserves the original features; no reasoning.
    assert refined.forecaster_kwargs.get("lags") == original_lags
    assert "LLM Refinement Reasoning" not in refined.explanation
    assert call_count["n"] == 3
    fail_warnings = [
        x for x in w if "LLM plan refinement failed after" in str(x.message)
    ]
    assert len(fail_warnings) == 1


def test_refine_plan_prompt_transient_failure_is_not_retried(monkeypatch):
    """
    Test that a transient/model error (e.g. network failure) returns the
    deterministic plan immediately, without retrying with budget feedback.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    original_lags = plan.forecaster_kwargs.get("lags")

    call_count = {"n": 0}

    class _FailingAgent:
        async def run(self, msg, **kw):
            call_count["n"] += 1
            raise RuntimeError("connection reset")

    monkeypatch.setattr(assistant, "_plan_refinement_agent", _FailingAgent())
    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        refined = assistant.refine_plan(profile, plan, prompt="Strong weekly cycles.")

    assert refined.forecaster_kwargs.get("lags") == original_lags
    assert "LLM Refinement Reasoning" not in refined.explanation
    # No retries: only one call was made despite max_retries=2.
    assert call_count["n"] == 1
    fail_warnings = [x for x in w if "LLM plan refinement failed (" in str(x.message)]
    assert len(fail_warnings) == 1
