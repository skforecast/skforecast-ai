# Unit test describe_low_coverage_candidates execution/interval_coverage

from types import SimpleNamespace

from skforecast_ai.execution.interval_coverage import (
    describe_low_coverage_candidates,
)

# Fixtures
from .fixtures_interval_coverage import (
    interval,
    predictions_single_200,
    predictions_single_400,
    metrics_single_06,
    metrics_single_078,
    predictions_multi_3,
    metrics_multi_3,
)


def _candidate(metrics, predictions):
    """Backtest result with the three attributes the function reads."""
    return SimpleNamespace(
        metrics     = metrics,
        predictions = predictions,
        plan        = SimpleNamespace(interval=interval),
    )


candidate_single_low = _candidate(metrics_single_06, predictions_single_200)
candidate_single_ok = _candidate(metrics_single_078, predictions_single_400)
candidate_multi_low = _candidate(metrics_multi_3, predictions_multi_3)


def test_describe_low_coverage_candidates_names_single_and_multi_series_candidates():
    """
    Test the exact message naming a single-series candidate (60 % of 200
    values) and a multi-series candidate (1 of 3 series, the lowest 'b' at
    50 %), and that a candidate that is not low is not named.
    """
    candidates = {
        "ridge": candidate_single_low,
        "good": candidate_single_ok,
        "multi": candidate_multi_low,
    }

    results = describe_low_coverage_candidates(
        candidates = candidates,
        interval   = interval,
    )

    expected = (
        "The prediction interval [0.1, 0.9] has a nominal coverage of 80 %, "
        "but it covered clearly less (more than 2 binomial standard errors "
        "for the number of predictions, and at least 5 percentage points, "
        "below 80 %) in these candidates: "
        "'ridge' (60 % of 200 actual values), "
        "'multi' (1 of 3 series, the lowest 'b' at 50 %). "
        "Do not present their interval as covering 80 %: report the "
        "coverage measured in the backtest (the `coverage` column of the "
        "table, and of the metrics of each candidate by series)."
    )
    assert results == expected


def test_describe_low_coverage_candidates_none_when_no_candidate_is_low():
    """
    Test that None is returned when no candidate is below the threshold.
    """
    results = describe_low_coverage_candidates(
        candidates = {"good": candidate_single_ok},
        interval   = interval,
    )

    assert results is None


def test_describe_low_coverage_candidates_none_when_interval_is_none():
    """
    Test that None is returned when the comparison has no interval, even if a
    candidate has a low coverage.
    """
    results = describe_low_coverage_candidates(
        candidates = {"ridge": candidate_single_low},
        interval   = None,
    )

    assert results is None
