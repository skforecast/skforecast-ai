# Unit test refine_plan ForecastingAssistant

import re

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.schemas import ForecastPlan

from tests.fixtures_assistant import df_single


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_refine_plan_ValueError_when_invalid_override_key():
    """
    Test that refine_plan() raises ValueError when an unsupported
    override key is passed.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "Invalid override keys: ['not_a_valid_key']. "
        "Allowed keys: ['estimator', 'estimator_kwargs', 'forecaster', 'interval', 'lags', 'steps', 'window_features']."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.refine_plan(profile, plan, not_a_valid_key="something")


def test_refine_plan_ValueError_when_lags_exceed_data_budget():
    """
    Test that explicit lags spanning more than the allowed fraction of the
    available observations raise ValueError before building the plan.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    # 100 observations -> budget is int(100 * 0.33) = 33.
    with pytest.raises(ValueError, match=re.escape("exceeding the maximum")):
        assistant.refine_plan(profile, plan, lags=50)


def test_refine_plan_ValueError_when_lags_duplicated():
    """
    Test that an explicit lags override with duplicated values raises
    ValueError before the plan is rebuilt.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape("`lags` must not contain duplicates, got [2, 2].")
    with pytest.raises(ValueError, match=err_msg):
        assistant.refine_plan(profile, plan, lags=[2, 2])


def test_refine_plan_output_when_lags_within_budget():
    """
    Test that an explicit lag override within the data budget is applied.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan, lags=[1, 2, 7])

    assert refined.forecaster_kwargs["lags"] == [1, 2, 7]


def test_refine_plan_ValueError_when_forecaster_not_in_candidates():
    """
    Test that refine_plan() raises ValueError when the overridden
    forecaster is not in the profile's candidate list.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "Forecaster 'ForecasterRnn' is not compatible with this profile."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.refine_plan(profile, plan, forecaster="ForecasterRnn")


# =============================================================================
# Tests: basic output
# =============================================================================
def test_refine_plan_output_when_no_overrides():
    """
    Test that refine_plan() with no overrides returns a plan equivalent
    to the original (same key parameters).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan)

    assert refined.steps == plan.steps
    assert refined.forecaster == plan.forecaster
    assert refined.estimator == plan.estimator
    assert refined.interval == plan.interval
    assert refined.task_type == plan.task_type


def test_refine_plan_output_when_steps_overridden():
    """
    Test that refine_plan() returns a new plan with the overridden steps
    while preserving the original plan's forecaster and estimator.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan, steps=24)

    assert isinstance(refined, ForecastPlan)
    assert refined.steps == 24
    assert refined.forecaster == plan.forecaster
    assert refined.estimator == plan.estimator


# =============================================================================
# Tests: feature-rich (individual overrides)
# =============================================================================
def test_refine_plan_output_when_forecaster_overridden():
    """
    Test that refine_plan() applies a forecaster override and re-derives
    the plan accordingly.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan, forecaster="ForecasterDirect")

    assert refined.forecaster == "ForecasterDirect"
    assert refined.steps == plan.steps
    assert refined.task_type == "single_series"


def test_refine_plan_output_when_estimator_overridden():
    """
    Test that refine_plan() applies an estimator override.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan, estimator="RandomForestRegressor")

    assert refined.estimator == "RandomForestRegressor"
    assert refined.forecaster == plan.forecaster
    assert refined.steps == plan.steps


def test_refine_plan_output_when_estimator_kwargs_overridden():
    """
    Test that refine_plan() applies estimator_kwargs override.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    custom_kwargs = {"n_estimators": 200, "learning_rate": 0.05}
    refined = assistant.refine_plan(profile, plan, estimator_kwargs=custom_kwargs)

    assert refined.estimator_kwargs == custom_kwargs


