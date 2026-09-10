# Unit test _build_profile_explanation recommendation/explanation

import pytest

from skforecast_ai.recommendation.explanation import _build_profile_explanation
from skforecast_ai.schemas import DataProfile


def _make_profile(**overrides) -> DataProfile:
    """Build a minimal DataProfile, daily single series unless overridden."""
    fields = dict(
        n_series       = 1,
        series_lengths = {"y": {"start": "2023-01-01", "end": "2023-04-10", "length": 100}},
        target         = "y",
        index_type     = "datetime",
        frequency      = "D",
    )
    fields.update(overrides)
    return DataProfile(**fields)


@pytest.mark.parametrize(
    "task_type, forecaster, expected",
    [
        ("multivariate", "ForecasterDirectMultiVariate", "A multivariate forecaster (ForecasterDirectMultiVariate) is recommended"),
        ("foundation", "ForecasterFoundation", "A foundation model (ForecasterFoundation) was selected per user preference."),
        ("statistical", "ForecasterStats", "A statistical model (ForecasterStats) was selected per user preference."),
    ],
    ids=lambda dt: f"{dt}",
)
def test_build_profile_explanation_opens_with_the_task_family(task_type, forecaster, expected):
    """
    Test that the explanation opens with a sentence naming the forecaster
    family for the multivariate, foundation and statistical tasks.
    """
    explanation = _build_profile_explanation(
        task_type             = task_type,
        forecaster            = forecaster,
        forecaster_candidates = [forecaster],
        estimator             = None,
        estimator_candidates  = [],
        data_profile          = _make_profile(),
    )

    assert explanation.startswith(expected)


def test_build_profile_explanation_output_when_index_is_not_datetime():
    """
    Test that a dataset without frequency and without a datetime index is
    described by its index type instead of a frequency.
    """
    explanation = _build_profile_explanation(
        task_type             = "single_series",
        forecaster            = "ForecasterRecursive",
        forecaster_candidates = ["ForecasterRecursive"],
        estimator             = "Ridge",
        estimator_candidates  = ["Ridge"],
        data_profile          = _make_profile(
            series_lengths={"y": {"length": 100}}, index_type="range", frequency=None
        ),
    )

    assert "Data: 100 observations, a range index." in explanation


def test_build_profile_explanation_output_when_gradient_boosting_estimator():
    """
    Test that a non-linear estimator is justified by the dataset size
    rather than by the small-dataset rule used for Ridge.
    """
    explanation = _build_profile_explanation(
        task_type             = "single_series",
        forecaster            = "ForecasterRecursive",
        forecaster_candidates = ["ForecasterRecursive", "ForecasterDirect"],
        estimator             = "LGBMRegressor",
        estimator_candidates  = ["LGBMRegressor", "XGBRegressor"],
        data_profile          = _make_profile(
            series_lengths={"y": {"start": "2020-01-01", "end": "2021-02-13", "length": 410}}
        ),
    )

    assert "A gradient boosting model is preferred for a dataset of this size (410 observations)." in explanation
    assert "Alternative estimators: ['XGBRegressor']." in explanation


def test_build_profile_explanation_counts_categorical_exog():
    """
    Test that the exogenous variables note reports how many of them are
    categorical.
    """
    explanation = _build_profile_explanation(
        task_type             = "single_series",
        forecaster            = "ForecasterRecursive",
        forecaster_candidates = ["ForecasterRecursive"],
        estimator             = "Ridge",
        estimator_candidates  = ["Ridge"],
        data_profile          = _make_profile(
            exog_columns=["temp", "holiday", "weather"], categorical_exog=["holiday", "weather"]
        ),
    )

    assert "3 exogenous variables (2 categorical) available as predictors." in explanation
