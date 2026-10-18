# Unit test count_comparison_cost execution/comparison

from skforecast_ai.execution.comparison import count_comparison_cost
from skforecast_ai.schemas import CandidateCost, ComparisonCost

_BASELINE = ("Baseline (seasonal naive)", {"forecaster": "ForecasterEquivalentDate"})
_DEFAULTS = [
    ("ForecasterRecursive", {"forecaster": "ForecasterRecursive"}),
    ("ForecasterDirect", {"forecaster": "ForecasterDirect"}),
    ("ForecasterStats", {"forecaster": "ForecasterStats"}),
]


def test_count_comparison_cost_output_when_only_the_strategy():
    """
    Test that a single candidate with an empty config takes the forecaster
    from `preferred`.
    """
    result = count_comparison_cost(
        candidate_configs = [("plan", {})],
        preferred         = "ForecasterDirect",
        steps             = 5,
        n_fits            = 4,
        n_folds           = 10,
        n_series          = 1,
    )

    assert result == ComparisonCost(
        n_folds    = 10,
        candidates = {
            "plan": CandidateCost(
                forecaster        = "ForecasterDirect",
                n_fits            = 4,
                estimator_fits    = 20,
                inference_windows = 0,
            )
        },
    )
    assert result.n_fits == 4
    assert result.estimator_fits == 20
    assert result.inference_windows == 0


def test_count_comparison_cost_output_when_default_candidates_and_baseline():
    """
    Test the cost of the default-like candidates plus the baseline: the
    baseline counts its trainings but no estimator fit, ForecasterStats
    counts one training per fold and the totals add up.
    """
    result = count_comparison_cost(
        candidate_configs = _DEFAULTS + [_BASELINE],
        preferred         = "ForecasterRecursive",
        steps             = 3,
        n_fits            = 4,
        n_folds           = 10,
        n_series          = 1,
    )

    assert result.n_folds == 10
    assert result.candidates == {
        "ForecasterRecursive": CandidateCost(
            forecaster="ForecasterRecursive", n_fits=4, estimator_fits=4,
            inference_windows=0,
        ),
        "ForecasterDirect": CandidateCost(
            forecaster="ForecasterDirect", n_fits=4, estimator_fits=12,
            inference_windows=0,
        ),
        "ForecasterStats": CandidateCost(
            forecaster="ForecasterStats", n_fits=10, estimator_fits=10,
            inference_windows=0,
        ),
        "Baseline (seasonal naive)": CandidateCost(
            forecaster="ForecasterEquivalentDate", n_fits=4, estimator_fits=0,
            inference_windows=0,
        ),
    }
    assert result.n_fits == 22
    assert result.estimator_fits == 26
    assert result.inference_windows == 0


def test_count_comparison_cost_output_when_default_candidates_without_baseline():
    """
    Test that the totals of the default-like candidates do not include the
    baseline when it is not among the candidates.
    """
    result = count_comparison_cost(
        candidate_configs = _DEFAULTS,
        preferred         = "ForecasterRecursive",
        steps             = 3,
        n_fits            = 4,
        n_folds           = 10,
        n_series          = 1,
    )

    assert list(result.candidates) == [
        "ForecasterRecursive", "ForecasterDirect", "ForecasterStats"
    ]
    assert result.n_fits == 18
    assert result.estimator_fits == 26
    assert result.inference_windows == 0


def test_count_comparison_cost_output_when_each_candidate_is_below_the_threshold():
    """
    Test that explicit candidates that fit 50 estimators or fewer each add
    up above 50: two ForecasterDirect (36 each) and one recursive (6).
    """
    result = count_comparison_cost(
        candidate_configs = [
            ("direct_a", {"forecaster": "ForecasterDirect", "estimator": "Ridge"}),
            ("direct_b", {"forecaster": "ForecasterDirect", "lags": [1, 2]}),
            ("recursive", {"forecaster": "ForecasterRecursive"}),
        ],
        preferred         = "ForecasterRecursive",
        steps             = 6,
        n_fits            = 6,
        n_folds           = 6,
        n_series          = 1,
    )

    assert [c.estimator_fits for c in result.candidates.values()] == [36, 36, 6]
    assert [c.n_fits for c in result.candidates.values()] == [6, 6, 6]
    assert result.n_fits == 18
    assert result.estimator_fits == 78


def test_count_comparison_cost_output_when_stats_without_refit():
    """
    Test that ForecasterStats counts one training and one estimator fit per
    fold even when the strategy trains once (`n_fits` 1).
    """
    result = count_comparison_cost(
        candidate_configs = [("stats", {"forecaster": "ForecasterStats"})],
        preferred         = "ForecasterRecursive",
        steps             = 5,
        n_fits            = 1,
        n_folds           = 51,
        n_series          = 1,
    )

    assert result.candidates["stats"] == CandidateCost(
        forecaster="ForecasterStats", n_fits=51, estimator_fits=51,
        inference_windows=0,
    )
    assert result.n_fits == 51
    assert result.estimator_fits == 51


def test_count_comparison_cost_output_when_foundation_candidates():
    """
    Test that ForecasterFoundation counts no training and no estimator fit,
    only one inference window per series and fold (50 x 41 = 2050), and
    that two foundation candidates add up.
    """
    one = count_comparison_cost(
        candidate_configs = [("foundation", {"forecaster": "ForecasterFoundation"})],
        preferred         = "ForecasterRecursive",
        steps             = 5,
        n_fits            = 1,
        n_folds           = 41,
        n_series          = 50,
    )
    two = count_comparison_cost(
        candidate_configs = [
            ("small", {"forecaster": "ForecasterFoundation"}),
            ("large", {"forecaster": "ForecasterFoundation"}),
        ],
        preferred         = "ForecasterRecursive",
        steps             = 5,
        n_fits            = 1,
        n_folds           = 41,
        n_series          = 50,
    )

    assert one.candidates["foundation"] == CandidateCost(
        forecaster="ForecasterFoundation", n_fits=0, estimator_fits=0,
        inference_windows=2050,
    )
    assert (one.n_fits, one.estimator_fits, one.inference_windows) == (0, 0, 2050)
    assert (two.n_fits, two.estimator_fits, two.inference_windows) == (0, 0, 4100)


def test_count_comparison_cost_keeps_the_order_and_dumps_the_totals():
    """
    Test that `candidates` keeps the input order and that `model_dump()`
    includes the computed totals.
    """
    result = count_comparison_cost(
        candidate_configs = [_BASELINE, _DEFAULTS[1], _DEFAULTS[0]],
        preferred         = "ForecasterRecursive",
        steps             = 2,
        n_fits            = 3,
        n_folds           = 5,
        n_series          = 1,
    )

    assert list(result.candidates) == [
        "Baseline (seasonal naive)", "ForecasterDirect", "ForecasterRecursive"
    ]
    assert result.model_dump() == {
        "n_folds": 5,
        "candidates": {
            "Baseline (seasonal naive)": {
                "forecaster": "ForecasterEquivalentDate", "n_fits": 3,
                "estimator_fits": 0, "inference_windows": 0,
            },
            "ForecasterDirect": {
                "forecaster": "ForecasterDirect", "n_fits": 3,
                "estimator_fits": 6, "inference_windows": 0,
            },
            "ForecasterRecursive": {
                "forecaster": "ForecasterRecursive", "n_fits": 3,
                "estimator_fits": 3, "inference_windows": 0,
            },
        },
        "n_fits": 9,
        "estimator_fits": 9,
        "inference_windows": 0,
    }
