# Unit test series_coverages execution/interval_coverage

import pytest

from skforecast_ai.execution.interval_coverage import (
    SeriesCoverage,
    series_coverages,
)

# Fixtures
from .fixtures_interval_coverage import (
    interval,
    predictions_single_200,
    predictions_single_200_nan,
    predictions_foundation_50,
    metrics_single_06,
    metrics_single_084,
    metrics_single_no_interval,
    metrics_single_nan_coverage,
    predictions_multi_3,
    metrics_multi_3,
    metrics_multi_3_nan_coverage,
    predictions_multi_nan_bounds,
    metrics_multi_nan_bounds,
)


def test_series_coverages_single_series():
    """
    Test that a single-series backtest gives one SeriesCoverage with series
    None, the coverage and width of the metrics and the number of predictions.
    """
    results = series_coverages(
        metrics     = metrics_single_06,
        predictions = predictions_single_200,
        interval    = interval,
    )

    assert results == [
        SeriesCoverage(
            series=None, coverage=0.6, interval_width=4.0, n_predictions=200
        )
    ]


def test_series_coverages_single_series_counts_only_predictions_with_both_bounds():
    """
    Test that the number of predictions of a single series does not count
    the rows with a missing lower or upper bound (200 - 3 - 2 = 195).
    """
    results = series_coverages(
        metrics     = metrics_single_06,
        predictions = predictions_single_200_nan,
        interval    = interval,
    )

    assert results == [
        SeriesCoverage(
            series=None, coverage=0.6, interval_width=4.0, n_predictions=195
        )
    ]


def test_series_coverages_foundation_quantile_columns():
    """
    Test that the `q_<lower>` and `q_<upper>` columns of a foundation model
    are used as bounds when `lower_bound` and `upper_bound` are absent (50
    predictions, one with a missing upper quantile).
    """
    results = series_coverages(
        metrics     = metrics_single_084,
        predictions = predictions_foundation_50,
        interval    = interval,
    )

    assert results == [
        SeriesCoverage(
            series=None, coverage=0.84, interval_width=3.0, n_predictions=49
        )
    ]


def test_series_coverages_multi_series_ignores_aggregated_rows():
    """
    Test that multi-series metrics give one SeriesCoverage per series, in the
    order of the metrics, without the `average`, `weighted_average` and
    `pooling` rows.
    """
    results = series_coverages(
        metrics     = metrics_multi_3,
        predictions = predictions_multi_3,
        interval    = interval,
    )

    assert results == [
        SeriesCoverage(
            series="a", coverage=0.8, interval_width=4.0, n_predictions=100
        ),
        SeriesCoverage(
            series="b", coverage=0.5, interval_width=3.0, n_predictions=100
        ),
        SeriesCoverage(
            series="c", coverage=0.82, interval_width=5.0, n_predictions=100
        ),
    ]


def test_series_coverages_multi_series_counts_only_rows_with_both_bounds():
    """
    Test that the number of predictions of each series counts only the rows
    with both bounds: series 'a' has 5 rows and one NaN lower bound (n=4);
    series 'b' has no row with both bounds, so it is left out.
    """
    results = series_coverages(
        metrics     = metrics_multi_nan_bounds,
        predictions = predictions_multi_nan_bounds,
        interval    = interval,
    )

    assert results == [
        SeriesCoverage(
            series="a", coverage=0.75, interval_width=4.0, n_predictions=4
        )
    ]


def test_series_coverages_multi_series_leaves_out_series_with_nan_coverage():
    """
    Test that a series whose coverage is NaN is left out of the result.
    """
    results = series_coverages(
        metrics     = metrics_multi_3_nan_coverage,
        predictions = predictions_multi_3,
        interval    = interval,
    )

    assert results == [
        SeriesCoverage(
            series="a", coverage=0.8, interval_width=4.0, n_predictions=100
        ),
        SeriesCoverage(
            series="b", coverage=0.5, interval_width=3.0, n_predictions=100
        ),
    ]


def test_series_coverages_multi_series_foundation_quantile_columns():
    """
    Test that the quantile columns of a foundation model also give the
    number of predictions of each series.
    """
    predictions = predictions_multi_3.rename(
        columns={"lower_bound": "q_0.1", "upper_bound": "q_0.9"}
    )

    results = series_coverages(
        metrics     = metrics_multi_3,
        predictions = predictions,
        interval    = interval,
    )

    assert [(r.series, r.n_predictions) for r in results] == [
        ("a", 100), ("b", 100), ("c", 100)
    ]


def test_series_coverages_single_series_left_out_when_nan_coverage():
    """
    Test that a single series whose coverage is NaN gives an empty list.
    """
    results = series_coverages(
        metrics     = metrics_single_nan_coverage,
        predictions = predictions_single_200,
        interval    = interval,
    )

    assert results == []


@pytest.mark.parametrize(
    'metrics, predictions, interval_arg',
    [
        (metrics_single_06, predictions_single_200, None),
        (None, predictions_single_200, interval),
        (metrics_single_06, None, interval),
        (metrics_single_no_interval, predictions_single_200, interval),
        (metrics_single_06, predictions_single_200[["pred"]], interval),
    ],
    ids=[
        'interval None', 'metrics None', 'predictions None',
        'metrics without coverage columns', 'predictions without bounds',
    ]
)
def test_series_coverages_empty_when_interval_not_measured(
    metrics, predictions, interval_arg
):
    """
    Test that an empty list is returned when there is no interval, no
    metrics, no predictions, no coverage columns in the metrics or no bound
    columns in the predictions.
    """
    results = series_coverages(
        metrics     = metrics,
        predictions = predictions,
        interval    = interval_arg,
    )

    assert results == []


def test_series_coverages_takes_the_count_from_n_evaluated():
    """
    Test that, with the `n_evaluated` column of skforecast 0.27, the number
    of predictions of each series is the number of points its metrics are
    measured on (without the predictions of overlapping folds, which the
    predictions keep), not the rows of the predictions; a row with a missing
    `n_evaluated` falls back to counting them.
    """
    metrics_single = metrics_single_06.assign(n_evaluated=[150])
    metrics_multi = metrics_multi_3.assign(n_evaluated=[90, 80, None, 0, 0, 0])

    single = series_coverages(
        metrics     = metrics_single,
        predictions = predictions_single_200,
        interval    = interval,
    )
    multi = series_coverages(
        metrics     = metrics_multi,
        predictions = predictions_multi_3,
        interval    = interval,
    )

    assert single == [
        SeriesCoverage(
            series=None, coverage=0.6, interval_width=4.0, n_predictions=150
        )
    ]
    assert [c.n_predictions for c in multi] == [90, 80, 100]


def test_series_coverages_does_not_count_rows_without_observed_value():
    """
    Test that, without `n_evaluated`, the predictions whose observed value
    (`y_true` of skforecast 0.27) is missing are not counted, since the
    coverage of skforecast is measured on the observed values.
    """
    predictions = predictions_single_200.assign(y_true=1.0)
    predictions.loc[[0, 1, 2, 3], "y_true"] = float("nan")

    results = series_coverages(
        metrics     = metrics_single_06,
        predictions = predictions,
        interval    = interval,
    )

    assert results[0].n_predictions == 196
