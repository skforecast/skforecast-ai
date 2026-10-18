# Unit test estimator_change recommendation/estimator_choice

import pytest

from skforecast_ai.recommendation import estimator_change
from skforecast_ai.recommendation.estimator_choice import EstimatorChange

from .fixtures_recommendation import (
    plan_baseline,
    plan_direct_lgbm_user,
    plan_foundation,
    plan_multiseries_lgbm,
    plan_multiseries_ridge_user,
    plan_multivariate_lgbm_user,
    plan_multivariate_ridge_user,
    plan_recursive_forest_exog_user,
    plan_recursive_forest_user,
    plan_recursive_lgbm,
    plan_recursive_lgbm_user,
    plan_recursive_ridge,
    plan_recursive_ridge_user,
    plan_stats,
    profile_monthly_120,
    profile_monthly_120_gaps,
    profile_monthly_120_missing_exog,
    profile_monthly_120_missing_target,
    profile_monthly_249_missing_target,
    profile_monthly_250,
    profile_monthly_250_missing_target,
    profile_monthly_3x120,
    profile_monthly_3x120_missing_target,
)


@pytest.mark.parametrize(
    "plan, profile",
    [
        (plan_recursive_ridge, profile_monthly_120),
        (plan_recursive_ridge_user, profile_monthly_120),
        (plan_recursive_lgbm, profile_monthly_250),
        (plan_recursive_lgbm_user, profile_monthly_250),
        (plan_multiseries_lgbm, profile_monthly_3x120),
        (plan_multivariate_ridge_user, profile_monthly_3x120),
    ],
    ids=[
        "rules, Ridge",
        "user passed the same Ridge",
        "rules, LGBMRegressor",
        "user passed the same LGBMRegressor",
        "multi-series, LGBMRegressor",
        "multivariate sized with the shared dates, Ridge",
    ],
)
def test_estimator_change_None_when_estimator_is_the_recommended_one(plan, profile):
    """
    Test that a plan with the estimator the rules recommend gives None, also
    when the user passed that same estimator: ForecasterDirectMultiVariate
    with Ridge on three series of 120 dates is not a change although the
    profile recommends LGBMRegressor for ForecasterRecursiveMultiSeries.
    """
    assert estimator_change(plan, profile) is None


@pytest.mark.parametrize(
    "plan", [plan_stats, plan_foundation, plan_baseline],
    ids=lambda plan: f"{plan.forecaster}",
)
def test_estimator_change_None_when_forecaster_has_no_estimator_to_choose(plan):
    """
    Test that ForecasterStats, ForecasterFoundation and the baseline give
    None, also with missing values in the data.
    """
    assert estimator_change(plan, profile_monthly_120_missing_target) is None


@pytest.mark.parametrize(
    "plan, profile, expected",
    [
        (
            plan_recursive_lgbm_user,
            profile_monthly_120,
            EstimatorChange(
                estimator      = "LGBMRegressor",
                recommended    = "Ridge",
                forecaster     = "ForecasterRecursive",
                chosen_by_user = True,
                missing_values = False,
            ),
        ),
        (
            plan_recursive_ridge_user,
            profile_monthly_250,
            EstimatorChange(
                estimator      = "Ridge",
                recommended    = "LGBMRegressor",
                forecaster     = "ForecasterRecursive",
                chosen_by_user = True,
                missing_values = False,
            ),
        ),
        (
            plan_direct_lgbm_user,
            profile_monthly_120,
            EstimatorChange(
                estimator      = "LGBMRegressor",
                recommended    = "Ridge",
                forecaster     = "ForecasterDirect",
                chosen_by_user = True,
                missing_values = False,
            ),
        ),
        (
            plan_multiseries_ridge_user,
            profile_monthly_3x120,
            EstimatorChange(
                estimator      = "Ridge",
                recommended    = "LGBMRegressor",
                forecaster     = "ForecasterRecursiveMultiSeries",
                chosen_by_user = True,
                missing_values = False,
            ),
        ),
        (
            plan_multivariate_lgbm_user,
            profile_monthly_3x120,
            EstimatorChange(
                estimator      = "LGBMRegressor",
                recommended    = "Ridge",
                forecaster     = "ForecasterDirectMultiVariate",
                chosen_by_user = True,
                missing_values = False,
            ),
        ),
    ],
    ids=[
        "ForecasterRecursive, LGBMRegressor on 120",
        "ForecasterRecursive, Ridge on 250",
        "ForecasterDirect, LGBMRegressor on 120",
        "ForecasterRecursiveMultiSeries, Ridge on 3x120",
        "ForecasterDirectMultiVariate, LGBMRegressor on 3x120",
    ],
)
def test_estimator_change_output_when_user_chose_another_estimator(
    plan, profile, expected
):
    """
    Test that the estimator chosen by the user that is not the recommended
    one gives the change, with the forecaster and the estimator the rules
    recommend for the size of the data, and no missing values.
    """
    assert estimator_change(plan, profile) == expected


