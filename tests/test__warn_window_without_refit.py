# Unit test _warn_window_without_refit

import re
import warnings

import pytest
from skforecast.exceptions import IgnoredArgumentWarning

from skforecast_ai._utils import _warn_window_without_refit


@pytest.mark.parametrize("fixed_train_size", [True, False])
@pytest.mark.parametrize("refit", [False, 0])
def test_warn_window_without_refit_IgnoredArgumentWarning_when_trained_once(
    refit, fixed_train_size
):
    """
    Test that a `fixed_train_size` passed for a forecaster that is trained
    once (`refit` False or 0) warns that it has no effect.
    """
    warn_msg = re.escape(
        f"`fixed_train_size={fixed_train_size!r}` has no effect: with "
        f"`refit={refit!r}` the forecaster is trained once, on a single "
        f"training window. Pass `refit=True` (or an integer) to refit it, or "
        f"omit `fixed_train_size` to avoid this warning."
    )
    with pytest.warns(IgnoredArgumentWarning, match=warn_msg):
        _warn_window_without_refit(fixed_train_size, refit, "ForecasterRecursive")


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
def test_warn_window_without_refit_no_warning_when_window_applies(
    fixed_train_size, refit, forecaster
):
    """
    Test that nothing is warned when `fixed_train_size` is not passed, when
    the forecaster is refitted, or for ForecasterStats, which is always
    refitted.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = _warn_window_without_refit(fixed_train_size, refit, forecaster)

    assert result is None
