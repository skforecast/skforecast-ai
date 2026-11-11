# Unit test check_backtest_cost

import re

import pytest

from skforecast_ai._utils import check_backtest_cost
from skforecast_ai.exceptions import CostNotConfirmedError

_PREFIX = (
    "This backtest is above the threshold of an expensive run (50 estimator "
    "fits or {windows} inference windows), so it needs a confirmation and "
    "nothing ran. "
)
_WAIT = " It can take substantial amounts of time. If not feasible, "


def test_check_backtest_cost_CostNotConfirmedError_when_direct_fits_exceed_threshold():
    """
    Test that a ForecasterDirect refitted in each of 6 folds, which fits 10
    estimators per training (60 in all), raises the error with the
    trainings x estimators breakdown and the remedies of a forecaster
    trained more than once, `skip_folds` included.
    """
    err_msg = re.escape(
        _PREFIX.format(windows=2000)
        + "ForecasterDirect will be fit 60 times (6 trainings x 10 "
        "estimators)."
        + _WAIT
        + "use an integer `refit` (retrain every n folds), fewer folds (a "
        "later `initial_train_size`, a larger `fold_stride` or `skip_folds`) "
        "or `refit=False` (train once)."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        check_backtest_cost(
            confirm_cost = False,
            cv_config    = {"n_folds": 6, "n_fits": 6},
            forecaster   = "ForecasterDirect",
            steps        = 10,
            n_series     = 1,
        )

    error = exc_info.value
    assert error.figure == 60
    assert error.cost == {
        "n_folds": 6, "n_fits": 6, "estimator_fits": 60, "inference_windows": 0
    }
    assert error.description == (
        "ForecasterDirect will be fit 60 times (6 trainings x 10 estimators)."
    )
    assert error.comparison_cost is None


def test_check_backtest_cost_CostNotConfirmedError_when_stats_fits_exceed_threshold():
    """
    Test that a ForecasterStats, refitted in every fold (60 folds, 60 fits),
    raises the error without a breakdown and with fewer folds as the only
    remedy, without `skip_folds`, which skforecast rejects for it.
    """
    err_msg = re.escape(
        _PREFIX.format(windows=2000)
        + "ForecasterStats will be fit 60 times."
        + _WAIT
        + "use fewer folds (a later `initial_train_size` or a larger "
        "`fold_stride`)."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        check_backtest_cost(
            confirm_cost = False,
            cv_config    = {"n_folds": 60, "n_fits": 60},
            forecaster   = "ForecasterStats",
            steps        = 5,
            n_series     = 1,
        )

    error = exc_info.value
    assert error.figure == 60
    assert error.cost == {
        "n_folds": 60, "n_fits": 60, "estimator_fits": 60, "inference_windows": 0
    }


def test_check_backtest_cost_CostNotConfirmedError_when_foundation_windows_exceed(
    monkeypatch,
):
    """
    Test that a ForecasterFoundation, which fits nothing, takes its
    inference windows (3 series x 6 folds = 18, above the lowered threshold
    of 10) as the figure, describes them, and names as remedies fewer folds
    (with `skip_folds`) and fewer series.
    """
    monkeypatch.setattr("skforecast_ai._utils.LONG_INFERENCE_WINDOWS", 10)

    err_msg = re.escape(
        _PREFIX.format(windows=10)
        + "ForecasterFoundation will forecast up to 18 inference windows "
        "(3 series x 6 folds)."
        + _WAIT
        + "use fewer folds (a later `initial_train_size`, a larger "
        "`fold_stride` or `skip_folds`) or fewer series."
    )
    with pytest.raises(CostNotConfirmedError, match=f"^{err_msg}$") as exc_info:
        check_backtest_cost(
            confirm_cost = False,
            cv_config    = {"n_folds": 6, "n_fits": 0},
            forecaster   = "ForecasterFoundation",
            steps        = 5,
            n_series     = 3,
        )

    error = exc_info.value
    assert error.figure == 18
    assert error.cost == {
        "n_folds": 6, "n_fits": 0, "estimator_fits": 0, "inference_windows": 18
    }
    assert error.description == (
        "ForecasterFoundation will forecast up to 18 inference windows "
        "(3 series x 6 folds)."
    )


@pytest.mark.parametrize(
    "confirm_cost, cv_config, forecaster, n_series",
    [
        (False, {"n_folds": 5, "n_fits": 5}, "ForecasterDirect", 1),
        (False, {"n_folds": 50, "n_fits": 50}, "ForecasterStats", 1),
        (False, {"n_folds": 50, "n_fits": 50}, "ForecasterRecursive", 1),
        (False, {"n_folds": 8, "n_fits": 0}, "ForecasterFoundation", 250),
        (7, {"n_folds": 8, "n_fits": 0}, "ForecasterFoundation", 250),
        (False, {"n_folds": 80, "n_fits": 0}, "ForecasterEquivalentDate", 250),
    ],
    ids=[
        "direct_50_fits", "stats_50_fits", "recursive_50_fits",
        "foundation_2000_windows", "foundation_wrong_int", "baseline_no_cost",
    ],
)
def test_check_backtest_cost_no_error_when_cost_at_threshold(
    confirm_cost, cv_config, forecaster, n_series
):
    """
    Test that a backtest at the thresholds (50 estimator fits, 2000
    inference windows) or of a forecaster that costs nothing needs no
    confirmation: `confirm_cost` is not read and None is returned.
    """
    result = check_backtest_cost(
        confirm_cost = confirm_cost,
        cv_config    = cv_config,
        forecaster   = forecaster,
        steps        = 10 if forecaster == "ForecasterDirect" else 5,
        n_series     = n_series,
    )

    assert result is None


@pytest.mark.parametrize("confirm_cost", [True, 60], ids=["true", "figure"])
def test_check_backtest_cost_no_error_when_confirm_cost_confirms_the_cost(
    confirm_cost,
):
    """
    Test that a backtest above the threshold returns None when
    `confirm_cost` is True or the figure of its cost (60 estimator fits).
    """
    result = check_backtest_cost(
        confirm_cost = confirm_cost,
        cv_config    = {"n_folds": 6, "n_fits": 6},
        forecaster   = "ForecasterDirect",
        steps        = 10,
        n_series     = 1,
    )

    assert result is None


def test_check_backtest_cost_CostNotConfirmedError_when_confirm_cost_is_another_int():
    """
    Test that a number other than the figure of the cost (59 for 60
    estimator fits) raises the error with the sentence that says the
    strategy or the plan changed since that number was given.
    """
    err_msg = re.escape(
        "`confirm_cost=59` does not confirm it: the figure of this cost is "
        "60, so the strategy or the plan changed since that number was given."
    )
    with pytest.raises(CostNotConfirmedError, match=f"{err_msg}$"):
        check_backtest_cost(
            confirm_cost = 59,
            cv_config    = {"n_folds": 6, "n_fits": 6},
            forecaster   = "ForecasterDirect",
            steps        = 10,
            n_series     = 1,
        )
