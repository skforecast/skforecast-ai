# Unit test long_comparison_message

from skforecast_ai._utils import long_comparison_message
from skforecast_ai.schemas import CandidateCost, ComparisonCost


def _cost(forecaster, n_fits, estimator_fits, inference_windows=0):
    """Return the CandidateCost of a candidate."""
    return CandidateCost(
        forecaster        = forecaster,
        n_fits            = n_fits,
        estimator_fits    = estimator_fits,
        inference_windows = inference_windows,
    )


def test_long_comparison_message_output_when_candidates_are_direct_and_baseline():
    """
    Test that the message states the total of estimator fits, each
    candidate with its fits, the direct candidates with their trainings x
    estimators and the baseline with 0, without a final period.
    """
    cost = ComparisonCost(
        n_folds    = 6,
        candidates = {
            "direct": _cost("ForecasterDirect", 6, 36),
            "recursive": _cost("ForecasterRecursive", 6, 6),
            "Baseline (seasonal naive)": _cost("ForecasterEquivalentDate", 6, 0),
            "direct_2": _cost("ForecasterDirect", 3, 18),
        },
    )

    result = long_comparison_message(cost=cost, steps=6)

    assert result == (
        "The comparison will fit 60 estimators in all ('direct': 36 "
        "(6 trainings x 6 estimators), 'recursive': 6, 'Baseline (seasonal "
        "naive)': 0, 'direct_2': 18 (3 trainings x 6 estimators))"
    )


def test_long_comparison_message_output_when_candidates_are_not_direct():
    """
    Test that the candidates that are not direct show only their fits (a
    ForecasterStats and a ForecasterFoundation with 0), with no breakdown.
    """
    cost = ComparisonCost(
        n_folds    = 51,
        candidates = {
            "stats": _cost("ForecasterStats", 51, 51),
            "foundation": _cost("ForecasterFoundation", 0, 0, 300),
        },
    )

    result = long_comparison_message(cost=cost, steps=5)

    assert result == (
        "The comparison will fit 51 estimators in all ('stats': 51, "
        "'foundation': 0)"
    )
