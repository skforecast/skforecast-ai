# Unit test exclude_costly_candidates execution/comparison

from skforecast_ai.execution.comparison import exclude_costly_candidates

_CANDIDATES = [
    ("recursive", {"forecaster": "ForecasterRecursive"}),
    ("stats", {"forecaster": "ForecasterStats"}),
]


def test_exclude_costly_candidates_leaves_out_stats_when_n_folds_exceed_budget():
    """
    Test that an automatic ForecasterStats candidate is left out when the
    folds of the strategy exceed the budget, even though `n_fits` is 1
    (skforecast refits it in every fold), and the preferred forecaster is
    kept.
    """
    kept, note = exclude_costly_candidates(
        candidate_configs = _CANDIDATES,
        preferred         = "ForecasterRecursive",
        n_fits            = 1,
        steps             = 5,
        budget            = 10,
        n_folds           = 12,
    )

    assert kept == [_CANDIDATES[0]]
    assert note == (
        "Left out of the automatic candidates because this cross-validation "
        "strategy exceeds the budget of 10 estimator fits: 'stats': "
        "ForecasterStats will be fit 12 times. Pass them in `candidates` to "
        "include them."
    )


def test_exclude_costly_candidates_keeps_stats_when_n_folds_is_none():
    """
    Test that without `n_folds` the cost of ForecasterStats is `n_fits`,
    so it stays within the budget as before.
    """
    kept, note = exclude_costly_candidates(
        candidate_configs = _CANDIDATES,
        preferred         = "ForecasterRecursive",
        n_fits            = 1,
        steps             = 5,
        budget            = 10,
    )

    assert kept == _CANDIDATES
    assert note is None


def test_exclude_costly_candidates_keeps_preferred_stats_when_n_folds_exceed_budget():
    """
    Test that ForecasterStats is never left out when it is the preferred
    forecaster, whatever the number of folds.
    """
    kept, note = exclude_costly_candidates(
        candidate_configs = _CANDIDATES,
        preferred         = "ForecasterStats",
        n_fits            = 1,
        steps             = 5,
        budget            = 10,
        n_folds           = 12,
    )

    assert kept == _CANDIDATES
    assert note is None
