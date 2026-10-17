# Unit test estimator_n_observations recommendation/forecaster_selection

import pytest

from skforecast_ai.recommendation import (
    estimator_n_observations,
    select_estimator_and_candidates,
)

from .fixtures_recommendation import profile_single_daily, profile_wide_monthly


@pytest.mark.parametrize(
    "task_type, profile, expected",
    [
        ("multivariate", profile_wide_monthly, 96),
        ("multi_series", profile_wide_monthly, 288),
        ("single_series", profile_single_daily, 365),
    ],
    ids=lambda dt: f"{dt}",
)
def test_estimator_n_observations_output(task_type, profile, expected):
    """
    Test that the multivariate task is sized on the dates the series share
    (`span_index_length`) and the other tasks on the observations pooled
    across the series, which for a single series is its length.
    """
    assert estimator_n_observations(task_type, profile) == expected


def test_estimator_n_observations_gives_ridge_to_multivariate_when_pooled_count_is_large():
    """
    Test that three series of 96 dates, 288 observations pooled, give
    LGBMRegressor to the multi-series task and Ridge to the multivariate
    task, which trains on one row per date.
    """
    multi_series, _ = select_estimator_and_candidates(
        task_type      = "multi_series",
        n_observations = estimator_n_observations("multi_series", profile_wide_monthly),
    )
    multivariate, _ = select_estimator_and_candidates(
        task_type      = "multivariate",
        n_observations = estimator_n_observations("multivariate", profile_wide_monthly),
    )

    assert multi_series == "LGBMRegressor"
    assert multivariate == "Ridge"
