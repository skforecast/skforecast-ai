# Unit test create_cv ForecastingAssistant

import re
import warnings

import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant, LLMRequiredError
from skforecast_ai.schemas import CVParams
from tests.fixtures_assistant import df_single, df_multi_long, df_short


# =============================================================================
# Tests: error / validation
# =============================================================================
@pytest.mark.parametrize(
    "value",
    [0.0, 1.0, -0.1, 1.5],
    ids=lambda v: f"initial_train_size: {v}",
)
def test_create_cv_ValueError_when_initial_train_size_float_out_of_range(value):
    """
    Test that create_cv() raises ValueError when initial_train_size is a
    float outside the open interval (0, 1).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "initial_train_size as float must satisfy 0 < value < 1"
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.create_cv(profile, plan, initial_train_size=value)


def test_create_cv_ValueError_when_fewer_than_2_folds():
    """
    Test that create_cv() raises ValueError when the configuration
    produces fewer than 2 folds.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_short, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape("At least 2 are required")
    with pytest.raises(ValueError, match=err_msg):
        assistant.create_cv(profile, plan, initial_train_size=20)


# =============================================================================
# Tests: basic output
# =============================================================================
def test_create_cv_output_when_single_series_defaults():
    """
    Test that create_cv() returns a tuple of (TimeSeriesFold, str) with
    correct types for a single-series profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.create_cv(profile, plan)

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], TimeSeriesFold)
    assert isinstance(result[1], str)


def test_create_cv_output_when_default_initial_train_size():
    """
    Test that the default initial_train_size is a date string corresponding
    to approximately 70% of data when a datetime index is available.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    cv, _ = assistant.create_cv(profile, plan)

    # 70% of 100 daily observations starting 2023-01-01 → position 70 → date at
    # index 69 = 2023-01-01 + 69 days = 2023-03-11
    assert cv.initial_train_size == "2023-03-11"


def test_create_cv_output_when_steps_from_plan():
    """
    Test that cv.steps equals plan.steps.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=7)

    cv, _ = assistant.create_cv(profile, plan)

    assert cv.steps == 7


def test_create_cv_output_when_multi_series_defaults():
    """
    Test that create_cv() works for multi-series profiles.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.plan(profile, steps=5)

    cv, explanation = assistant.create_cv(profile, plan)

    assert isinstance(cv, TimeSeriesFold)
    assert cv.steps == 5
    assert "5-step horizon" in explanation


# =============================================================================
# Tests: explicit overrides
# =============================================================================
def test_create_cv_output_when_initial_train_size_int_override():
    """
    Test that an explicit int initial_train_size is used directly.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv, _ = assistant.create_cv(profile, plan, initial_train_size=50)

    assert cv.initial_train_size == 50


def test_create_cv_output_when_initial_train_size_float_override():
    """
    Test that a float initial_train_size is converted to a fraction of
    n_observations.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv, _ = assistant.create_cv(profile, plan, initial_train_size=0.5)

    # 50% of 100 observations = 50
    assert cv.initial_train_size == 50


def test_create_cv_output_when_initial_train_size_str_skips_validation():
    """
    Test that a str initial_train_size is passed through without fold
    count validation.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    # A date far into the future would fail validation, but str skips it
    cv, explanation = assistant.create_cv(
        profile, plan, initial_train_size="2023-03-01"
    )

    assert isinstance(cv, TimeSeriesFold)
    assert cv.initial_train_size == "2023-03-01"


def test_create_cv_output_when_refit_override():
    """
    Test that explicit refit value overrides the default.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv, _ = assistant.create_cv(profile, plan, refit=3)

    assert cv.refit == 3


def test_create_cv_output_when_fixed_train_size_override():
    """
    Test that explicit fixed_train_size overrides the default.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv, _ = assistant.create_cv(profile, plan, fixed_train_size=True)

    assert cv.fixed_train_size is True


def test_create_cv_output_when_gap_override():
    """
    Test that explicit gap value overrides the default.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv, _ = assistant.create_cv(profile, plan, gap=2)

    assert cv.gap == 2


