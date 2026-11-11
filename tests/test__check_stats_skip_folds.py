# Unit test _check_stats_skip_folds

import re

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai._utils import _check_stats_skip_folds
from skforecast_ai.exceptions import InvalidInputError

from tests.tests_rendering.fixtures_rendering import (
    plan_single_recursive_no_exog,
    plan_statistical,
)


@pytest.mark.parametrize(
    "skip_folds, shown",
    [(2, "2"), ([1], "[1]"), ([], "[]")],
    ids=["integer", "list", "empty_list"],
)
def test_check_stats_skip_folds_InvalidInputError_when_stats_skips_folds(
    skip_folds, shown
):
    """
    Test that a ForecasterStats plan with a strategy that skips folds, an
    empty list included, raises InvalidInputError with the field 'cv' and the
    hint about running fewer folds.
    """
    cv = TimeSeriesFold(
        steps=5, initial_train_size=70, skip_folds=skip_folds, verbose=False
    )

    err_msg = re.escape(
        f"`skip_folds={shown}` is not allowed for ForecasterStats: skforecast "
        f"refits it in every fold and rejects any `skip_folds`, an empty "
        f"list included. Use a strategy without `skip_folds`, or another "
        f"forecaster."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        _check_stats_skip_folds(plan_statistical, cv)

    assert exc_info.value.field == "cv"
    assert exc_info.value.hint == (
        "For fewer folds, use a later `initial_train_size` or a larger "
        "`fold_stride`."
    )


@pytest.mark.parametrize(
    "plan, skip_folds",
    [
        (plan_statistical, None),
        (plan_single_recursive_no_exog, 2),
        (plan_single_recursive_no_exog, None),
    ],
    ids=["stats_without_skip", "recursive_with_skip", "recursive_without_skip"],
)
def test_check_stats_skip_folds_no_error_when_it_can_run(plan, skip_folds):
    """
    Test that nothing is raised when the plan is not ForecasterStats or the
    strategy does not skip folds.
    """
    cv = TimeSeriesFold(
        steps=5, initial_train_size=70, skip_folds=skip_folds, verbose=False
    )

    assert _check_stats_skip_folds(plan, cv) is None
