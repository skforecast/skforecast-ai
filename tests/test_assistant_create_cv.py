# Unit test create_cv ForecastingAssistant

import ast
import re
import warnings

import pandas as pd
import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant, LLMRequiredError
from skforecast_ai.schemas import CVParams, CVResult
from tests.fixtures_assistant import (
    df_single,
    df_multi_long,
    df_range_index,
    df_short,
)


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


def test_create_cv_ValueError_when_initial_train_size_date_unparseable():
    """
    Test that create_cv() raises a ValueError naming initial_train_size
    when the date string cannot be parsed, instead of a raw pandas error.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "`initial_train_size` date 'not-a-date' could not be parsed. Use an "
        "ISO date such as '2023-03-01'."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.create_cv(profile, plan, initial_train_size="not-a-date")


@pytest.mark.parametrize(
    "initial_train_size",
    ["2023-03-01", pd.Timestamp("2023-03-01")],
    ids=["str", "Timestamp"],
)
def test_create_cv_ValueError_when_date_initial_train_size_without_datetime_index(
    initial_train_size,
):
    """
    Test that a date-based initial_train_size (string or Timestamp, the
    latter normalised to its string form) raises ValueError on a dataset
    without a datetime index, where the split date cannot be located.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_range_index, target="sales")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "`initial_train_size` is a date ('2023-03-01') but the dataset has no "
        "datetime index with a known frequency, so the split date cannot be "
        "located. Pass an integer number of observations instead."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.create_cv(profile, plan, initial_train_size=initial_train_size)


# =============================================================================
# Tests: basic output
# =============================================================================
def test_create_cv_output_when_single_series_defaults():
    """
    Test that create_cv() returns a CVResult carrying the splitter, the
    resolved configuration, the snippet and the explanation, plus the
    profile and plan it was derived from.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.create_cv(profile, plan)

    assert isinstance(result, CVResult)
    assert isinstance(result.cv, TimeSeriesFold)
    assert isinstance(result.explanation, str)
    assert result.profile is profile
    assert result.plan is plan


def test_create_cv_cv_config_matches_splitter_and_counts_folds():
    """
    Test that `cv_config` mirrors every TimeSeriesFold parameter,
    including `skip_folds` and `allow_incomplete_fold`, and reports the
    fold count the splitter actually produces.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.create_cv(
        profile, plan, initial_train_size=60, refit=False,
        allow_incomplete_fold=False,
    )

    cv = result.cv
    assert result.cv_config == {
        "steps": 10,
        "initial_train_size": cv.initial_train_size,
        "refit": False,
        "fixed_train_size": cv.fixed_train_size,
        "gap": 0,
        "fold_stride": 10,
        "skip_folds": None,
        "allow_incomplete_fold": False,
        "differentiation": None,
        "n_folds": 4,
    }
    assert "4 folds" in result.explanation


def test_create_cv_code_builds_the_same_splitter():
    """
    Test that the `code` snippet is a standalone construction of the
    splitter: executing it yields a TimeSeriesFold with the same
    parameters as `result.cv`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.create_cv(profile, plan, initial_train_size=60, refit=False)

    namespace: dict = {}
    exec(result.code, namespace)  # noqa: S102
    rebuilt = namespace["cv"]

    assert result.code.startswith("from skforecast.model_selection import TimeSeriesFold")
    assert rebuilt.steps == result.cv.steps
    assert rebuilt.initial_train_size == result.cv.initial_train_size
    assert rebuilt.refit == result.cv.refit


def test_create_cv_TypeError_when_result_is_unpacked():
    """
    Test that unpacking the result as the former `(cv, explanation)` tuple
    fails with a message that points to the new attributes. A pydantic
    model would otherwise iterate over its fields and fail with a puzzling
    "too many values to unpack".
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    with pytest.raises(TypeError, match=re.escape("Use `result.cv`")):
        cv, explanation = assistant.create_cv(profile, plan)


def test_create_cv_display_shows_explanation_and_configuration():
    """
    Test that rendering the result to text shows the explanation panel
    and the configuration table with the fold count.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    text = str(assistant.create_cv(profile, plan, initial_train_size=60))

    assert "Cross-Validation Explanation" in text
    assert "Cross-Validation Configuration" in text
    assert "n_folds" in text


def test_create_cv_output_when_default_initial_train_size():
    """
    Test that the default initial_train_size is a date string corresponding
    to approximately 70% of data when a datetime index is available.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    cv = assistant.create_cv(profile, plan).cv

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

    cv = assistant.create_cv(profile, plan).cv

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

    cv_result = assistant.create_cv(profile, plan)
    cv, explanation = cv_result.cv, cv_result.explanation

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

    cv = assistant.create_cv(profile, plan, initial_train_size=50).cv

    assert cv.initial_train_size == 50


def test_create_cv_output_when_initial_train_size_float_override():
    """
    Test that a float initial_train_size is converted to a fraction of
    n_observations.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, initial_train_size=0.5).cv

    # 50% of 100 observations = 50
    assert cv.initial_train_size == 50


def test_create_cv_output_when_initial_train_size_str_date():
    """
    Test that a str (date) initial_train_size is passed through and
    validated against a DatetimeIndex built from the profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv_result = assistant.create_cv(
        profile, plan, initial_train_size="2023-03-01"
    )
    cv = cv_result.cv

    assert isinstance(cv, TimeSeriesFold)
    assert cv.initial_train_size == "2023-03-01"


