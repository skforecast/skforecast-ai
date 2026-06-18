"""Unit tests for calendar feature selection."""

import pytest

from skforecast_ai._constants import TREE_BASED_ESTIMATORS
from skforecast_ai.recommendation.calendar import (
    MIN_OBS_CALENDAR,
    MIN_YEARS_FOR_ANNUAL,
    OBS_PER_YEAR,
    select_calendar_encoding,
    select_calendar_features,
)


# ---------------------------------------------------------------------------
# select_calendar_features: cases returning None
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "task_type",
    ["statistical", "foundation"],
    ids=lambda t: f"task_type: {t}",
)
def test_select_calendar_features_None_when_task_not_machine_learning(task_type):
    """
    Test select_calendar_features returns None for statistical and
    foundation task types (calendar_features is not a supported parameter).
    """
    result = select_calendar_features(
        task_type=task_type, frequency="D", n_observations=1000
    )

    assert result is None


def test_select_calendar_features_None_when_frequency_is_None():
    """
    Test select_calendar_features returns None when the frequency is None
    (no datetime index / frequency could not be inferred).
    """
    result = select_calendar_features(
        task_type="single_series", frequency=None, n_observations=1000
    )

    assert result is None


@pytest.mark.parametrize(
    "n_observations",
    [0, 1, MIN_OBS_CALENDAR - 1],
    ids=lambda n: f"n_observations: {n}",
)
def test_select_calendar_features_None_when_series_too_short(n_observations):
    """
    Test select_calendar_features returns None when the series has fewer
    than MIN_OBS_CALENDAR observations.
    """
    result = select_calendar_features(
        task_type="single_series", frequency="D", n_observations=n_observations
    )

    assert result is None


@pytest.mark.parametrize(
    "frequency",
    ["YS", "YE", "Y", "A", "unknown"],
    ids=lambda f: f"frequency: {f}",
)
def test_select_calendar_features_None_when_frequency_has_no_subyear_seasonality(
    frequency,
):
    """
    Test select_calendar_features returns None for yearly and unknown
    frequencies, which have no recommended calendar features.
    """
    result = select_calendar_features(
        task_type="single_series", frequency=frequency, n_observations=1000
    )

    assert result is None


# ---------------------------------------------------------------------------
# select_calendar_features: base recommendation per frequency
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("min", ["hour", "minute", "day_of_week", "weekend"]),
        ("T", ["hour", "minute", "day_of_week", "weekend"]),
        ("h", ["hour", "day_of_week", "weekend"]),
        ("H", ["hour", "day_of_week", "weekend"]),
        ("B", ["day_of_week", "month"]),
        ("D", ["day_of_week", "weekend", "month"]),
        ("W", ["week", "month"]),
        ("MS", ["month", "quarter"]),
        ("ME", ["month", "quarter"]),
        ("M", ["month", "quarter"]),
        ("QS", ["quarter"]),
        ("QE", ["quarter"]),
        ("Q", ["quarter"]),
    ],
    ids=lambda v: f"value: {v}",
)
def test_select_calendar_features_output_per_frequency(frequency, expected):
    """
    Test select_calendar_features returns the expected base feature set for
    each supported frequency. The series length (1000) is above
    MIN_OBS_CALENDAR but below the sub-daily annual threshold, so no annual
    augmentation is applied.
    """
    result = select_calendar_features(
        task_type="single_series", frequency=frequency, n_observations=1000
    )

    assert result == expected


@pytest.mark.parametrize(
    "frequency, expected",
    [
        ("30min", ["hour", "minute", "day_of_week", "weekend"]),
        ("2h", ["hour", "day_of_week", "weekend"]),
        ("W-SUN", ["week", "month"]),
        ("QS-OCT", ["quarter"]),
        ("ms", ["month", "quarter"]),
    ],
    ids=lambda v: f"value: {v}",
)
def test_select_calendar_features_normalizes_anchored_and_multiplied_frequency(
    frequency, expected
):
    """
    Test select_calendar_features normalizes anchored offsets (e.g. 'W-SUN',
    'QS-OCT'), multiplied frequencies (e.g. '30min', '2h') and lowercase
    aliases to the same recommendation as their base unit.
    """
    result = select_calendar_features(
        task_type="single_series", frequency=frequency, n_observations=1000
    )

    assert result == expected


