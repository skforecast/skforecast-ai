# Unit test check_cost_confirmed

import re

import numpy as np
import pytest

from skforecast_ai._utils import check_cost_confirmed
from skforecast_ai.exceptions import CostNotConfirmedError, InvalidInputError
from skforecast_ai.schemas import CandidateCost, ComparisonCost

_PREFIX = (
    "is above the threshold of an expensive run (50 estimator fits or 2000 "
    "inference windows), so it needs a confirmation and nothing ran. "
)
_FITS = {"n_folds": 6, "n_fits": 6, "estimator_fits": 60, "inference_windows": 0}
_WINDOWS = {"n_folds": 6, "n_fits": 0, "estimator_fits": 0, "inference_windows": 3000}
_BOTH = {"n_folds": 6, "n_fits": 6, "estimator_fits": 60, "inference_windows": 2400}
_AT_THRESHOLD = {
    "n_folds": 6, "n_fits": 6, "estimator_fits": 50, "inference_windows": 2000
}
_DESCRIPTION = "ForecasterRecursive will be fit 60 times."
_REMEDIES = "use `refit=False` (train once)"


@pytest.mark.parametrize("run", ["backtest", "comparison"])
@pytest.mark.parametrize("confirm_cost", [False, 7], ids=["false", "wrong_int"])
def test_check_cost_confirmed_no_error_when_cost_within_threshold(run, confirm_cost):
    """
    Test that a run at the thresholds (50 estimator fits and 2000 inference
    windows) needs no confirmation: `confirm_cost` is not read, so False and
    a number that is not the figure of the cost return None.
    """
    result = check_cost_confirmed(
        confirm_cost = confirm_cost,
        run          = run,
        cost         = _AT_THRESHOLD,
        description  = _DESCRIPTION,
        remedies     = _REMEDIES,
    )

    assert result is None


@pytest.mark.parametrize("run", ["backtest", "comparison"])
@pytest.mark.parametrize(
    "cost, confirm_cost",
    [
        (_FITS, True),
        (_FITS, 60),
        (_FITS, np.int64(60)),
        (_WINDOWS, True),
        (_WINDOWS, 3000),
        (_BOTH, True),
        (_BOTH, 60),
    ],
    ids=[
        "fits_true", "fits_figure", "fits_numpy_figure", "windows_true",
        "windows_figure", "both_true", "both_figure",
    ],
)
def test_check_cost_confirmed_no_error_when_confirm_cost_confirms_the_cost(
    run, cost, confirm_cost
):
    """
    Test that a run above a threshold needs True or the figure of its cost
    and that either returns None: the estimator fits when above 50, the
    inference windows when only those are above 2000.
    """
    result = check_cost_confirmed(
        confirm_cost = confirm_cost,
        run          = run,
        cost         = cost,
        description  = _DESCRIPTION,
        remedies     = _REMEDIES,
    )

    assert result is None


