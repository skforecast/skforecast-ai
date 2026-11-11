# Unit test check_comparison_cost

import re

import pytest

from skforecast_ai.exceptions import CostNotConfirmedError, InvalidInputError
from skforecast_ai._utils import check_comparison_cost
from skforecast_ai.schemas import CandidateCost, ComparisonCost

_THRESHOLD = (
    "This comparison is above the threshold of an expensive run (50 estimator "
    "fits or 2000 inference windows), so it needs a confirmation and nothing "
    "ran. "
)
_WAIT = " It can take substantial amounts of time. If not feasible, "
_REFIT_AND_FOLDS = (
    "an integer `refit` (retrain every n folds), fewer folds (a later "
    "`initial_train_size`, a larger `fold_stride` or `skip_folds`) or "
    "`refit=False` (train once)."
)


def _cost(forecaster, n_fits, estimator_fits, inference_windows=0):
    """Return the CandidateCost of a candidate."""
    return CandidateCost(
        forecaster        = forecaster,
        n_fits            = n_fits,
        estimator_fits    = estimator_fits,
        inference_windows = inference_windows,
    )


def _direct_comparison():
    """Return a comparison of 78 estimator fits in all, in 4 candidates."""
    return ComparisonCost(
        n_folds    = 6,
        candidates = {
            "direct": _cost("ForecasterDirect", 6, 36),
            "recursive": _cost("ForecasterRecursive", 6, 6),
            "Baseline (seasonal naive)": _cost("ForecasterEquivalentDate", 6, 0),
            "direct_2": _cost("ForecasterDirect", 6, 36),
        },
    )


def _foundation_comparison():
    """Return a comparison of 3000 inference windows in two candidates."""
    return ComparisonCost(
        n_folds    = 6,
        candidates = {
            "chronos": _cost("ForecasterFoundation", 0, 0, 1500),
            "moirai": _cost("ForecasterFoundation", 0, 0, 1500),
            "Baseline (seasonal naive)": _cost("ForecasterEquivalentDate", 6, 0),
        },
    )


def _mixed_comparison():
    """Return a comparison above the threshold in both fits and windows."""
    return ComparisonCost(
        n_folds    = 6,
        candidates = {
            "direct": _cost("ForecasterDirect", 6, 60),
            "chronos": _cost("ForecasterFoundation", 0, 0, 1200),
            "moirai": _cost("ForecasterFoundation", 0, 0, 1200),
        },
    )


def test_check_comparison_cost_no_error_when_total_fits_within_threshold():
    """
    Test that nothing is raised when the candidates fit 50 estimators in
    all, the threshold, even though one fits most of them, and that
    `confirm_cost` is not read.
    """
    cost = ComparisonCost(
        n_folds    = 6,
        candidates = {
            "direct": _cost("ForecasterDirect", 6, 42),
            "recursive": _cost("ForecasterRecursive", 6, 8),
        },
    )

    result = check_comparison_cost(
        confirm_cost = False,
        cost         = cost,
        n_fits       = 6,
        steps        = 7,
        n_series     = 1,
    )

    assert result is None


