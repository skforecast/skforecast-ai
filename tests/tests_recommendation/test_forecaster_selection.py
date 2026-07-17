# Unit test forecaster_selection recommendation/forecaster_selection
"""Tests for forecaster, task-type, and estimator selection rules."""

import re

import pytest

from skforecast_ai.recommendation import (
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_task_type_from_forecaster,
)
from skforecast_ai.schemas import DataProfile


# --- Fixtures ---

profile_single = DataProfile(
    n_series       = 1,
    series_lengths = {"y": 365},
    target         = "y",
    index_type     = "datetime",
    frequency      = "D",
)

profile_multi = DataProfile(
    n_series       = 3,
    series_lengths = {"value": 300},
    target         = "value",
    series_id_column = "series_id",
    index_type     = "datetime",
    frequency      = "D",
)

profile_single_categorical = DataProfile(
    n_series       = 1,
    series_lengths = {"y": 365},
    target         = "y",
    target_dtype   = "categorical",
    index_type     = "datetime",
    frequency      = "D",
)


# =============================================================================
# Tests: select_forecaster_and_candidates
# =============================================================================
def test_select_forecaster_and_candidates_output_when_single_series():
    """
    Test that a single-series profile recommends ForecasterRecursive
    first, with the full ordered candidate list.
    """
    preferred, candidates = select_forecaster_and_candidates(profile_single)

    assert preferred == "ForecasterRecursive"
    assert candidates == [
        "ForecasterRecursive",
        "ForecasterDirect",
        "ForecasterFoundation",
        "ForecasterStats",
    ]
    assert candidates[0] == preferred


def test_select_forecaster_and_candidates_output_when_single_categorical():
    """
    Test that a single categorical target routes to the classifier
    forecaster, never to a regression forecaster.
    """
    preferred, candidates = select_forecaster_and_candidates(profile_single_categorical)

    assert preferred == "ForecasterRecursiveClassifier"
    assert "ForecasterRecursive" not in candidates
    assert candidates[0] == preferred


def test_select_forecaster_and_candidates_output_when_multi_series():
    """
    Test that a multi-series profile recommends
    ForecasterRecursiveMultiSeries first, with the multivariate
    alternative as candidate.
    """
    preferred, candidates = select_forecaster_and_candidates(profile_multi)

    assert preferred == "ForecasterRecursiveMultiSeries"
    assert candidates == [
        "ForecasterRecursiveMultiSeries",
        "ForecasterDirectMultiVariate",
    ]
    assert candidates[0] == preferred


# =============================================================================
# Tests: select_task_type_from_forecaster
# =============================================================================
@pytest.mark.parametrize(
    "forecaster, expected_task_type",
    [
        ("ForecasterRecursive", "single_series"),
        ("ForecasterDirect", "single_series"),
        ("ForecasterRecursiveMultiSeries", "multi_series"),
        ("ForecasterDirectMultiVariate", "multivariate"),
        ("ForecasterStats", "statistical"),
        ("ForecasterFoundation", "foundation"),
        ("ForecasterRecursiveClassifier", "classification"),
    ],
)
def test_select_task_type_from_forecaster_output(forecaster, expected_task_type):
    """
    Test that each known forecaster maps to its expected task type.
    """
    assert select_task_type_from_forecaster(forecaster) == expected_task_type


def test_select_task_type_from_forecaster_ValueError_when_unknown_forecaster():
    """
    Test that an unknown forecaster name raises ValueError.
    """
    err_msg = re.escape("Unknown forecaster 'ForecasterMystery'.")
    with pytest.raises(ValueError, match=err_msg):
        select_task_type_from_forecaster("ForecasterMystery")


# =============================================================================
# Tests: select_estimator_and_candidates
# =============================================================================
def test_select_estimator_and_candidates_output_when_statistical():
    """
    Test that the statistical task type always returns Arima, ignoring
    the number of observations.
    """
    preferred, candidates = select_estimator_and_candidates("statistical", n_observations=10000)

    assert preferred == "Arima"
    assert candidates == ["Arima"]


def test_select_estimator_and_candidates_output_when_foundation():
    """
    Test that the foundation task type always returns Chronos-2,
    ignoring the number of observations.
    """
    preferred, candidates = select_estimator_and_candidates("foundation", n_observations=10000)

    assert preferred == "Chronos-2"
    assert candidates == ["Chronos-2"]


def test_select_estimator_and_candidates_output_when_short_series():
    """
    Test that a short series (< 250 observations) prefers Ridge, a
    low-variance linear model, with tree-based alternatives as
    candidates.
    """
    preferred, candidates = select_estimator_and_candidates("single_series", n_observations=249)

    assert preferred == "Ridge"
    assert candidates == ["Ridge", "RandomForestRegressor", "LGBMRegressor"]


def test_select_estimator_and_candidates_output_when_long_series():
    """
    Test that a longer series (>= 250 observations) prefers
    LGBMRegressor, with gradient-boosting and linear alternatives.
    """
    preferred, candidates = select_estimator_and_candidates("single_series", n_observations=250)

    assert preferred == "LGBMRegressor"
    assert candidates == ["LGBMRegressor", "XGBRegressor", "Ridge"]


def test_select_estimator_and_candidates_output_when_classification():
    """
    Test that the classification task type returns a classifier estimator,
    never a regressor.
    """
    preferred, candidates = select_estimator_and_candidates("classification", n_observations=10000)

    assert preferred == "RandomForestClassifier"
    assert "RandomForestClassifier" in candidates
    assert "LGBMRegressor" not in candidates
    assert candidates[0] == preferred
