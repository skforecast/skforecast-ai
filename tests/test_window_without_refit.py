# Unit test window_without_refit

import pytest

from skforecast_ai._utils import window_without_refit


@pytest.mark.parametrize("fixed_train_size", [True, False])
@pytest.mark.parametrize("refit", [False, 0, None])
def test_window_without_refit_output_is_true_when_trained_once(
    refit, fixed_train_size
):
    """
    Test that a `fixed_train_size` passed with a `refit` of False, 0 or None
    (its default, False) is reported, since the forecaster is trained once.
    """
    assert window_without_refit(fixed_train_size, refit, "ForecasterRecursive")


@pytest.mark.parametrize(
    "fixed_train_size, refit, forecaster",
    [
        (None, False, "ForecasterRecursive"),
        (None, None, "ForecasterDirect"),
        (True, True, "ForecasterRecursive"),
        (False, 1, "ForecasterRecursive"),
        (True, 3, "ForecasterDirect"),
        (True, False, "ForecasterStats"),
        (False, None, "ForecasterStats"),
        (True, 0, "ForecasterStats"),
    ],
    ids=[
        "not_passed", "not_passed_refit_none", "refit_true", "refit_1",
        "refit_3", "stats_refit_false", "stats_refit_none", "stats_refit_0",
    ],
)
def test_window_without_refit_output_is_false_when_window_applies(
    fixed_train_size, refit, forecaster
):
    """
    Test that False is returned when `fixed_train_size` is not passed, when
    the forecaster is refitted (True or a positive integer), and for
    ForecasterStats, which skforecast refits in every fold.
    """
    assert not window_without_refit(fixed_train_size, refit, forecaster)


def test_window_without_refit_output_is_bool():
    """
    Test that the result is a bool in both outcomes.
    """
    assert window_without_refit(True, False, "ForecasterRecursive") is True
    assert window_without_refit(True, True, "ForecasterRecursive") is False