def test_create_cv_ValueError_when_initial_train_size_str_date_too_late():
    """
    Test that a str (date) initial_train_size leaving fewer than 2 folds
    raises ValueError, mirroring the integer validation path.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    # df_single has 100 daily observations (2023-01-01 .. 2023-04-10). A
    # near-final training date leaves too few observations for 2 folds.
    err_msg = re.escape("At least 2 are required")
    with pytest.raises(ValueError, match=err_msg):
        assistant.create_cv(profile, plan, initial_train_size="2023-04-09")


def test_create_cv_output_when_refit_override():
    """
    Test that explicit refit value overrides the default.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, refit=3).cv

    assert cv.refit == 3


def test_create_cv_output_when_fixed_train_size_override():
    """
    Test that explicit fixed_train_size overrides the default.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, fixed_train_size=True).cv

    assert cv.fixed_train_size is True


def test_create_cv_output_when_gap_override():
    """
    Test that explicit gap value overrides the default.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    cv = assistant.create_cv(profile, plan, gap=2).cv

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

    cv = assistant.create_cv(profile, plan).cv

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

    cv = assistant.create_cv(profile, plan).cv

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

    cv = assistant.create_cv(profile, plan).cv

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

    cv = assistant.create_cv(profile, plan).cv

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
        {"stats": ["mean"], "window_size": 60}
    ]

    cv = assistant.create_cv(profile, plan).cv

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

    explanation = assistant.create_cv(profile, plan).explanation

    assert "10-step horizon" in explanation
    assert "Initial training up to" in explanation


def test_create_cv_output_when_initial_train_size_timestamp():
    """
    Test that a pandas Timestamp initial_train_size is accepted, stored as
    a date string on the splitter and in cv_config, and rendered as a
    quoted string so the snippet is valid Python.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.create_cv(
        profile, plan, initial_train_size=pd.Timestamp("2023-03-01")
    )

    assert result.cv.initial_train_size == "2023-03-01"
    assert result.cv_config["initial_train_size"] == "2023-03-01"
    assert result.cv_config["n_folds"] == 4
    assert "initial_train_size = '2023-03-01'," in result.code
    ast.parse(result.code)


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
        async def run(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    cv_result = assistant.create_cv(
        profile, plan, prompt="I retrain weekly"
    )
    cv, explanation = cv_result.cv, cv_result.explanation

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
        async def run(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    # Override refit and gap
    cv = assistant.create_cv(
        profile, plan, prompt="I retrain weekly", refit=3, gap=1
    ).cv

    assert cv.refit == 3
    assert cv.gap == 1
    # LLM values preserved for non-overridden params
    assert cv.initial_train_size == 50


def test_create_cv_prompt_ignored_when_all_params_explicit(monkeypatch):
    """
    Test that create_cv() skips the LLM entirely (with a UserWarning) when
    every CV parameter the LLM would decide is supplied explicitly.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    class _RaisingAgent:
        async def run(self, msg, **kw):
            raise AssertionError("LLM should not be called")

    monkeypatch.setattr(assistant, "_cv_agent", _RaisingAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cv = assistant.create_cv(
            profile,
            plan,
            prompt="I retrain weekly",
            initial_train_size=50,
            fold_stride=5,
            refit=False,
            fixed_train_size=True,
            gap=0,
            skip_folds=1,
            allow_incomplete_fold=True,
        ).cv

    assert isinstance(cv, TimeSeriesFold)
    assert cv.initial_train_size == 50
    assert cv.refit is False
    assert cv.fixed_train_size is True
    assert cv.gap == 0
    ignored = [
        x
        for x in w
        if "Prompt ignored: all CV parameters were set explicitly" in str(x.message)
    ]
    assert len(ignored) == 1


def test_create_cv_llm_retry_then_success(monkeypatch):
    """
    Test that create_cv() retries on validation failure and succeeds
    on the second attempt.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    n_obs = profile.data_profile.series_lengths["sales"].length

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
        async def run(self, msg, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _FakeResult(bad_params)
            return _FakeResult(good_params)

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    cv = assistant.create_cv(profile, plan, prompt="Forecast ahead").cv

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
    n_obs = profile.data_profile.series_lengths["sales"].length

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
        async def run(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cv = assistant.create_cv(profile, plan, prompt="Bad scenario").cv

    # Should have fallen back to deterministic defaults
    assert isinstance(cv, TimeSeriesFold)
    assert cv.steps == 5
    # Deterministic default: 70% of 100 daily obs = date string '2023-03-11'
    assert cv.initial_train_size == "2023-03-11"

    # Should have emitted a warning
    llm_warnings = [x for x in w if "LLM CV configuration failed" in str(x.message)]
    assert len(llm_warnings) == 1


def _make_cv_params(initial_train_size, reasoning: str) -> CVParams:
    """Build CVParams around `initial_train_size` with neutral defaults."""
    return CVParams(
        initial_train_size    = initial_train_size,
        refit                 = True,
        fixed_train_size      = False,
        gap                   = 0,
        fold_stride           = None,
        skip_folds            = None,
        allow_incomplete_fold = True,
        reasoning             = reasoning,
    )


def _install_fake_cv_agent(monkeypatch, assistant, outputs: list[CVParams]) -> dict:
    """Install a fake CV agent yielding `outputs` in order (last one repeats)."""
    call_count = {"n": 0}

    class _FakeResult:
        def __init__(self, params):
            self.output = params

    class _FakeAgent:
        async def run(self, msg, **kw):
            i = min(call_count["n"], len(outputs) - 1)
            call_count["n"] += 1
            return _FakeResult(outputs[i])

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())
    monkeypatch.setattr(assistant, "_resolve_model", lambda self_=None: "fake-model")
    return call_count


def test_create_cv_llm_retry_then_success_when_date_out_of_range(monkeypatch):
    """
    Test that a date-based initial_train_size outside the series range
    is caught inside the LLM retry loop (not after it) and the second
    suggestion is used.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    call_count = _install_fake_cv_agent(
        monkeypatch,
        assistant,
        [
            _make_cv_params("2030-01-01", "Beyond the last date."),
            _make_cv_params(50, "Fixed after retry."),
        ],
    )

    cv = assistant.create_cv(profile, plan, prompt="Forecast ahead").cv

    assert cv.initial_train_size == 50
    assert call_count["n"] == 2


def test_create_cv_llm_deterministic_fallback_when_date_unparseable(monkeypatch):
    """
    Test that an unparseable date-based initial_train_size exhausts the
    LLM retries and create_cv() degrades to the deterministic defaults
    with a UserWarning, instead of raising a pandas parsing error.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)

    call_count = _install_fake_cv_agent(
        monkeypatch, assistant, [_make_cv_params("next spring", "Always bad.")]
    )

    warn_msg = re.escape(
        "LLM CV configuration failed after 3 attempts (last error: "
        "`initial_train_size` date 'next spring' could not be parsed. Use an "
        "ISO date such as '2023-03-01'.). Falling back to deterministic "
        "defaults."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        cv = assistant.create_cv(profile, plan, prompt="Bad scenario").cv

    assert call_count["n"] == 3
    assert cv.initial_train_size == "2023-03-11"


def test_create_cv_llm_deterministic_fallback_when_date_on_range_index(monkeypatch):
    """
    Test that a date-based LLM suggestion on a dataset without a datetime
    index is rejected inside the retry loop and the deterministic integer
    default is used, with a UserWarning.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=df_range_index, target="sales")
    plan = assistant.plan(profile, steps=5)

    _install_fake_cv_agent(
        monkeypatch, assistant, [_make_cv_params("2023-03-01", "A date.")]
    )

    warn_msg = re.escape(
        "`initial_train_size` is a date ('2023-03-01') but the dataset has no "
        "datetime index with a known frequency"
    )
    with pytest.warns(UserWarning, match=warn_msg):
        cv = assistant.create_cv(profile, plan, prompt="Some scenario").cv

    assert cv.initial_train_size == 70


