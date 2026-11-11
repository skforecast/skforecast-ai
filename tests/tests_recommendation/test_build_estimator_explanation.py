# Unit test build_estimator_explanation recommendation/explanation

import pytest

from skforecast_ai.recommendation.explanation import build_estimator_explanation

from .fixtures_recommendation import profile_wide_monthly


def test_build_estimator_explanation_output_when_multivariate_estimator_differs_from_profile():
    """
    Test that a ForecasterDirectMultiVariate plan on a profile that
    recommends ForecasterRecursiveMultiSeries names its estimator, the one
    of the profile, and the count that chose it: the dates the series
    share, not the observations pooled across them.
    """
    explanation = build_estimator_explanation(
        forecaster         = "ForecasterDirectMultiVariate",
        estimator          = "Ridge",
        task_type          = "multivariate",
        data_profile       = profile_wide_monthly,
        profile_forecaster = "ForecasterRecursiveMultiSeries",
        profile_estimator  = "LGBMRegressor",
    )

    assert explanation == (
        "Estimator: Ridge, chosen by the rules for ForecasterDirectMultiVariate "
        "(the profile recommends LGBMRegressor for ForecasterRecursiveMultiSeries). "
        "A linear model is preferred because the dataset is small "
        "(96 observations < 250); gradient boosting is offered as an "
        "alternative once more data is available. ForecasterDirectMultiVariate "
        "trains on one row per date, so the size is the 96 dates the series "
        "share, not the 288 observations pooled across them."
    )


def test_build_estimator_explanation_output_when_estimator_equals_profile():
    """
    Test that the estimator is not contrasted with the one of the profile
    when both are the same, and that the multi-series task gives the
    pooled count.
    """
    explanation = build_estimator_explanation(
        forecaster         = "ForecasterRecursiveMultiSeries",
        estimator          = "LGBMRegressor",
        task_type          = "multi_series",
        data_profile       = profile_wide_monthly,
        profile_forecaster = "ForecasterDirectMultiVariate",
        profile_estimator  = "LGBMRegressor",
    )

    assert explanation == (
        "Estimator: LGBMRegressor, chosen by the rules for "
        "ForecasterRecursiveMultiSeries. A gradient boosting model is "
        "preferred for a dataset of this size (288 observations)."
    )


@pytest.mark.parametrize(
    "task_type, forecaster, estimator",
    [
        ("statistical", "ForecasterStats", "Arima"),
        ("foundation", "ForecasterFoundation", "autogluon/chronos-2-small"),
        ("baseline", "ForecasterEquivalentDate", None),
    ],
    ids=lambda dt: f"{dt}",
)
def test_build_estimator_explanation_output_None_when_estimator_does_not_depend_on_size(
    task_type, forecaster, estimator
):
    """
    Test that the statistical, foundation and baseline tasks get no
    sentence: their estimator does not depend on the dataset size.
    """
    explanation = build_estimator_explanation(
        forecaster         = forecaster,
        estimator          = estimator,
        task_type          = task_type,
        data_profile       = profile_wide_monthly,
        profile_forecaster = "ForecasterRecursiveMultiSeries",
        profile_estimator  = "LGBMRegressor",
    )

    assert explanation is None
