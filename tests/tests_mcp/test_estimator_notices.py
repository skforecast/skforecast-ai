# Unit test _estimator_notices

from types import SimpleNamespace

import pytest

from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.mcp.server import _estimator_notices

from ..fixtures_last_window import (
    plan_h2o_baseline,
    plan_h2o_forest,
    plan_h2o_lgbm,
    plan_h2o_ridge,
    plans_h2o_without_lags,
    profile_h2o,
    profile_h2o_gaps,
)

# The plan of a candidate of `compare()` does not record the estimator.
plan_h2o_lgbm_not_recorded = plan_h2o_lgbm.model_copy(
    update={"overridden_fields": []}
)

ASK = (
    " Say in your answer that the estimator is not the recommended one, which "
    "one the rules recommend and why it was changed."
)


@pytest.mark.parametrize("run", ["backtest", "forecast"])
@pytest.mark.parametrize(
    "plan, data_profile, estimator, origin",
    [
        (
            plan_h2o_lgbm,
            profile_h2o,
            "LGBMRegressor",
            "It was passed to `plan` or `refine_plan`.",
        ),
        (
            plan_h2o_forest,
            profile_h2o_gaps,
            "RandomForestRegressor",
            "It was passed to `plan` or `refine_plan`, and it is the estimator "
            "that accepts missing values that the advice on the missing values "
            "of the data names.",
        ),
        (
            plan_h2o_lgbm_not_recorded,
            profile_h2o,
            "LGBMRegressor",
            "It was not passed to `plan` or `refine_plan`: it is the plan of a "
            "candidate of `compare`.",
        ),
    ],
    ids=["chosen_by_user", "chosen_by_user_missing_values", "not_passed"],
)
def test_estimator_notices_output_when_estimator_is_not_the_recommended_one(
    plan, data_profile, estimator, origin, run
):
    """
    Test that a plan whose estimator is not the one the rules recommend (Ridge
    for the 120 observations of h2o) gets one notice (source 'plan') that
    names the run, both estimators and who chose it: the user, the user with
    the estimator that accepts missing values that the advice names, or not
    passed (a candidate of `compare`). It asks to say it in the answer.
    """
    notices = _estimator_notices(
        plan, SimpleNamespace(data_profile=data_profile), run
    )

    assert notices == [
        ToolNotice(
            source   = "plan",
            category = "EstimatorNotRecommendedNotice",
            message  = (
                f"This {run} ran the estimator '{estimator}', not the one the "
                f"rules recommend for ForecasterRecursive on these data "
                f"('Ridge'). {origin}" + ASK
            ),
            count    = 1,
        )
    ]


def test_estimator_notices_message_when_chosen_by_user():
    """
    Test the whole text of the notice of a backtest of LGBMRegressor chosen by
    the user on 120 observations.
    """
    notices = _estimator_notices(
        plan_h2o_lgbm, SimpleNamespace(data_profile=profile_h2o), "backtest"
    )

    assert [notice.message for notice in notices] == [
        "This backtest ran the estimator 'LGBMRegressor', not the one the rules "
        "recommend for ForecasterRecursive on these data ('Ridge'). It was "
        "passed to `plan` or `refine_plan`. Say in your answer that the "
        "estimator is not the recommended one, which one the rules recommend "
        "and why it was changed."
    ]


@pytest.mark.parametrize(
    "plan",
    [
        plan_h2o_ridge,
        plan_h2o_baseline,
        plans_h2o_without_lags["stats"],
        plans_h2o_without_lags["foundation"],
    ],
    ids=["recommended_estimator", "baseline", "stats", "foundation"],
)
def test_estimator_notices_empty_when_no_change(plan):
    """
    Test that there is no notice for the estimator of the rules, nor for the
    forecasters without an estimator to choose (the baseline,
    ForecasterStats and ForecasterFoundation).
    """
    notices = _estimator_notices(
        plan, SimpleNamespace(data_profile=profile_h2o), "forecast"
    )

    assert notices == []
