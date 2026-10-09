# Unit test _exog_notices

import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.mcp.server import _exog_notices

from ..fixtures_assistant import df_no_exog, df_single

assistant = ForecastingAssistant()
profile_exog = assistant.profile(df_single, target="sales")
profile_no_exog = assistant.profile(df_no_exog, target="sales")


def test_exog_notices_plan_that_uses_exogenous_variables():
    """
    Test that a plan that uses the exogenous columns gets a notice saying
    that `forecast` needs their future values from the user, who is asked
    for them, and that the agent never writes them.
    """
    plan = assistant.plan(profile=profile_exog, steps=10)

    notices = _exog_notices(plan, profile_exog, forecast=False)

    assert notices == [
        ToolNotice(
            source   = "plan",
            category = "FutureExogNotice",
            message  = (
                "This plan uses the exogenous columns 'promo': `forecast` "
                "needs their future values, which only the user has, in a CSV "
                "file (`exog_path`). Never write that file yourself: ask the "
                "user for it, or use `use_exog: false` and tell them those "
                "columns were left out."
            ),
            count    = 1,
        )
    ]


def test_exog_notices_forecast_that_leaves_them_out():
    """
    Test that a forecast of a plan with `use_exog=False` on data with
    exogenous columns gets a notice asking to say so in the answer.
    """
    plan = assistant.plan(profile=profile_exog, steps=10, use_exog=False)

    notices = _exog_notices(plan, profile_exog, forecast=True)

    assert notices == [
        ToolNotice(
            source   = "plan",
            category = "ExogLeftOutNotice",
            message  = (
                "Say in your answer that this forecast does not use the "
                "exogenous columns of the data ('promo'): its plan has "
                "`use_exog: false`."
            ),
            count    = 1,
        )
    ]


def test_exog_notices_names_five_columns_at_most():
    """
    Test that the notice names the first 5 exogenous columns and counts
    them all.
    """
    data = df_single.assign(**{f"exog_{i}": df_single["promo"] for i in range(6)})
    profile = assistant.profile(data, target="sales")
    plan = assistant.plan(profile=profile, steps=10, use_exog=False)

    notices = _exog_notices(plan, profile, forecast=True)

    assert notices[0].message == (
        "Say in your answer that this forecast does not use the exogenous "
        "columns of the data ('promo', 'exog_0', 'exog_1', 'exog_2', 'exog_3' "
        "(first 5 of 7)): its plan has `use_exog: false`."
    )


@pytest.mark.parametrize(
    "use_exog, forecast",
    [(True, True), (False, False)],
    ids=lambda dt: f"{dt}",
)
def test_exog_notices_empty_when_nothing_to_say(use_exog, forecast):
    """
    Test that a forecast that uses the exogenous variables, a plan that
    leaves them out and data without exogenous columns get no notice.
    """
    plan = assistant.plan(profile=profile_exog, steps=10, use_exog=use_exog)
    plan_no_exog = assistant.plan(profile=profile_no_exog, steps=10)

    assert _exog_notices(plan, profile_exog, forecast=forecast) == []
    assert _exog_notices(plan_no_exog, profile_no_exog, forecast=True) == []
    assert _exog_notices(plan_no_exog, profile_no_exog, forecast=False) == []
