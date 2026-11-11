# Unit test comparison_remedies

import pytest

from skforecast_ai._utils import comparison_remedies
from skforecast_ai.schemas import CandidateCost, ComparisonCost

_REFIT = "an integer `refit` (retrain every n folds)"
_FOLDS_SKIP = (
    "fewer folds (a later `initial_train_size`, a larger `fold_stride` or "
    "`skip_folds`)"
)
_FOLDS = "fewer folds (a later `initial_train_size` or a larger `fold_stride`)"
_NO_REFIT = "`refit=False` (train once)"
_HORIZON = "a shorter horizon (a direct forecaster fits one estimator per step)"
_SERIES = "fewer series"


def _comparison(candidates):
    """
    Return the ComparisonCost of candidates given as
    `name: (forecaster, n_fits, estimator_fits, inference_windows)`.
    """
    return ComparisonCost(
        n_folds    = 6,
        candidates = {
            name: CandidateCost(
                forecaster        = forecaster,
                n_fits            = n_fits,
                estimator_fits    = estimator_fits,
                inference_windows = inference_windows,
            )
            for name, (forecaster, n_fits, estimator_fits, inference_windows)
            in candidates.items()
        },
    )


@pytest.mark.parametrize(
    "candidates, n_fits, steps, expected",
    [
        (
            {"recursive": ("ForecasterRecursive", 6, 60, 0)},
            6, 5, [_REFIT, _FOLDS_SKIP, _NO_REFIT],
        ),
        (
            {
                "recursive": ("ForecasterRecursive", 6, 30, 0),
                "direct": ("ForecasterDirect", 6, 30, 0),
                "baseline": ("ForecasterEquivalentDate", 6, 0, 0),
            },
            6, 5, [_REFIT, _FOLDS_SKIP, _NO_REFIT],
        ),
        (
            {
                "recursive": ("ForecasterRecursive", 6, 60, 0),
                "foundation": ("ForecasterFoundation", 0, 0, 100),
            },
            6, 5, [_REFIT, _FOLDS_SKIP, _NO_REFIT],
        ),
        (
            {
                "recursive": ("ForecasterRecursive", 6, 60, 0),
                "foundation": ("ForecasterFoundation", 0, 0, 2400),
            },
            6, 5, [_REFIT, _FOLDS_SKIP, _NO_REFIT, _SERIES],
        ),
        (
            {
                "recursive": ("ForecasterRecursive", 6, 10, 0),
                "foundation": ("ForecasterFoundation", 0, 0, 3000),
            },
            6, 5, [_FOLDS_SKIP, _SERIES],
        ),
        (
            {
                "recursive": ("ForecasterRecursive", 6, 60, 0),
                "stats": ("ForecasterStats", 6, 6, 0),
            },
            6, 5, [_REFIT, _FOLDS, _NO_REFIT],
        ),
        (
            {
                "recursive": ("ForecasterRecursive", 6, 60, 0),
                "stats": ("ForecasterStats", 6, 0, 0),
            },
            6, 5, [_REFIT, _FOLDS, _NO_REFIT],
        ),
        (
            {
                "stats": ("ForecasterStats", 6, 5, 0),
                "foundation": ("ForecasterFoundation", 0, 0, 3000),
            },
            6, 5, [_FOLDS, _SERIES],
        ),
        (
            {
                "direct": ("ForecasterDirect", 1, 60, 0),
                "baseline": ("ForecasterEquivalentDate", 1, 0, 0),
            },
            1, 60, [_HORIZON],
        ),
        (
            {
                "recursive": ("ForecasterRecursive", 6, 10, 0),
                "foundation": ("ForecasterFoundation", 0, 0, 100),
            },
            6, 5, [],
        ),
    ],
    ids=[
        "fits_above",
        "fits_above_of_two_candidates_and_baseline",
        "fits_above_foundation_windows_below",
        "fits_and_windows_above",
        "windows_above_only",
        "fits_above_with_stats",
        "fits_above_with_stats_without_fits",
        "windows_above_with_stats",
        "fits_above_direct_trained_once",
        "both_below",
    ],
)
def test_comparison_remedies_output(candidates, n_fits, steps, expected):
    """
    Test that comparison_remedies names the changes of cost_remedies for
    the forecasters whose cost puts the comparison above a threshold: the
    candidates that fit estimators when the fits in all are above 50, and
    ForecasterFoundation when the windows in all are above 2000 (its
    estimator fits are 0, so it is not counted among the first). The
    baseline never counts, `skip_folds` is left out when any candidate is
    a ForecasterStats, and a comparison below both thresholds has none.
    """
    result = comparison_remedies(
        cost   = _comparison(candidates),
        n_fits = n_fits,
        steps  = steps,
    )

    assert result == expected


def test_comparison_remedies_output_when_false_is_lowercase():
    """
    Test that `false` sets how `refit=False` is written, as the JSON
    arguments of the MCP server need.
    """
    result = comparison_remedies(
        cost   = _comparison({"recursive": ("ForecasterRecursive", 6, 60, 0)}),
        n_fits = 6,
        steps  = 5,
        false  = "false",
    )

    assert result == [_REFIT, _FOLDS_SKIP, "`refit=false` (train once)"]
