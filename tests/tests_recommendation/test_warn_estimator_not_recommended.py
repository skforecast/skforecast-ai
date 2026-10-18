# Unit test warn_estimator_not_recommended recommendation/estimator_choice

import re
import warnings

import pytest

from skforecast_ai.exceptions import EstimatorNotRecommendedWarning
from skforecast_ai.recommendation import warn_estimator_not_recommended

from .fixtures_recommendation import (
    plan_baseline,
    plan_recursive_lgbm_user,
    plan_recursive_ridge,
    plan_recursive_ridge_user,
    plan_stats,
    profile_monthly_120,
)


def test_warn_estimator_not_recommended_warns_when_estimator_is_not_the_recommended_one():
    """
    Test that a plan with an estimator chosen by the user that is not the
    recommended one warns EstimatorNotRecommendedWarning, once, with the text
    of the change.
    """
    warn_msg = re.escape(
        "The estimator of the plan, 'LGBMRegressor' (chosen by the user), is "
        "not the one the rules recommend for ForecasterRecursive on these "
        "data: 'Ridge'."
    )
    with pytest.warns(EstimatorNotRecommendedWarning, match=warn_msg) as record:
        warn_estimator_not_recommended(plan_recursive_lgbm_user, profile_monthly_120)

    assert len(record) == 1


@pytest.mark.parametrize(
    "plan",
    [plan_recursive_ridge, plan_recursive_ridge_user, plan_stats, plan_baseline],
    ids=["rules", "user passed the recommended one", "ForecasterStats", "baseline"],
)
def test_warn_estimator_not_recommended_does_not_warn_when_no_change(plan):
    """
    Test that no warning is emitted for the estimator of the rules, nor for
    the forecasters without an estimator to choose.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = warn_estimator_not_recommended(plan, profile_monthly_120)

    assert result is None
