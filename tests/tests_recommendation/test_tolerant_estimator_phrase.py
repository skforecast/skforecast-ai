# Unit test tolerant_estimator_phrase recommendation/missing_values

import pytest

from skforecast_ai.recommendation.missing_values import tolerant_estimator_phrase


@pytest.mark.parametrize(
    "estimator, expected",
    [
        (
            "RandomForestRegressor",
            "an estimator that accepts missing values (such as "
            "'RandomForestRegressor')",
        ),
        (None, "an estimator that accepts missing values"),
    ],
    ids=["estimator", "none"],
)
def test_tolerant_estimator_phrase_output(estimator, expected):
    """
    Test that the phrase names the estimator of the rules when there is one,
    the text every warning, error and notice of the missing values shares.
    """
    assert tolerant_estimator_phrase(estimator) == expected
