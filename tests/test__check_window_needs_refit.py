# Unit test _check_window_needs_refit

import re

import pytest

from skforecast_ai._utils import _check_window_needs_refit
from skforecast_ai.exceptions import InvalidInputError


@pytest.mark.parametrize("fixed_train_size", [True, False])
@pytest.mark.parametrize("refit", [False, 0])
def test_check_window_needs_refit_InvalidInputError_when_trained_once(
    refit, fixed_train_size
):
    """
    Test that a `fixed_train_size` passed for a forecaster that is trained
    once (`refit` False or 0) raises with the field 'fixed_train_size'.
    """
    err_msg = re.escape(
        f"`fixed_train_size={fixed_train_size!r}` only applies when the "
        f"forecaster is refitted, and with `refit={refit!r}` it is trained "
        f"once. Pass `refit=True` (or an integer) to refit it, or omit "
        f"`fixed_train_size`."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        _check_window_needs_refit(fixed_train_size, refit, "ForecasterRecursive")

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "fixed_train_size"


@pytest.mark.parametrize(
    "fixed_train_size, refit, forecaster",
    [
        (None, False, "ForecasterRecursive"),
        (True, True, "ForecasterRecursive"),
        (False, 2, "ForecasterDirect"),
        (True, False, "ForecasterStats"),
        (False, 0, "ForecasterStats"),
    ],
    ids=[
        "not passed", "refit True", "integer refit", "stats, no refit",
        "stats, refit 0",
    ],
)
def test_check_window_needs_refit_output_when_window_applies(
    fixed_train_size, refit, forecaster
):
    """
    Test that nothing is raised when `fixed_train_size` is not passed, when
    the forecaster is refitted, or for ForecasterStats, which is always
    refitted.
    """
    assert _check_window_needs_refit(fixed_train_size, refit, forecaster) is None
