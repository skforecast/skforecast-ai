# Unit test estimator_change_message recommendation/estimator_choice

import pytest

from skforecast_ai.recommendation.estimator_choice import (
    EstimatorChange,
    estimator_change_message,
)


@pytest.mark.parametrize(
    "change, expected",
    [
        (
            EstimatorChange(
                estimator      = "LGBMRegressor",
                recommended    = "Ridge",
                forecaster     = "ForecasterRecursive",
                chosen_by_user = True,
                missing_values = False,
            ),
            "The estimator of the plan, 'LGBMRegressor' (chosen by the user), is "
            "not the one the rules recommend for ForecasterRecursive on these "
            "data: 'Ridge'.",
        ),
        (
            EstimatorChange(
                estimator      = "RandomForestRegressor",
                recommended    = "Ridge",
                forecaster     = "ForecasterRecursive",
                chosen_by_user = True,
                missing_values = True,
            ),
            "The estimator of the plan, 'RandomForestRegressor' (chosen by the "
            "user), is not the one the rules recommend for ForecasterRecursive "
            "on these data: 'Ridge'. 'RandomForestRegressor' is the estimator "
            "that accepts missing values that the advice on the missing values "
            "of the data names.",
        ),
        (
            EstimatorChange(
                estimator      = "Ridge",
                recommended    = "LGBMRegressor",
                forecaster     = "ForecasterRecursiveMultiSeries",
                chosen_by_user = False,
                missing_values = False,
            ),
            "The estimator of the plan, 'Ridge' (not recorded in "
            "`overridden_fields`: a candidate of `compare()`, or a plan edited "
            "by hand), is not the one the rules recommend for "
            "ForecasterRecursiveMultiSeries on these data: 'LGBMRegressor'.",
        ),
    ],
    ids=["chosen by the user", "with the missing values", "not recorded"],
)
def test_estimator_change_message_output(change, expected):
    """
    Test the text of the warning for an estimator chosen by the user, for the
    estimator that accepts missing values (with its extra sentence) and for a
    plan that does not record the estimator in `overridden_fields`.
    """
    assert estimator_change_message(change) == expected
