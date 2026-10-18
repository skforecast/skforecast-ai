# Unit test warn_long_comparison

import re
import warnings

import pytest
from skforecast.exceptions import LongTrainingWarning

from skforecast_ai._utils import warn_long_comparison
from skforecast_ai.schemas import CandidateCost, ComparisonCost


def _cost(forecaster, n_fits, estimator_fits):
    """Return the CandidateCost of a candidate that has no inference window."""
    return CandidateCost(
        forecaster        = forecaster,
        n_fits            = n_fits,
        estimator_fits    = estimator_fits,
        inference_windows = 0,
    )


def test_warn_long_comparison_no_warning_when_total_fits_within_threshold():
    """
    Test that no warning is emitted when the candidates fit 50 estimators
    in all, the threshold, even though one fits most of them.
    """
    cost = ComparisonCost(
        n_folds    = 6,
        candidates = {
            "direct": _cost("ForecasterDirect", 6, 42),
            "recursive": _cost("ForecasterRecursive", 6, 8),
        },
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warn_long_comparison(cost=cost, n_fits=6, steps=7)


def test_warn_long_comparison_message_when_total_fits_exceed_threshold():
    """
    Test that the warning states the total, each candidate with its fits,
    the direct candidates with their trainings and estimators, the baseline
    with 0, and the remedies of a forecaster trained more than once.
    """
    cost = ComparisonCost(
        n_folds    = 6,
        candidates = {
            "direct": _cost("ForecasterDirect", 6, 36),
            "recursive": _cost("ForecasterRecursive", 6, 6),
            "Baseline (seasonal naive)": _cost("ForecasterEquivalentDate", 6, 0),
            "direct_2": _cost("ForecasterDirect", 6, 36),
        },
    )

    msg = re.escape(
        "The comparison will fit 78 estimators in all ('direct': 36 "
        "(6 trainings x 6 estimators), 'recursive': 6, 'Baseline (seasonal "
        "naive)': 0, 'direct_2': 36 (6 trainings x 6 estimators)). This can "
        "take substantial amounts of time. If not feasible, compare fewer "
        "candidates or use an integer `refit` (retrain every n folds), fewer "
        "folds (a later `initial_train_size`, a larger `fold_stride` or "
        "`skip_folds`) or `refit=False` (train once)."
    )
    with pytest.warns(LongTrainingWarning, match=msg):
        warn_long_comparison(cost=cost, n_fits=6, steps=6)


def test_warn_long_comparison_message_when_candidates_are_stats_and_baseline():
    """
    Test that for a ForecasterStats candidate (one fit per fold) the
    remedies are only fewer folds, without `skip_folds`, and that the
    baseline is listed with 0.
    """
    cost = ComparisonCost(
        n_folds    = 51,
        candidates = {
            "stats": _cost("ForecasterStats", 51, 51),
            "Baseline (seasonal naive)": _cost("ForecasterEquivalentDate", 1, 0),
        },
    )

    msg = re.escape(
        "The comparison will fit 51 estimators in all ('stats': 51, "
        "'Baseline (seasonal naive)': 0). This can take substantial amounts "
        "of time. If not feasible, compare fewer candidates or use fewer "
        "folds (a later `initial_train_size` or a larger `fold_stride`)."
    )
    with pytest.warns(LongTrainingWarning, match=msg):
        warn_long_comparison(cost=cost, n_fits=1, steps=5)


def test_warn_long_comparison_message_without_skip_folds_when_stats_has_no_fits():
    """
    Test that `skip_folds` is not named when the comparison has a
    ForecasterStats candidate, even when it adds no fit to the total.
    """
    cost = ComparisonCost(
        n_folds    = 6,
        candidates = {
            "recursive": _cost("ForecasterRecursive", 6, 60),
            "stats": _cost("ForecasterStats", 6, 0),
        },
    )

    msg = re.escape(
        "The comparison will fit 60 estimators in all ('recursive': 60, "
        "'stats': 0). This can take substantial amounts of time. If not "
        "feasible, compare fewer candidates or use an integer `refit` "
        "(retrain every n folds), fewer folds (a later `initial_train_size` "
        "or a larger `fold_stride`) or `refit=False` (train once)."
    )
    with pytest.warns(LongTrainingWarning, match=msg):
        warn_long_comparison(cost=cost, n_fits=6, steps=5)
