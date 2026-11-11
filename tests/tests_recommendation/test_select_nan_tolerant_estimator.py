# Unit test select_nan_tolerant_estimator recommendation/missing_values

import pytest

from skforecast_ai.recommendation import select_nan_tolerant_estimator


@pytest.mark.parametrize(
    "task_type, n_observations, expected",
    [
        ("single_series", 120, "RandomForestRegressor"),
        ("single_series", 249, "RandomForestRegressor"),
        ("single_series", 250, "LGBMRegressor"),
        ("multi_series", 360, "LGBMRegressor"),
        ("multivariate", 120, "RandomForestRegressor"),
    ],
    ids=lambda dt: f"{dt}",
)
def test_select_nan_tolerant_estimator_output(task_type, n_observations, expected):
    """
    Test that the estimator is the first candidate of the rules that accepts
    missing values: RandomForestRegressor below 250 observations, where the
    rules rank Ridge, RandomForestRegressor and LGBMRegressor, and
    LGBMRegressor from 250 on, where it is the preferred one.
    """
    assert select_nan_tolerant_estimator(task_type, n_observations) == expected


@pytest.mark.parametrize(
    "task_type",
    ["statistical", "foundation", "baseline"],
    ids=lambda dt: f"task_type: {dt}",
)
def test_select_nan_tolerant_estimator_None_when_no_candidate_accepts_missing_values(
    task_type,
):
    """
    Test that the tasks without a candidate that accepts missing values (an
    Arima, a foundation model, the baseline without estimator) give None.
    """
    assert select_nan_tolerant_estimator(task_type, 1000) is None
