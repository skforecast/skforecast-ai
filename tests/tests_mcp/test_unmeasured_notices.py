# Unit test _unmeasured_notices

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.mcp.server import _measured_key, _unmeasured_notices

from ..fixtures_assistant import df_no_exog

assistant = ForecastingAssistant()
profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
plan = assistant.plan(profile, steps=5)
plan_interval = assistant.plan(profile, steps=5, interval=[0.1, 0.9])
plan_estimator = assistant.plan(profile, steps=5, estimator="RandomForestRegressor")
plan_metric = assistant.plan(profile, steps=5, metric="mean_squared_error")


def test_unmeasured_notices_when_no_plan_was_measured():
    """
    Test that a forecast of the future gets one notice when the session
    measured no plan, saying that it has no measure of accuracy and how to
    get one.
    """
    notices = _unmeasured_notices(set(), "profile-1", plan, None)

    assert notices == [
        ToolNotice(
            source   = "runtime",
            category = "UnmeasuredPlanNotice",
            message  = (
                "No `backtest`, `compare` or `forecast` with `test_size` in "
                "this session measured this plan (the same decisions, with "
                "any interval or metric), so this forecast has no measure of "
                "accuracy. Say so, and "
                "before presenting it as reliable measure it: `create_cv` "
                "with this `plan_id`, then `backtest` or `compare`. Never "
                "give the accuracy of another plan as that of this forecast."
            ),
            count    = 1,
        )
    ]


@pytest.mark.parametrize(
    "measured_plan, forecast_plan",
    [(plan, plan), (plan, plan_interval), (plan_interval, plan), (plan, plan_metric)],
    ids=[
        "same plan", "measured without interval", "measured with interval",
        "measured with another metric",
    ],
)
def test_unmeasured_notices_empty_when_the_plan_was_measured(
    measured_plan, forecast_plan
):
    """
    Test that the plan measured, with or without an interval or with another
    metric, gets no notice.
    """
    measured = {_measured_key("profile-1", measured_plan)}

    assert _unmeasured_notices(measured, "profile-1", forecast_plan, None) == []


def test_unmeasured_notices_when_another_plan_was_measured():
    """
    Test that a measure of a plan with other decisions, or of the same plan
    on another profile, does not count.
    """
    measured = {
        _measured_key("profile-1", plan_estimator),
        _measured_key("profile-2", plan),
    }

    notices = _unmeasured_notices(measured, "profile-1", plan, None)

    assert [notice.category for notice in notices] == ["UnmeasuredPlanNotice"]


@pytest.mark.parametrize(
    "test_size", [5, 0.05, "2023-04-06"], ids=lambda dt: f"test_size: {dt!r}"
)
def test_unmeasured_notices_empty_for_an_evaluation(test_size):
    """
    Test that a forecast with `test_size`, a measure itself, gets no notice.
    """
    assert _unmeasured_notices(set(), "profile-1", plan, test_size) == []