@pytest.mark.parametrize(
    "data, profile_kwargs, expected",
    [
        (df_single, {"date_column": "date"}, ("2023-01-01", "2023-04-10")),
        (df_range_index, {}, (None, None)),
    ],
    ids=["datetime_index", "range_index"],
)
def test_create_cv_llm_deps_carry_date_range(
    monkeypatch, data, profile_kwargs, expected
):
    """
    Test that the CV agent receives the first and last date of the series
    when the dataset has a datetime index with a known frequency, and no
    dates otherwise, matching the rule `count_cv_folds` applies.
    """
    assistant = ForecastingAssistant(llm="openai:fake-model")
    profile = assistant.profile(data=data, target="sales", **profile_kwargs)
    plan = assistant.plan(profile, steps=5)
    captured = {}

    class _FakeResult:
        output = _make_cv_params(50, "Fifty observations.")

    class _FakeAgent:
        async def run(self, msg, **kw):
            captured["deps"] = kw["deps"]
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())
    monkeypatch.setattr(assistant, "_resolve_model", lambda self_=None: "fake-model")

    assistant.create_cv(profile, plan, prompt="Retrain weekly.")

    deps = captured["deps"]
    assert (deps.start_date, deps.end_date) == expected
    assert deps.n_observations == 100


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
        async def run(self, msg, **kw):
            return _FakeResult()

    monkeypatch.setattr(assistant, "_cv_agent", _FakeAgent())

    def _mock_resolve_model(self_=None):
        return "fake-model-string"

    monkeypatch.setattr(assistant, "_resolve_model", _mock_resolve_model)

    explanation = assistant.create_cv(
        profile, plan, prompt="Use expanding window"
    ).explanation

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
    cv_result = assistant.create_cv(profile, plan)
    cv, explanation = cv_result.cv, cv_result.explanation

    assert isinstance(cv, TimeSeriesFold)
    assert cv.steps == 5
    assert "Initial training up to" in explanation
