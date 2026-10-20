# Unit test low_coverage_series execution/interval_coverage

from skforecast_ai.execution.interval_coverage import (
    SeriesCoverage,
    low_coverage_series,
)

# Fixtures
from .fixtures_interval_coverage import interval


def test_low_coverage_series_sorted_from_lowest_coverage():
    """
    Test that only the series below the threshold are returned (with n=100
    the threshold is 0.72), from the lowest coverage to the highest.
    """
    coverages = [
        SeriesCoverage("a", 0.80, 4.0, 100),
        SeriesCoverage("b", 0.60, 4.0, 100),
        SeriesCoverage("c", 0.71, 4.0, 100),
        SeriesCoverage("d", 0.30, 4.0, 100),
        SeriesCoverage("e", 0.73, 4.0, 100),
    ]

    results = low_coverage_series(coverages=coverages, interval=interval)

    assert results == [
        SeriesCoverage("d", 0.30, 4.0, 100),
        SeriesCoverage("b", 0.60, 4.0, 100),
        SeriesCoverage("c", 0.71, 4.0, 100),
    ]


def test_low_coverage_series_keeps_order_on_tie():
    """
    Test that series with the same coverage keep the order of the input.
    """
    coverages = [
        SeriesCoverage("x", 0.5, 4.0, 100),
        SeriesCoverage("y", 0.5, 4.0, 100),
    ]

    results = low_coverage_series(coverages=coverages, interval=interval)

    assert [r.series for r in results] == ["x", "y"]


def test_low_coverage_series_threshold_depends_on_number_of_predictions():
    """
    Test that the same coverage of 0.7 is low with 400 predictions
    (threshold 0.75) and not low with 20 (threshold 0.6211).
    """
    coverages = [
        SeriesCoverage("many", 0.7, 4.0, 400),
        SeriesCoverage("few", 0.7, 4.0, 20),
    ]

    results = low_coverage_series(coverages=coverages, interval=interval)

    assert results == [SeriesCoverage("many", 0.7, 4.0, 400)]


def test_low_coverage_series_empty_list():
    """
    Test that an empty list of coverages gives an empty list.
    """
    results = low_coverage_series(coverages=[], interval=interval)

    assert results == []
