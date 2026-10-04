# Unit test _warn_direct_gap

import re

import pytest

from skforecast_ai._utils import _warn_direct_gap

from tests.tests_rendering.fixtures_rendering import (
    plan_multivariate,
    plan_single_direct,
    plan_single_recursive_no_exog,
)


def _create_strategy(plan, gap):
    """Stand in for `create_cv()`, the caller of `_warn_direct_gap`."""
    _warn_direct_gap(plan, gap)


@pytest.mark.parametrize(
    "plan, forecaster",
    [
        (plan_single_direct, "ForecasterDirect"),
        (plan_multivariate, "ForecasterDirectMultiVariate"),
    ],
    ids=["direct", "multivariate"],
)
def test_warn_direct_gap_UserWarning_when_direct_forecaster_with_gap(
    plan, forecaster
):
    """
    Test that a strategy with a gap for a direct forecaster warns that its
    backtest raises, attributed to the caller of the caller of the helper
    (the caller of `create_cv()`).
    """
    warn_msg = re.escape(
        f"{forecaster} is trained to predict 5 steps, and with `gap=2` each "
        f"fold needs steps + gap = 7 steps ahead, so skforecast would fail: "
        f"`backtest()` and `backtest_code()` of this plan with this strategy "
        f"raise. The strategy can still serve the candidates of `compare()` "
        f"that are not direct; use a strategy without gap to backtest this "
        f"plan."
    )
    with pytest.warns(UserWarning, match=warn_msg) as record:
        _create_strategy(plan, 2)

    assert record[0].filename == __file__


@pytest.mark.parametrize(
    "plan, gap",
    [
        (plan_single_direct, 0),
        (plan_single_direct, None),
        (plan_multivariate, 0),
        (plan_single_recursive_no_exog, 2),
    ],
    ids=["direct_gap_0", "direct_gap_None", "multivariate_gap_0", "recursive_gap"],
)
def test_warn_direct_gap_no_warning_when_plan_can_run(plan, gap):
    """
    Test that there is no warning without a gap or for a recursive
    forecaster (warnings are errors in this suite).
    """
    _create_strategy(plan, gap)
