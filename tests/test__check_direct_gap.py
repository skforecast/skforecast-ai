# Unit test _check_direct_gap

import re

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai._utils import _check_direct_gap
from skforecast_ai.exceptions import InvalidInputError

from tests.tests_rendering.fixtures_rendering import (
    plan_multivariate,
    plan_single_direct,
    plan_single_recursive_no_exog,
)


@pytest.mark.parametrize(
    "plan, forecaster",
    [
        (plan_single_direct, "ForecasterDirect"),
        (plan_multivariate, "ForecasterDirectMultiVariate"),
    ],
    ids=["direct", "multivariate"],
)
def test_check_direct_gap_InvalidInputError_when_direct_forecaster_with_gap(
    plan, forecaster
):
    """
    Test that a direct forecaster with a strategy whose gap is greater than 0
    raises InvalidInputError with the field 'cv'.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=70, gap=3, verbose=False)

    err_msg = re.escape(
        f"{forecaster} is trained to predict 5 steps, and with `gap=3` each "
        f"fold needs steps + gap = 8 steps ahead, so skforecast would fail. "
        f"Use a strategy without gap, or a recursive forecaster."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        _check_direct_gap(plan, cv)

    assert exc_info.value.field == "cv"


@pytest.mark.parametrize(
    "plan, gap",
    [
        (plan_single_direct, 0),
        (plan_multivariate, 0),
        (plan_single_recursive_no_exog, 3),
    ],
    ids=["direct_without_gap", "multivariate_without_gap", "recursive_with_gap"],
)
def test_check_direct_gap_output_when_plan_can_run(plan, gap):
    """
    Test that a direct forecaster without gap, or a recursive one with a
    gap, passes.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=70, gap=gap, verbose=False)

    assert _check_direct_gap(plan, cv) is None