@pytest.mark.parametrize("run", ["backtest", "comparison"])
def test_check_cost_confirmed_CostNotConfirmedError_when_confirm_cost_is_false(run):
    """
    Test that a run above the threshold with `confirm_cost=False` raises
    CostNotConfirmedError with the message that names the run, states the
    threshold, the description, the wait and the remedies, and no sentence
    about another figure.
    """
    err_msg = re.escape(
        f"This {run} "
        + _PREFIX
        + "ForecasterRecursive will be fit 60 times. It can take substantial "
        "amounts of time. If not feasible, use `refit=False` (train once)."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$"):
        check_cost_confirmed(
            confirm_cost = False,
            run          = run,
            cost         = _FITS,
            description  = _DESCRIPTION,
            remedies     = _REMEDIES,
        )


def test_check_cost_confirmed_error_attributes_when_comparison_cost_is_given():
    """
    Test that the error is an InvalidInputError with the code
    `invalid_argument`, the field `confirm_cost`, the hint that says how to
    run it as it is, the figure, the cost dict and the description passed,
    and the comparison cost as the object passed.
    """
    comparison_cost = ComparisonCost(
        n_folds    = 6,
        candidates = {
            "recursive": CandidateCost(
                forecaster        = "ForecasterRecursive",
                n_fits            = 6,
                estimator_fits    = 60,
                inference_windows = 0,
            ),
        },
    )

    with pytest.raises(CostNotConfirmedError) as exc_info:
        check_cost_confirmed(
            confirm_cost    = False,
            run             = "comparison",
            cost            = _FITS,
            description     = _DESCRIPTION,
            remedies        = _REMEDIES,
            comparison_cost = comparison_cost,
        )

    error = exc_info.value
    assert isinstance(error, InvalidInputError)
    assert error.code == "invalid_argument"
    assert error.field == "confirm_cost"
    assert error.hint == "Pass `confirm_cost=True` to run it as it is."
    assert error.figure == 60
    assert error.cost == _FITS
    assert error.description == "ForecasterRecursive will be fit 60 times."
    assert error.comparison_cost is comparison_cost


def test_check_cost_confirmed_comparison_cost_is_none_when_not_given():
    """
    Test that the error has no comparison cost when none is passed, as for
    a backtest.
    """
    with pytest.raises(CostNotConfirmedError) as exc_info:
        check_cost_confirmed(
            confirm_cost = False,
            run          = "backtest",
            cost         = _FITS,
            description  = _DESCRIPTION,
            remedies     = _REMEDIES,
        )

    assert exc_info.value.comparison_cost is None


@pytest.mark.parametrize(
    "run, changed",
    [
        ("backtest", "the strategy or the plan"),
        ("comparison", "the strategy or the candidates"),
    ],
)
def test_check_cost_confirmed_CostNotConfirmedError_when_confirm_cost_is_another_int(
    run, changed
):
    """
    Test that a number other than the figure of the cost (59 for 60
    estimator fits) raises the error with a last sentence that names the
    figure and what changed since that number was given: the strategy or
    the plan of a backtest, the strategy or the candidates of a comparison.
    """
    err_msg = re.escape(
        f"This {run} "
        + _PREFIX
        + "ForecasterRecursive will be fit 60 times. It can take substantial "
        "amounts of time. If not feasible, use `refit=False` (train once). "
        "`confirm_cost=59` does not confirm it: the figure of this cost is "
        f"60, so {changed} changed since that number was given."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        check_cost_confirmed(
            confirm_cost = 59,
            run          = run,
            cost         = _FITS,
            description  = _DESCRIPTION,
            remedies     = _REMEDIES,
        )

    assert exc_info.value.figure == 60


@pytest.mark.parametrize(
    "cost, confirm_cost, figure",
    [
        (_WINDOWS, 60, 3000),
        (_WINDOWS, False, 3000),
        (_BOTH, 2400, 60),
        (_BOTH, 0, 60),
    ],
    ids=["windows_other_int", "windows_false", "both_windows", "both_zero"],
)
def test_check_cost_confirmed_figure_when_confirm_cost_does_not_confirm(
    cost, confirm_cost, figure
):
    """
    Test that the figure of the error is the inference windows when only
    those are above the threshold and the estimator fits when both are, so
    the windows of a run above both do not confirm it.
    """
    with pytest.raises(CostNotConfirmedError) as exc_info:
        check_cost_confirmed(
            confirm_cost = confirm_cost,
            run          = "backtest",
            cost         = cost,
            description  = _DESCRIPTION,
            remedies     = _REMEDIES,
        )

    assert exc_info.value.figure == figure


def test_check_cost_confirmed_message_without_remedies_when_remedies_is_empty():
    """
    Test that the "If not feasible" sentence is left out when nothing lowers
    the cost (`remedies` is empty), with and without a figure other than
    that of the cost.
    """
    err_msg = re.escape(
        "This backtest "
        + _PREFIX
        + "ForecasterRecursive will be fit 60 times. It can take substantial "
        "amounts of time."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        check_cost_confirmed(
            confirm_cost = False,
            run          = "backtest",
            cost         = _FITS,
            description  = _DESCRIPTION,
            remedies     = "",
        )
    with pytest.raises(CostNotConfirmedError) as exc_info_int:
        check_cost_confirmed(
            confirm_cost = 59,
            run          = "backtest",
            cost         = _FITS,
            description  = _DESCRIPTION,
            remedies     = "",
        )

    assert "If not feasible" not in str(exc_info.value)
    assert str(exc_info_int.value) == (
        "This backtest "
        + _PREFIX
        + "ForecasterRecursive will be fit 60 times. It can take substantial "
        "amounts of time. `confirm_cost=59` does not confirm it: the figure "
        "of this cost is 60, so the strategy or the plan changed since that "
        "number was given."
    )
