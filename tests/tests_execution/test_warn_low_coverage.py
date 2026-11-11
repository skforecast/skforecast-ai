# Unit test warn_low_coverage execution/interval_coverage

import re
import warnings
import pytest

from skforecast_ai.exceptions import IntervalCoverageWarning
from skforecast_ai.execution.interval_coverage import warn_low_coverage

# Fixtures
from .fixtures_interval_coverage import (
    interval,
    predictions_single_20,
    predictions_single_200,
    predictions_single_400,
    metrics_single_06,
    metrics_single_07,
    metrics_single_078,
    metrics_single_no_interval,
    predictions_multi_3,
    metrics_multi_3,
    predictions_multi_7,
    metrics_multi_7,
)

_RULE = (
    "(more than 2 binomial standard errors for the number of predictions, "
    "and at least 5 percentage points, below 80 %)"
)


def test_warn_low_coverage_warns_single_series_when_coverage_clearly_low():
    """
    Test that a single series with a coverage of 0.6 over 200 predictions
    (threshold 0.75) emits an IntervalCoverageWarning with the exact text.
    """
    warn_msg = re.escape(
        "The prediction interval [0.1, 0.9] has a nominal coverage of 80 %, "
        "but only 60 % of the 200 actual values of the backtest fell inside "
        f"it {_RULE}. Do not present this interval as covering 80 %: report "
        "the coverage measured in the backtest (the `coverage` column of "
        "the metrics)."
    )
    with pytest.warns(IntervalCoverageWarning, match=f"^{warn_msg}$"):
        warn_low_coverage(
            metrics     = metrics_single_06,
            predictions = predictions_single_200,
            interval    = interval,
        )


@pytest.mark.parametrize(
    'metrics, predictions',
    [
        (metrics_single_07, predictions_single_20),
        (metrics_single_078, predictions_single_400),
    ],
    ids=['slightly low with few predictions', 'close to nominal, many predictions']
)
def test_warn_low_coverage_no_warning_when_coverage_not_clearly_low(
    metrics, predictions
):
    """
    Test that no warning is emitted for a coverage of 0.7 over 20 predictions
    (threshold 0.6211) or of 0.78 over 400 predictions (threshold 0.75).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        results = warn_low_coverage(
            metrics     = metrics,
            predictions = predictions,
            interval    = interval,
        )

    assert results is None


def test_warn_low_coverage_names_only_low_series_in_multi_series():
    """
    Test that with three series where only 'b' (0.5 over 100 predictions,
    threshold 0.72) is low, the warning names only 'b' and counts 1 of 3.
    """
    warn_msg = re.escape(
        "The prediction interval [0.1, 0.9] has a nominal coverage of 80 %, "
        "but it covered clearly less in 1 of 3 series (share of the actual "
        "values inside it): 'b' 50 % of 100 predictions "
        f"{_RULE}. Do not present the interval of these series as covering "
        "80 %: report the coverage measured in the backtest (the `coverage` "
        "column of the metrics)."
    )
    with pytest.warns(IntervalCoverageWarning, match=f"^{warn_msg}$"):
        warn_low_coverage(
            metrics     = metrics_multi_3,
            predictions = predictions_multi_3,
            interval    = interval,
        )


def test_warn_low_coverage_names_five_lowest_series_and_counts_the_rest():
    """
    Test that with 7 low series the warning names the 5 with the lowest
    coverage, from the lowest, and counts the other 2.
    """
    warn_msg = re.escape(
        "The prediction interval [0.1, 0.9] has a nominal coverage of 80 %, "
        "but it covered clearly less in 7 of 7 series (share of the actual "
        "values inside it): 's2' 30 % of 100 predictions, 's5' 35 % of 100 "
        "predictions, 's4' 40 % of 100 predictions, 's7' 45 % of 100 "
        "predictions, 's6' 50 % of 100 predictions and 2 more series "
        f"{_RULE}. Do not present the interval of these series as covering "
        "80 %: report the coverage measured in the backtest (the `coverage` "
        "column of the metrics)."
    )
    with pytest.warns(IntervalCoverageWarning, match=f"^{warn_msg}$"):
        warn_low_coverage(
            metrics     = metrics_multi_7,
            predictions = predictions_multi_7,
            interval    = interval,
        )


@pytest.mark.parametrize(
    'metrics, interval_arg',
    [
        (metrics_single_06, None),
        (metrics_single_no_interval, interval),
        (None, interval),
    ],
    ids=['interval None', 'metrics without coverage columns', 'metrics None']
)
def test_warn_low_coverage_no_warning_when_interval_not_measured(
    metrics, interval_arg
):
    """
    Test that no warning is emitted when there is no interval, the metrics
    carry no coverage columns or there are no metrics.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        results = warn_low_coverage(
            metrics     = metrics,
            predictions = predictions_single_200,
            interval    = interval_arg,
        )

    assert results is None
