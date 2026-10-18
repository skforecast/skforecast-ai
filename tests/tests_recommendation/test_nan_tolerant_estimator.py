# Unit test nan_tolerant_estimator recommendation/missing_values

import pytest

from skforecast_ai.recommendation.missing_values import nan_tolerant_estimator

from ..fixtures_last_window import (
    plan_h2o_baseline,
    plan_h2o_direct,
    plan_h2o_lgbm,
    plan_h2o_ridge,
    plan_wide_multivariate,
    plan_wide_ridge,
    plans_h2o_without_lags,
    profile_h2o,
    profile_wide,
)


@pytest.mark.parametrize(
    "plan, profile, expected",
    [
        (plan_h2o_ridge, profile_h2o, "RandomForestRegressor"),
        (plan_h2o_direct, profile_h2o, "RandomForestRegressor"),
        (plan_wide_ridge, profile_wide, "LGBMRegressor"),
        (plan_wide_multivariate, profile_wide, "RandomForestRegressor"),
    ],
    ids=["recursive", "direct", "multi_series", "multivariate"],
)
def test_nan_tolerant_estimator_output_when_estimator_cannot_use_missing_values(
    plan, profile, expected
):
    """
    Test that a lag forecaster with Ridge gets the estimator of the rules
    for the task of its plan and the size of the data: 120 observations of
    h2o give RandomForestRegressor, the 360 pooled of the three items_sales
    series LGBMRegressor, and ForecasterDirectMultiVariate, sized on the 120
    dates the series share, RandomForestRegressor.
    """
    assert nan_tolerant_estimator(plan, profile) == expected


@pytest.mark.parametrize(
    "plan",
    [
        plan_h2o_lgbm,
        plan_h2o_baseline,
        plans_h2o_without_lags["stats"],
        plans_h2o_without_lags["foundation"],
    ],
    ids=["lgbm", "baseline", "stats", "foundation"],
)
def test_nan_tolerant_estimator_None_when_there_is_no_estimator_to_replace(plan):
    """
    Test that a plan whose estimator already accepts missing values, and the
    forecasters without lags, give None.
    """
    assert nan_tolerant_estimator(plan, profile_h2o) is None
