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
        "Invalid override keys: ['lags']. "
        "Allowed keys: ['estimator', 'estimator_kwargs', 'forecaster',"
        " 'interval', 'steps']."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.refine_plan(profile, plan, lags=[1, 2, 3])


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