def test_estimator_change_chosen_by_user_False_when_estimator_not_in_overridden_fields():
    """
    Test that a plan that does not record the estimator in `overridden_fields`
    (a candidate of `compare()`, a plan edited by hand) gives
    `chosen_by_user=False`.
    """
    expected = EstimatorChange(
        estimator      = "LGBMRegressor",
        recommended    = "Ridge",
        forecaster     = "ForecasterRecursive",
        chosen_by_user = False,
        missing_values = False,
    )

    assert estimator_change(plan_recursive_lgbm, profile_monthly_120) == expected


@pytest.mark.parametrize(
    "profile",
    [profile_monthly_120_missing_target, profile_monthly_120_gaps],
    ids=["missing values in the target", "missing timestamps"],
)
def test_estimator_change_missing_values_True_when_tolerant_estimator_and_target_gaps(
    profile,
):
    """
    Test that RandomForestRegressor, the estimator that accepts missing
    values for 120 observations, on a target with missing values or missing
    timestamps gives `missing_values=True`, because Ridge, the recommended
    estimator, does not accept them.
    """
    expected = EstimatorChange(
        estimator      = "RandomForestRegressor",
        recommended    = "Ridge",
        forecaster     = "ForecasterRecursive",
        chosen_by_user = True,
        missing_values = True,
    )

    assert estimator_change(plan_recursive_forest_user, profile) == expected


def test_estimator_change_missing_values_True_when_missing_exog_read_by_plan():
    """
    Test that missing values in an exogenous column count when the plan uses
    exogenous variables, and that they do not when the plan leaves them out.
    """
    with_exog = estimator_change(
        plan_recursive_forest_exog_user, profile_monthly_120_missing_exog
    )
    without_exog = estimator_change(
        plan_recursive_forest_user, profile_monthly_120_missing_exog
    )

    assert with_exog.missing_values is True
    assert without_exog.missing_values is False


def test_estimator_change_missing_values_False_when_data_complete():
    """
    Test that RandomForestRegressor on complete data gives
    `missing_values=False`: the sentence about the missing values does not
    apply.
    """
    expected = EstimatorChange(
        estimator      = "RandomForestRegressor",
        recommended    = "Ridge",
        forecaster     = "ForecasterRecursive",
        chosen_by_user = True,
        missing_values = False,
    )

    assert estimator_change(plan_recursive_forest_user, profile_monthly_120) == expected


@pytest.mark.parametrize(
    "plan, profile, estimator, recommended",
    [
        (
            plan_recursive_lgbm_user, profile_monthly_249_missing_target,
            "LGBMRegressor", "Ridge",
        ),
        (
            plan_recursive_forest_user, profile_monthly_250_missing_target,
            "RandomForestRegressor", "LGBMRegressor",
        ),
        (
            plan_multiseries_ridge_user, profile_monthly_3x120_missing_target,
            "Ridge", "LGBMRegressor",
        ),
    ],
    ids=[
        "LGBMRegressor below 250 is not the one the advice names",
        "RandomForestRegressor from 250, the advice names LGBMRegressor",
        "Ridge, which accepts no missing values",
    ],
)
def test_estimator_change_missing_values_False_when_estimator_is_not_the_one_of_the_advice(
    plan, profile, estimator, recommended
):
    """
    Test that missing values in the data give `missing_values=False` when
    the estimator of the plan is not the one the advice on the missing
    values names (RandomForestRegressor below 250 observations,
    LGBMRegressor from 250).
    """
    change = estimator_change(plan, profile)

    assert (change.estimator, change.recommended) == (estimator, recommended)
    assert change.missing_values is False