def test_check_comparison_cost_CostNotConfirmedError_when_total_fits_exceed_threshold():
    """
    Test that the error states the total, each candidate with its fits, the
    direct candidates with their trainings and estimators, the baseline
    with 0, and the remedies of a forecaster trained more than once, even
    though no candidate is above the threshold by itself.
    """
    err_msg = re.escape(
        _THRESHOLD
        + "The comparison will fit 78 estimators in all ('direct': 36 "
        "(6 trainings x 6 estimators), 'recursive': 6, 'Baseline (seasonal "
        "naive)': 0, 'direct_2': 36 (6 trainings x 6 estimators))."
        + _WAIT
        + "compare fewer candidates or use "
        + _REFIT_AND_FOLDS
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$"):
        check_comparison_cost(
            confirm_cost = False,
            cost         = _direct_comparison(),
            n_fits       = 6,
            steps        = 6,
            n_series     = 1,
        )


def test_check_comparison_cost_error_attributes_when_total_fits_exceed_threshold():
    """
    Test that the error carries the code `invalid_argument`, the field
    `confirm_cost`, the hint, the figure (the estimator fits in all), the
    totals of the comparison as `cost`, the description without the
    remedies and the cost of each candidate as the object passed.
    """
    cost = _direct_comparison()

    with pytest.raises(CostNotConfirmedError) as exc_info:
        check_comparison_cost(
            confirm_cost = False,
            cost         = cost,
            n_fits       = 6,
            steps        = 6,
            n_series     = 1,
        )

    error = exc_info.value
    assert isinstance(error, InvalidInputError)
    assert error.code == "invalid_argument"
    assert error.field == "confirm_cost"
    assert error.hint == "Pass `confirm_cost=True` to run it as it is."
    assert error.figure == 78
    assert error.cost == {
        "n_folds": 6, "n_fits": 24, "estimator_fits": 78, "inference_windows": 0
    }
    assert error.description == (
        "The comparison will fit 78 estimators in all ('direct': 36 "
        "(6 trainings x 6 estimators), 'recursive': 6, 'Baseline (seasonal "
        "naive)': 0, 'direct_2': 36 (6 trainings x 6 estimators))."
    )
    assert error.comparison_cost is cost


def test_check_comparison_cost_message_when_candidates_are_stats_and_baseline():
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

    err_msg = re.escape(
        _THRESHOLD
        + "The comparison will fit 51 estimators in all ('stats': 51, "
        "'Baseline (seasonal naive)': 0)."
        + _WAIT
        + "compare fewer candidates or use fewer folds (a later "
        "`initial_train_size` or a larger `fold_stride`)."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$"):
        check_comparison_cost(
            confirm_cost = False,
            cost         = cost,
            n_fits       = 1,
            steps        = 5,
            n_series     = 1,
        )


def test_check_comparison_cost_message_without_skip_folds_when_stats_has_no_fits():
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

    err_msg = re.escape(
        _THRESHOLD
        + "The comparison will fit 60 estimators in all ('recursive': 60, "
        "'stats': 0)."
        + _WAIT
        + "compare fewer candidates or use an integer `refit` (retrain every "
        "n folds), fewer folds (a later `initial_train_size` or a larger "
        "`fold_stride`) or `refit=False` (train once)."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$"):
        check_comparison_cost(
            confirm_cost = False,
            cost         = cost,
            n_fits       = 6,
            steps        = 5,
            n_series     = 1,
        )


@pytest.mark.parametrize("confirm_cost", [True, 78], ids=["true", "figure"])
def test_check_comparison_cost_no_error_when_confirm_cost_confirms_the_cost(
    confirm_cost,
):
    """
    Test that nothing is raised above the threshold when `confirm_cost` is
    True or the figure of the cost (78 estimator fits in all).
    """
    result = check_comparison_cost(
        confirm_cost = confirm_cost,
        cost         = _direct_comparison(),
        n_fits       = 6,
        steps        = 6,
        n_series     = 1,
    )

    assert result is None


def test_check_comparison_cost_CostNotConfirmedError_when_another_figure():
    """
    Test that a figure other than the total (77 for 78 estimator fits)
    raises the error with a closing sentence that says the strategy or the
    candidates changed since that number was given.
    """
    err_msg = re.escape(
        "`confirm_cost=77` does not confirm it: the figure of this cost is "
        "78, so the strategy or the candidates changed since that number was "
        "given."
    )
    with pytest.raises(CostNotConfirmedError, match=f"{err_msg}$") as exc_info:
        check_comparison_cost(
            confirm_cost = 77,
            cost         = _direct_comparison(),
            n_fits       = 6,
            steps        = 6,
            n_series     = 1,
        )

    assert exc_info.value.figure == 78


@pytest.mark.parametrize(
    "not_counted, sentence",
    [
        (
            ["broken"],
            " 'broken' is not counted: its plan cannot be built, so it runs "
            "nothing.",
        ),
        (
            ["broken", "worse"],
            " 'broken' and 'worse' are not counted: their plans cannot be "
            "built, so they run nothing.",
        ),
        (
            ["broken", "worse", "worst"],
            " 'broken', 'worse' and 'worst' are not counted: their plans "
            "cannot be built, so they run nothing.",
        ),
    ],
    ids=["one", "two", "three"],
)
def test_check_comparison_cost_message_when_candidates_are_not_counted(
    not_counted, sentence
):
    """
    Test that the candidates whose plan cannot be built are named after the
    cost, in the singular for one and in the plural for more, before the
    wait, and that the description carries the same sentence.
    """
    cost = ComparisonCost(
        n_folds    = 6,
        candidates = {"recursive": _cost("ForecasterRecursive", 60, 60)},
    )

    err_msg = re.escape(
        _THRESHOLD
        + "The comparison will fit 60 estimators in all ('recursive': 60)."
        + sentence
        + _WAIT
        + "compare fewer candidates or use "
        + _REFIT_AND_FOLDS
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        check_comparison_cost(
            confirm_cost = False,
            cost         = cost,
            n_fits       = 6,
            steps        = 5,
            n_series     = 1,
            not_counted  = not_counted,
        )

    assert exc_info.value.description == (
        "The comparison will fit 60 estimators in all ('recursive': 60)."
        + sentence
    )


def test_check_comparison_cost_CostNotConfirmedError_when_only_windows_exceed():
    """
    Test that a comparison above the threshold only in inference windows
    (two foundation candidates, 3000 in all, no estimator fit) raises the
    error with the windows as the figure, a description from the inference
    message with the 2 foundation candidates (the baseline is not one), and
    the remedies of a foundation model: fewer folds and fewer series.
    """
    cost = _foundation_comparison()

    err_msg = re.escape(
        _THRESHOLD
        + "ForecasterFoundation will forecast up to 3000 inference windows "
        "(250 series x 6 folds x 2 candidates)."
        + _WAIT
        + "compare fewer candidates or use fewer folds (a later "
        "`initial_train_size`, a larger `fold_stride` or `skip_folds`) or "
        "fewer series."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        check_comparison_cost(
            confirm_cost = False,
            cost         = cost,
            n_fits       = 1,
            steps        = 5,
            n_series     = 250,
        )

    error = exc_info.value
    assert error.figure == 3000
    assert error.cost == {
        "n_folds": 6, "n_fits": 6, "estimator_fits": 0, "inference_windows": 3000
    }
    assert error.description == (
        "ForecasterFoundation will forecast up to 3000 inference windows "
        "(250 series x 6 folds x 2 candidates)."
    )
    assert error.comparison_cost is cost


@pytest.mark.parametrize("confirm_cost", [True, 3000], ids=["true", "figure"])
def test_check_comparison_cost_no_error_when_confirm_cost_confirms_the_windows(
    confirm_cost,
):
    """
    Test that nothing is raised for a comparison above the threshold only
    in inference windows when `confirm_cost` is True or the windows in all.
    """
    result = check_comparison_cost(
        confirm_cost = confirm_cost,
        cost         = _foundation_comparison(),
        n_fits       = 1,
        steps        = 5,
        n_series     = 250,
    )

    assert result is None


def test_check_comparison_cost_CostNotConfirmedError_when_both_thresholds_exceed():
    """
    Test that a comparison above the threshold in estimator fits (60) and
    in inference windows (2400) joins both descriptions with ' and ', takes
    the estimator fits as the figure, and adds the remedies of both: those
    of the fits and fewer series.
    """
    cost = _mixed_comparison()

    err_msg = re.escape(
        _THRESHOLD
        + "The comparison will fit 60 estimators in all ('direct': 60 "
        "(6 trainings x 10 estimators), 'chronos': 0, 'moirai': 0) and "
        "ForecasterFoundation will forecast up to 2400 inference windows "
        "(200 series x 6 folds x 2 candidates)."
        + _WAIT
        + "compare fewer candidates or use an integer `refit` (retrain every "
        "n folds), fewer folds (a later `initial_train_size`, a larger "
        "`fold_stride` or `skip_folds`), `refit=False` (train once) or fewer "
        "series."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        check_comparison_cost(
            confirm_cost = False,
            cost         = cost,
            n_fits       = 6,
            steps        = 10,
            n_series     = 200,
        )

    error = exc_info.value
    assert error.figure == 60
    assert error.cost == {
        "n_folds": 6, "n_fits": 6, "estimator_fits": 60, "inference_windows": 2400
    }


def test_check_comparison_cost_CostNotConfirmedError_when_figure_is_the_windows():
    """
    Test that for a comparison above both thresholds the windows (2400) do
    not confirm it, since the figure is the estimator fits (60), and that
    the figure does.
    """
    kwargs = dict(
        cost     = _mixed_comparison(),
        n_fits   = 6,
        steps    = 10,
        n_series = 200,
    )

    err_msg = re.escape(
        "`confirm_cost=2400` does not confirm it: the figure of this cost is "
        "60, so the strategy or the candidates changed since that number was "
        "given."
    )
    with pytest.raises(CostNotConfirmedError, match=f"{err_msg}$"):
        check_comparison_cost(confirm_cost=2400, **kwargs)
    result = check_comparison_cost(confirm_cost=60, **kwargs)

    assert result is None
