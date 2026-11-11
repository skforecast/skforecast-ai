# Unit test coverage_threshold execution/interval_coverage

import math

from skforecast_ai.execution.interval_coverage import coverage_threshold


def test_coverage_threshold_floor_wins_when_many_predictions():
    """
    Test that with many predictions (nominal 0.8, n=400) the binomial term
    (2 * sqrt(0.16 / 400) = 0.04) is below the minimum shortfall of 0.05, so
    the threshold is 0.8 - 0.05 = 0.75.
    """
    results = coverage_threshold(nominal=0.8, n_predictions=400)

    assert results == 0.75


def test_coverage_threshold_binomial_term_wins_when_few_predictions():
    """
    Test that with few predictions (nominal 0.8, n=62) the binomial term
    (2 * sqrt(0.16 / 62) = 0.1016) is above the minimum shortfall, so the
    threshold is 0.8 - 0.1016.
    """
    results = coverage_threshold(nominal=0.8, n_predictions=62)

    assert math.isclose(results, 0.6983998983998476)


def test_coverage_threshold_minus_infinity_when_no_predictions():
    """
    Test that the threshold is minus infinity when there is no prediction, so
    no coverage can fall below it.
    """
    results = coverage_threshold(nominal=0.8, n_predictions=0)

    assert results == -math.inf
