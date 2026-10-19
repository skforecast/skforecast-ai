# Unit test recommended_estimator recommendation/estimator_choice

import pytest

from skforecast_ai.recommendation import recommended_estimator

from .fixtures_recommendation import (
    plan_baseline,
    plan_foundation,
    plan_multiseries_ridge_user,
    plan_multivariate_ridge_user,
    plan_recursive_ridge,
    plan_stats,
    profile_monthly_120,
    profile_monthly_249,
    profile_monthly_250,
    profile_monthly_3x120,
)


@pytest.mark.parametrize(
    "profile, expected",
    [
        (profile_monthly_120, "Ridge"),
        (profile_monthly_249, "Ridge"),
        (profile_monthly_250, "LGBMRegressor"),
    ],
    ids=lambda dt: f"{dt}",
)
def test_recommended_estimator_output_when_ForecasterRecursive(profile, expected):
    """
    Test that ForecasterRecursive gets Ridge below 250 observations and
    LGBMRegressor from 250 on, whatever the estimator of the plan.
    """
    assert recommended_estimator(plan_recursive_ridge, profile) == expected


def test_recommended_estimator_output_when_multivariate_sized_with_shared_dates():
    """
    Test that three series of 120 dates (360 observations pooled) give
    LGBMRegressor to ForecasterRecursiveMultiSeries, which trains on the
    pooled observations, and Ridge to ForecasterDirectMultiVariate, which
    trains on the 120 dates the series share.
    """
    multi_series = recommended_estimator(
        plan_multiseries_ridge_user, profile_monthly_3x120
    )
    multivariate = recommended_estimator(
        plan_multivariate_ridge_user, profile_monthly_3x120
    )

    assert multi_series == "LGBMRegressor"
    assert multivariate == "Ridge"


@pytest.mark.parametrize(
    "plan",
    [plan_stats, plan_foundation, plan_baseline],
    ids=lambda plan: f"{plan.forecaster}",
)
def test_recommended_estimator_None_when_forecaster_has_no_estimator_to_choose(plan):
    """
    Test that ForecasterStats, ForecasterFoundation and the baseline
    (ForecasterEquivalentDate) have no recommended estimator.
    """
    assert recommended_estimator(plan, profile_monthly_120) is None