# =============================================================================
# Tests: task-type floor logic
# =============================================================================
def test_create_cv_output_when_floor_by_lags_int():
    """
    Test that initial_train_size is floored to (lags + steps) when lags
    is int and that value exceeds the forecaster's window_size.
    """
    assistant = ForecastingAssistant()
    # Use short data where 70% = 17, but lags force a higher floor
    profile = assistant.profile(data=df_short, target="sales", date_column="date")
    # Steps=1 so we can get many folds even with small data
    plan = assistant.plan(profile, steps=1)

    # Override lags in the plan to force a specific floor
    plan.forecaster_kwargs["lags"] = 20  # floor = 20 + 1 = 21

    cv, _ = assistant.create_cv(profile, plan)

    # With 25 obs, 70% = 17. Floor = 21 (> 17). Ceiling = 25 - 2*1 = 23.
    # So initial_train_size = 21. Date at index 20 = 2023-01-21.
    assert cv.initial_train_size == "2023-01-21"


def test_create_cv_output_when_floor_by_lags_list():
    """
    Test that initial_train_size floor uses max(lags) + steps when lags
    is a list, and that the result exceeds the forecaster's window_size.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_short, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=1)

    plan.forecaster_kwargs["lags"] = [1, 5, 22]  # floor = 22 + 1 = 23

    cv, _ = assistant.create_cv(profile, plan)

    # With 25 obs, 70% = 17. Floor = 23 (> 17). Ceiling = 25 - 2*1 = 23.
    # Both constraints give 23. Date at index 22 = 2023-01-23.
    assert cv.initial_train_size == "2023-01-23"


def test_create_cv_output_when_statistical_floor():
    """
    Test that statistical task uses 2 * steps as floor.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats"
    )

    cv, _ = assistant.create_cv(profile, plan)

    # floor = 2*10 = 20, 70% of 100 = 70. 70 > 20, so 70 is used.
    # ceiling = 100 - 2*10 = 80. So initial_train_size = 70.
    # Date at index 69 = 2023-01-01 + 69 days = 2023-03-11.
    assert cv.initial_train_size == "2023-03-11"


def test_create_cv_output_when_differentiation_set():
    """
    Test that differentiation flows from plan.forecaster_kwargs to the
    TimeSeriesFold.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    plan.forecaster_kwargs["differentiation"] = 1

    cv, _ = assistant.create_cv(profile, plan)

    assert cv.differentiation == 1


def test_create_cv_output_when_floor_by_window_features():
    """
    Test that initial_train_size accounts for window_features when the
    max window_size exceeds max(lags), preventing skforecast ValueError.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    # Lags = 10 (window_size from lags alone = 10)
    # Window features with window_size = 60 → effective window = 60
    plan.forecaster_kwargs["lags"] = 10
    plan.forecaster_kwargs["window_features"] = [
        {"stats": ["mean"], "window_sizes": 60}
    ]

    cv, _ = assistant.create_cv(profile, plan)

    # Floor = effective_window + steps = 60 + 5 = 65.
    # 70% of 100 = 70. max(70, 65) = 70. Ceiling = 100 - 10 = 90.
    # initial_train_size = 70. Date at index 69 = 2023-03-11.
    assert cv.initial_train_size == "2023-03-11"


# =============================================================================
# Tests: explanation
# =============================================================================
def test_create_cv_explanation_contains_key_params():
    """
    Test that the explanation string mentions the key parameters.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    _, explanation = assistant.create_cv(profile, plan)

    assert "10-step horizon" in explanation
    assert "Initial training up to" in explanation


# =============================================================================
# Tests: LLM path
# =============================================================================
def test_create_cv_LLMRequiredError_when_prompt_but_no_llm():
    """
    Test that create_cv() raises LLMRequiredError when prompt is
    provided but no LLM is configured.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "`create_cv()` requires an LLM. "
        "Pass `llm=...` when creating ForecastingAssistant."
    )
    with pytest.raises(LLMRequiredError, match=err_msg):
        assistant.create_cv(profile, plan, prompt="I retrain weekly")


