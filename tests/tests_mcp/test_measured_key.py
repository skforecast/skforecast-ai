# Unit test _measured_key

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp.server import _measured_key

from ..fixtures_assistant import df_no_exog

assistant = ForecastingAssistant()
profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
plan = assistant.plan(profile, steps=5)


def test_measured_key_equal_when_plans_differ_in_interval_metric_or_provenance():
    """
    Test that the key is the same for a plan built with an interval, refined
    with one, built with other metrics (`metric` and `metrics_to_compute`),
    or with the same decisions passed by the user (other `overridden_fields`
    and `explanation`): none changes the point predictions.
    """
    with_interval = assistant.plan(profile, steps=5, interval=[0.1, 0.9])
    refined = assistant.refine_plan(profile, plan, interval=[0.05, 0.95])
    chosen = assistant.plan(profile, steps=5, estimator=plan.estimator)
    other_metric = assistant.plan(profile, steps=5, metric="mean_squared_error")
    metric_list = assistant.plan(
        profile, steps=5, metric=["mean_squared_error", "mean_absolute_error"]
    )

    assert chosen.overridden_fields == ["estimator"]
    assert plan.overridden_fields == []
    expected = _measured_key("profile-1", plan)
    assert _measured_key("profile-1", with_interval) == expected
    assert _measured_key("profile-1", refined) == expected
    assert _measured_key("profile-1", chosen) == expected
    assert other_metric.metric != plan.metric
    assert metric_list.metrics_to_compute != plan.metrics_to_compute
    assert _measured_key("profile-1", other_metric) == expected
    assert _measured_key("profile-1", metric_list) == expected


def test_measured_key_differs_when_a_decision_or_the_profile_differs():
    """
    Test that the key changes with a decision that changes the predictions
    (the estimator, the horizon) and with the profile.
    """
    key = _measured_key("profile-1", plan)

    assert _measured_key(
        "profile-1",
        assistant.plan(profile, steps=5, estimator="RandomForestRegressor"),
    ) != key
    assert _measured_key("profile-1", assistant.plan(profile, steps=6)) != key
    assert _measured_key("profile-2", plan) != key