# ---------------------------------------------------------------------------
# select_calendar_features: length-aware annual (month) augmentation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "frequency, n_observations, expected",
    [
        (
            "h",
            MIN_YEARS_FOR_ANNUAL * OBS_PER_YEAR["H"] - 1,
            ["hour", "day_of_week", "weekend"],
        ),
        (
            "h",
            MIN_YEARS_FOR_ANNUAL * OBS_PER_YEAR["H"],
            ["hour", "day_of_week", "weekend", "month"],
        ),
        (
            "min",
            MIN_YEARS_FOR_ANNUAL * OBS_PER_YEAR["MIN"] - 1,
            ["hour", "minute", "day_of_week", "weekend"],
        ),
        (
            "min",
            MIN_YEARS_FOR_ANNUAL * OBS_PER_YEAR["MIN"],
            ["hour", "minute", "day_of_week", "weekend", "month"],
        ),
    ],
    ids=lambda v: f"value: {v}",
)
def test_select_calendar_features_appends_month_for_long_subdaily_series(
    frequency, n_observations, expected
):
    """
    Test select_calendar_features appends 'month' to sub-daily frequencies
    only when the series spans at least MIN_YEARS_FOR_ANNUAL full years, so
    annual seasonality can be modeled without overfitting short histories.
    """
    result = select_calendar_features(
        task_type="single_series",
        frequency=frequency,
        n_observations=n_observations,
    )

    assert result == expected


def test_select_calendar_features_does_not_duplicate_month_for_daily_series():
    """
    Test select_calendar_features does not duplicate 'month' for daily
    series, which already include it in the base recommendation and are not
    subject to sub-daily annual augmentation.
    """
    result = select_calendar_features(
        task_type="single_series",
        frequency="D",
        n_observations=100 * OBS_PER_YEAR["H"],
    )

    assert result == ["day_of_week", "weekend", "month"]


def test_select_calendar_features_returns_fresh_list():
    """
    Test select_calendar_features returns a new list each call so callers
    mutating the result do not corrupt the shared relevance map.
    """
    result_1 = select_calendar_features(
        task_type="single_series", frequency="D", n_observations=1000
    )
    result_1.append("year")
    result_2 = select_calendar_features(
        task_type="single_series", frequency="D", n_observations=1000
    )

    assert result_2 == ["day_of_week", "weekend", "month"]


# ---------------------------------------------------------------------------
# select_calendar_encoding
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "task_type",
    ["statistical", "foundation"],
    ids=lambda t: f"task_type: {t}",
)
def test_select_calendar_encoding_None_when_task_not_machine_learning(task_type):
    """
    Test select_calendar_encoding returns None for statistical and
    foundation task types (calendar features are not generated for them).
    """
    result = select_calendar_encoding(estimator="Ridge", task_type=task_type)

    assert result is None


@pytest.mark.parametrize(
    "estimator",
    sorted(TREE_BASED_ESTIMATORS),
    ids=lambda e: f"estimator: {e}",
)
def test_select_calendar_encoding_None_when_tree_based_estimator(estimator):
    """
    Test select_calendar_encoding returns None for tree-based estimators,
    which split on raw ordinal calendar values natively.
    """
    result = select_calendar_encoding(
        estimator=estimator, task_type="single_series"
    )

    assert result is None


@pytest.mark.parametrize(
    "estimator",
    ["Ridge", "LinearRegression", "SVR", "KNeighborsRegressor", "MLPRegressor"],
    ids=lambda e: f"estimator: {e}",
)
def test_select_calendar_encoding_cyclical_when_non_tree_estimator(estimator):
    """
    Test select_calendar_encoding returns 'cyclical' for non-tree
    estimators (linear, SVM, KNN, neural networks), which benefit from a
    smooth sine/cosine representation of calendar features.
    """
    result = select_calendar_encoding(
        estimator=estimator, task_type="single_series"
    )

    assert result == "cyclical"