def test_create_cv_llm_success(monkeypatch):
    """
    Test that create_cv() uses LLM-returned parameters when prompt is
    provided and LLM is configured.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    # Mock the CV agent to return specific params
    cv_params = CVParams(
        initial_train_size=50,
        refit=False,
        fixed_train_size=True,
        gap=2,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Weekly retraining with 2-day gap.",
    )

    class _FakeResult:
        output = cv_params

    class _FakeAgent:
        def run_sync(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    cv, explanation = assistant.create_cv(
        profile, plan, prompt="I retrain weekly"
    )

    assert isinstance(cv, TimeSeriesFold)
    assert cv.initial_train_size == 50
    assert cv.refit is False
    assert cv.fixed_train_size is True
    assert cv.gap == 2
    assert "Weekly retraining" in explanation


def test_create_cv_llm_kwargs_override_llm(monkeypatch):
    """
    Test that explicit kwargs override LLM-returned parameters.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv_params = CVParams(
        initial_train_size=50,
        refit=True,
        fixed_train_size=False,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Default strategy.",
    )

    class _FakeResult:
        output = cv_params

    class _FakeAgent:
        def run_sync(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    # Override refit and gap
    cv, _ = assistant.create_cv(
        profile, plan, prompt="I retrain weekly", refit=3, gap=1
    )

    assert cv.refit == 3
    assert cv.gap == 1
    # LLM values preserved for non-overridden params
    assert cv.initial_train_size == 50


def test_create_cv_llm_retry_then_success(monkeypatch):
    """
    Test that create_cv() retries on validation failure and succeeds
    on the second attempt.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    n_obs = profile.data_profile.n_observations

    # First call: initial_train_size too large (only 1 fold)
    bad_params = CVParams(
        initial_train_size=n_obs - 3,  # Too large for 2 folds
        refit=True,
        fixed_train_size=False,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Bad first attempt.",
    )
    good_params = CVParams(
        initial_train_size=50,
        refit=True,
        fixed_train_size=False,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Fixed after retry.",
    )

    call_count = {"n": 0}

    class _FakeResult:
        def __init__(self, params):
            self.output = params

    class _FakeAgent:
        def run_sync(self, msg, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _FakeResult(bad_params)
            return _FakeResult(good_params)

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    cv, _ = assistant.create_cv(profile, plan, prompt="Forecast ahead")

    assert cv.initial_train_size == 50
    assert call_count["n"] == 2


def test_create_cv_llm_all_retries_fail_deterministic_fallback(monkeypatch):
    """
    Test that create_cv() falls back to deterministic defaults after
    all LLM retries are exhausted, emitting a UserWarning.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    n_obs = profile.data_profile.n_observations

    # Always return params that are too large
    bad_params = CVParams(
        initial_train_size=n_obs - 3,
        refit=True,
        fixed_train_size=False,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Always bad.",
    )

    class _FakeResult:
        output = bad_params

    class _FakeAgent:
        def run_sync(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cv, _ = assistant.create_cv(profile, plan, prompt="Bad scenario")

    # Should have fallen back to deterministic defaults
    assert isinstance(cv, TimeSeriesFold)
    assert cv.steps == 5
    # Deterministic default: 70% of 100 daily obs = date string '2023-03-11'
    assert cv.initial_train_size == "2023-03-11"

    # Should have emitted a warning
    llm_warnings = [x for x in w if "LLM CV configuration failed" in str(x.message)]
    assert len(llm_warnings) == 1


def test_create_cv_llm_explanation_includes_reasoning(monkeypatch):
    """
    Test that the explanation includes the LLM's reasoning field.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv_params = CVParams(
        initial_train_size=60,
        refit=True,
        fixed_train_size=False,
        gap=0,
        fold_stride=None,
        skip_folds=None,
        allow_incomplete_fold=True,
        reasoning="Expanding window chosen because data has no concept drift.",
    )

    class _FakeResult:
        output = cv_params

    class _FakeAgent:
        def run_sync(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    _, explanation = assistant.create_cv(
        profile, plan, prompt="Use expanding window"
    )

    assert "concept drift" in explanation


def test_create_cv_deterministic_when_no_prompt_and_llm_configured():
    """
    Test that create_cv() uses deterministic defaults when no prompt is
    provided, even if an LLM is configured. No LLM call is made.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    # No prompt → deterministic path. _cv_agent is never called.
    # If it were called, it would fail because no mock is set up and
    # _resolve_model would fail for "openai:fake-model" without env var.
    cv, explanation = assistant.create_cv(profile, plan)

    assert isinstance(cv, TimeSeriesFold)
    assert cv.steps == 5
    assert "Initial training up to" in explanation
