# Unit test describe_interval_coverage execution/interval_coverage

import pytest

from skforecast_ai.execution.interval_coverage import describe_interval_coverage

# Fixtures
from .fixtures_interval_coverage import (
    interval,
    predictions_single_200,
    metrics_single_06,
    metrics_single_no_interval,
    predictions_multi_2,
    metrics_multi_2,
    predictions_multi_12,
    metrics_multi_12,
)


def test_describe_interval_coverage_single_series():
    """
    Test the exact sentence of a single series: share of values inside the
    interval, coverage and mean width.
    """
    results = describe_interval_coverage(
        metrics     = metrics_single_06,
        predictions = predictions_single_200,
        interval    = interval,
    )

    expected = (
        "Prediction interval [0.1, 0.9] (nominal coverage 80 %): 60 % of the "
        "200 actual values fell inside it (coverage: 0.6000), with a mean "
        "width of 4.0000 in the units of the target (interval_width)."
    )
    assert results == expected


def test_describe_interval_coverage_two_series_with_average_row():
    """
    Test the exact sentence of two series: one part per series and the
    `average` row of the metrics at the end.
    """
    results = describe_interval_coverage(
        metrics     = metrics_multi_2,
        predictions = predictions_multi_2,
        interval    = interval,
    )

    expected = (
        "Prediction interval [0.1, 0.9] (nominal coverage 80 %), share of "
        "the actual values inside it (coverage) and mean width in the units "
        "of each series (interval_width), by series: 'a' 80 % of 100 "
        "predictions, width 4.0000; 'b' 50 % of 100 predictions, width "
        "3.0000; average across series 65 %, width 3.5000."
    )
    assert results == expected


def test_describe_interval_coverage_lists_ten_lowest_series_when_more_than_ten():
    """
    Test that with 12 series only the 10 with the lowest coverage are listed,
    from the lowest, and the intro says so (s01 and s11 are left out).
    """
    results = describe_interval_coverage(
        metrics     = metrics_multi_12,
        predictions = predictions_multi_12,
        interval    = interval,
    )

    expected = (
        "Prediction interval [0.1, 0.9] (nominal coverage 80 %), share of "
        "the actual values inside it (coverage) and mean width in the units "
        "of each series (interval_width), for the 10 series with the lowest "
        "coverage of 12: "
        "'s02' 55 % of 100 predictions, width 2.0000; "
        "'s04' 60 % of 100 predictions, width 2.0000; "
        "'s06' 65 % of 100 predictions, width 2.0000; "
        "'s08' 70 % of 100 predictions, width 2.0000; "
        "'s12' 72 % of 100 predictions, width 2.0000; "
        "'s10' 75 % of 100 predictions, width 2.0000; "
        "'s07' 78 % of 100 predictions, width 2.0000; "
        "'s05' 80 % of 100 predictions, width 2.0000; "
        "'s09' 82 % of 100 predictions, width 2.0000; "
        "'s03' 85 % of 100 predictions, width 2.0000; "
        "average across series 75 %, width 2.0000."
    )
    assert results == expected


@pytest.mark.parametrize(
    'metrics, interval_arg',
    [
        (metrics_single_06, None),
        (metrics_single_no_interval, interval),
        (None, interval),
    ],
    ids=['interval None', 'metrics without coverage columns', 'metrics None']
)
def test_describe_interval_coverage_none_without_interval(metrics, interval_arg):
    """
    Test that None is returned when there is no interval, the metrics carry
    no coverage columns or there are no metrics.
    """
    results = describe_interval_coverage(
        metrics     = metrics,
        predictions = predictions_single_200,
        interval    = interval_arg,
    )

    assert results is None