def test_refine_plan_output_when_interval_added():
    """
    Test that refine_plan() adds prediction intervals to a plan that
    previously had none.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    assert plan.interval is None

    refined = assistant.refine_plan(profile, plan, interval=[0.1, 0.9])

    assert refined.interval == [0.1, 0.9]
    assert refined.interval_method == "bootstrapping"


def test_refine_plan_output_when_interval_removed():
    """
    Test that refine_plan() removes prediction intervals when
    interval=None is explicitly passed.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, interval=[0.1, 0.9])

    assert plan.interval == [0.1, 0.9]

    refined = assistant.refine_plan(profile, plan, interval=None)

    assert refined.interval is None
    assert refined.interval_method is None


# =============================================================================
# Tests: edge cases (multiple overrides, preserved state)
# =============================================================================
def test_refine_plan_output_when_multiple_overrides():
    """
    Test that refine_plan() applies multiple overrides simultaneously.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(
        profile, plan,
        steps=30,
        estimator="XGBRegressor",
        interval=[0.2, 0.8],
    )

    assert refined.steps == 30
    assert refined.estimator == "XGBRegressor"
    assert refined.interval == [0.2, 0.8]
    assert refined.interval_method == "bootstrapping"


def test_refine_plan_preserves_custom_forecaster_when_other_fields_refined():
    """
    Test that when the original plan was created with a custom forecaster,
    refine_plan() preserves it even when other fields are overridden.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterDirect"
    )

    refined = assistant.refine_plan(profile, plan, steps=24, interval=[0.05, 0.95])

    assert refined.forecaster == "ForecasterDirect"
    assert refined.steps == 24
    assert refined.interval == [0.05, 0.95]


def test_refine_plan_output_resets_end_train():
    """
    Test that refine_plan() does not carry the `end_train` split boundary
    over to the refined plan. The boundary was derived from the original
    horizon and test size, so keeping it would make a refined plan run in
    evaluation mode (and fail when the new horizon exceeds the test set)
    instead of forecasting the future.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10).model_copy(
        update={"end_train": "2023-03-01"}
    )

    refined = assistant.refine_plan(profile, plan, steps=5)

    assert refined.end_train is None
    assert refined.steps == 5


def test_refine_plan_output_preserves_llm_refined_fields_when_not_overridden():
    """
    Test that an LLM mark on the original plan survives a deterministic
    refinement of an unrelated field, since the marked value itself is
    carried over from `plan.forecaster_kwargs`, and that the mark is
    dropped once the field is overridden explicitly.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10).model_copy(
        update={"llm_refined_fields": ["lags"]}
    )

    refined_unrelated = assistant.refine_plan(
        profile, plan, estimator_kwargs={"n_estimators": 50}
    )
    refined_lags = assistant.refine_plan(profile, plan, lags=[1, 2])

    assert refined_unrelated.llm_refined_fields == ["lags"]
    assert refined_unrelated.forecaster_kwargs["lags"] == plan.forecaster_kwargs["lags"]
    assert refined_lags.llm_refined_fields == []


def test_refine_plan_output_drops_llm_mark_when_value_is_not_carried_over():
    """
    Test that an LLM mark is dropped when the refinement switches to a
    forecaster family that has no lags, and stays dropped when a later
    refinement switches back and re-derives the lags deterministically.
    Otherwise PACF-derived lags would be displayed as LLM-suggested.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10).model_copy(
        update={"llm_refined_fields": ["lags"]}
    )

    statistical = assistant.refine_plan(profile, plan, forecaster="ForecasterStats")
    recursive = assistant.refine_plan(
        profile, statistical, forecaster="ForecasterRecursive"
    )

    assert statistical.llm_refined_fields == []
    assert recursive.llm_refined_fields == []


def test_refine_plan_output_when_switching_to_and_from_baseline():
    """
    Test that refine_plan() can switch a plan to the baseline, which drops
    the estimator and the features, and back to an ML forecaster, which
    re-derives them deterministically.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    baseline = assistant.refine_plan(
        profile, plan, forecaster="ForecasterEquivalentDate"
    )
    recursive = assistant.refine_plan(
        profile, baseline, forecaster="ForecasterRecursive"
    )

    assert baseline.task_type == "baseline"
    assert baseline.forecaster_kwargs == {"offset": 7, "n_offsets": 1}
    assert baseline.estimator is None
    assert recursive.task_type == "single_series"
    assert recursive.forecaster_kwargs["lags"] == plan.forecaster_kwargs["lags"]


