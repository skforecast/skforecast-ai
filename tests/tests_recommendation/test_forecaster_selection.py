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


@pytest.mark.parametrize(
    "frequency, expected",
    [
        (
            "QS-OCT",
            [
                "ForecasterRecursive",
                "ForecasterDirect",
                "ForecasterFoundation",
                "ForecasterStats",
            ],
        ),
        (
            "W-WED",
            ["ForecasterRecursive", "ForecasterDirect", "ForecasterFoundation"],
        ),
        (
            "W-SUN",
            ["ForecasterRecursive", "ForecasterDirect", "ForecasterFoundation"],
        ),
    ],
    ids=lambda dt: f"frequency, expected: {dt}",
)
def test_select_forecaster_and_candidates_output_when_anchored_frequency(
    frequency, expected
):
    """
    Test that an anchored frequency is read with the seasonal period of its
    base alias: quarters (m=4) keep ForecasterStats among the candidates,
    and weeks ending on any day (m=52) leave it out, as 'W-SUN' does.
    """
    profile = profile_single.model_copy(update={"frequency": frequency})

    preferred, candidates = select_forecaster_and_candidates(profile)

    assert preferred == "ForecasterRecursive"
    assert candidates == expected


def test_select_forecaster_and_candidates_output_when_multi_series():
    """
    Test that a multi-series profile recommends
    ForecasterRecursiveMultiSeries first, with the multivariate and the
    foundation alternatives as candidates.
    """
    preferred, candidates = select_forecaster_and_candidates(profile_multi)

    assert preferred == "ForecasterRecursiveMultiSeries"
    assert candidates == [
        "ForecasterRecursiveMultiSeries",
        "ForecasterDirectMultiVariate",
        "ForecasterFoundation",
    ]
    assert candidates[0] == preferred


@pytest.mark.parametrize(
    "data_format, expected",
    [
        (
            "wide",
            [
                "ForecasterRecursiveMultiSeries",
                "ForecasterDirectMultiVariate",
                "ForecasterFoundation",
            ],
        ),
        ("long", ["ForecasterRecursiveMultiSeries", "ForecasterFoundation"]),
    ],
    ids = lambda v: f"{v}",
)
def test_select_forecaster_and_candidates_output_when_multi_series_format(
    data_format, expected
):
    """
    Test that ForecasterDirectMultiVariate is a candidate for several series
    in wide format and not in long format, which plan() rejects for it.
    """
    profile = profile_multi.model_copy(update={"data_format": data_format})

    preferred, candidates = select_forecaster_and_candidates(profile)

    assert preferred == "ForecasterRecursiveMultiSeries"
    assert candidates == expected


@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("h", False),
        ("15min", False),
        ("30min", False),
        ("W", False),
        ("D", True),
        ("MS", True),
        ("QS", True),
        (None, True),
        ("unknown", True),
        ("2MS", True),
        ("3h", True),
        ("3D", True),
        ("7h", True),
        ("14h", True),
        ("4W-SUN", True),
        ("3min", True),
        ("60min", True),
        ("2W-SUN", True),
        ("5D", True),
        ("2min", True),
        ("s", True),
        ("10s", True),
    ],
    ids = lambda v: f"frequency: {v}",
)
def test_select_forecaster_and_candidates_stats_gated_by_frequency(
    frequency, expected
):
    """
    Test that ForecasterStats is only offered as automatic candidate when
    the seasonal period of Auto-ARIMA keeps it practical (below 24). Only
    a frequency of the table leaves it out: one outside it gets a period
    of 12 at most ('14h'), and none when its cycle is longer ('4W-SUN':
    13, '3min': 20, '60min': 24, '2W-SUN': 26, '5D': 73, seconds) or not
    whole ('3D', '7h'), so it always keeps ForecasterStats.
    """
    profile = DataProfile(
        n_series       = 1,
        series_lengths = {"y": 1000},
        target         = "y",
        index_type     = "datetime",
        frequency      = frequency,
    )

    _, candidates = select_forecaster_and_candidates(profile)

    assert ("ForecasterStats" in candidates) is expected


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
        ("ForecasterEquivalentDate", "baseline"),
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
    Test that the foundation task type always returns the model ID of
    Chronos-2 small, ignoring the number of observations.
    """
    preferred, candidates = select_estimator_and_candidates("foundation", n_observations=10000)

    assert preferred == "autogluon/chronos-2-small"
    assert candidates == ["autogluon/chronos-2-small"]


def test_select_estimator_and_candidates_output_when_baseline():
    """
    Test that the baseline task type has no estimator and no candidates.
    """
    preferred, candidates = select_estimator_and_candidates("baseline", n_observations=10000)

    assert preferred is None
    assert candidates == []


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
