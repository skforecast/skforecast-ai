# Unit test plan ForecastingAssistant

import re

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.schemas import ForecastPlan

from tests.fixtures_assistant import df_single, df_multi_long, df_no_exog


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_plan_ValueError_when_forecaster_not_in_candidates():
    """
    Test that plan() raises ValueError when the specified
    forecaster is not in the profile's candidate list.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        "Forecaster 'ForecasterRnn' is not compatible with this profile."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(profile, steps=10, forecaster="ForecasterRnn")


# =============================================================================
# Tests: basic output
# =============================================================================
def test_plan_output_when_single_series():
    """
    Test that plan() returns a ForecastPlan with correct task_type
    and steps for a single-series profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    assert isinstance(plan, ForecastPlan)
    assert plan.steps == 10
    assert plan.task_type == "single_series"
    assert plan.forecaster == profile.forecaster


def test_plan_output_when_forecaster_override():
    """
    Test that plan() honors an explicit forecaster override.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterDirect"
    )

    assert plan.forecaster == "ForecasterDirect"
    assert plan.task_type == "single_series"


def test_plan_output_when_multi_series():
    """
    Test that plan() produces a multi_series plan from a
    multi-series profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.plan(profile, steps=5)

    assert plan.task_type == "multi_series"
    assert plan.forecaster == "ForecasterRecursiveMultiSeries"


# =============================================================================
# Tests: feature-rich (intervals, kwargs, statistical/foundation)
# =============================================================================
def test_plan_output_when_interval_bootstrapping():
    """
    Test that plan() sets interval_method='bootstrapping' for ML
    forecasters when interval is provided.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, interval=[0.1, 0.9])

    assert plan.interval == [0.1, 0.9]
    assert plan.interval_method == "bootstrapping"


def test_plan_output_when_interval_native_for_statistical():
    """
    Test that plan() sets interval_method='native' for
    ForecasterStats when interval is provided.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats", interval=[0.1, 0.9]
    )

    assert plan.interval == [0.1, 0.9]
    assert plan.interval_method == "native"
    assert plan.task_type == "statistical"


def test_plan_output_when_statistical_has_no_lags():
    """
    Test that plan() sets lags, window_features, and transformers
    to None for statistical task types.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats"
    )

    assert plan.task_type == "statistical"
    assert "lags" not in plan.forecaster_kwargs or plan.forecaster_kwargs.get("lags") is None


def test_plan_output_when_foundation_forecaster():
    """
    Test that plan() assigns the foundation estimator and empty
    forecaster_kwargs for a foundation forecaster override.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterFoundation"
    )

    assert plan.task_type == "foundation"
    assert plan.estimator == "Chronos-2"
    assert plan.forecaster_kwargs == {}


def test_plan_deterministic():
    """
    Test that plan() is deterministic: two identical calls produce
    equal plans.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan_1 = assistant.plan(profile, steps=10)
    plan_2 = assistant.plan(profile, steps=10)

    assert plan_1 == plan_2



def test_plan_output_when_estimator_kwargs_provided():
    """
    Test that plan() passes estimator_kwargs through to the plan.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    custom_kwargs = {"n_estimators": 200, "learning_rate": 0.05}
    plan = assistant.plan(
        profile, steps=10, estimator_kwargs=custom_kwargs
    )

    assert plan.estimator_kwargs == custom_kwargs


def test_plan_output_when_estimator_override():
    """
    Test that plan() uses the explicitly specified estimator.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, estimator="RandomForestRegressor"
    )

    assert plan.estimator == "RandomForestRegressor"


def test_plan_output_when_no_exog():
    """
    Test that plan() sets use_exog=False when no exogenous
    variables are present.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    assert plan.use_exog is False


def test_plan_output_when_exog_present():
    """
    Test that plan() sets use_exog=True when exogenous variables
    are present in the data.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    assert plan.use_exog is True