def test_refine_plan_output_does_not_carry_estimator_across_families():
    """
    Test that switching an ML plan to ForecasterStats re-derives the
    statistical estimator instead of carrying the ML regressor over, and
    that switching back re-derives the ML estimator of the profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    statistical = assistant.refine_plan(profile, plan, forecaster="ForecasterStats")
    recursive = assistant.refine_plan(
        profile, statistical, forecaster="ForecasterRecursive"
    )

    assert plan.estimator == "Ridge"
    assert statistical.estimator == "Arima"
    assert statistical.forecaster_kwargs == {}
    assert recursive.estimator == "Ridge"
    assert recursive.forecaster_kwargs["lags"] == plan.forecaster_kwargs["lags"]


def test_refine_plan_output_keeps_estimator_within_ml_forecasters():
    """
    Test that switching between ML forecasters keeps the estimator, its
    kwargs and the lags of the plan.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile,
        steps=10,
        estimator="Ridge",
        estimator_kwargs={"alpha": 2.0},
        lags=[1, 2, 7],
    )

    direct = assistant.refine_plan(profile, plan, forecaster="ForecasterDirect")

    assert direct.estimator == "Ridge"
    assert direct.estimator_kwargs == {"alpha": 2.0}
    assert direct.forecaster_kwargs["lags"] == [1, 2, 7]


@pytest.mark.parametrize(
    "forecaster, estimator, estimator_kwargs, new_estimator, new_kwargs",
    [
        (
            "ForecasterRecursive",
            "Ridge",
            {"alpha": 2.0},
            "LGBMRegressor",
            {"n_estimators": 50},
        ),
        (
            "ForecasterFoundation",
            "autogluon/chronos-2-small",
            {"cross_learning": True},
            "google/timesfm-3.0-pytorch",
            {"context_length": 1024},
        ),
    ],
    ids=lambda dt: (
        f"forecaster, estimator, estimator_kwargs, new_estimator, new_kwargs: {dt}"
    ),
)
def test_refine_plan_output_drops_estimator_kwargs_when_estimator_changes(
    forecaster, estimator, estimator_kwargs, new_estimator, new_kwargs
):
    """
    Test that changing the estimator drops the kwargs written for the
    previous one (a Chronos-2 `cross_learning` would make TimesFM fail),
    while refining another field keeps them and new kwargs passed with the
    new estimator are applied.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile,
        steps            = 10,
        forecaster       = forecaster,
        estimator        = estimator,
        estimator_kwargs = estimator_kwargs,
    )

    same_estimator = assistant.refine_plan(profile, plan, steps=5)
    new = assistant.refine_plan(profile, plan, estimator=new_estimator)
    new_with_kwargs = assistant.refine_plan(
        profile, plan, estimator=new_estimator, estimator_kwargs=new_kwargs
    )

    assert same_estimator.estimator_kwargs == estimator_kwargs
    assert new.estimator == new_estimator
    assert new.estimator_kwargs == {}
    assert new_with_kwargs.estimator_kwargs == new_kwargs


def test_refine_plan_ValueError_when_statistical_with_explicit_lags():
    """
    Test that an explicit lags override is not silently dropped when the
    plan is switched to ForecasterStats: plan() rejects it.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "'ForecasterStats' models the past values itself: it takes no lag or "
        "window features, so ['lags'] cannot be applied. Omit them."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.refine_plan(profile, plan, forecaster="ForecasterStats", lags=7)


def test_refine_plan_ValueError_when_baseline_with_explicit_lags():
    """
    Test that an explicit lags override is not silently dropped when the
    plan is switched to the baseline: plan() rejects it.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    with pytest.raises(ValueError, match=re.escape("so ['lags'] cannot be applied")):
        assistant.refine_plan(
            profile, plan, forecaster="ForecasterEquivalentDate", lags=7
        )

