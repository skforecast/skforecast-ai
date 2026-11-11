# Unit test stats_skip_folds_exclusion execution/comparison

import pytest

from skforecast_ai.execution.comparison import stats_skip_folds_exclusion

from tests.fixtures_compare import profile_h2o, profile_sales


@pytest.mark.parametrize(
    "skip_folds, shown",
    [(2, "2"), ([1, 3], "[1, 3]"), ([], "[]")],
    ids=["integer", "list", "empty_list"],
)
def test_stats_skip_folds_exclusion_output_when_stats_is_a_candidate(
    skip_folds, shown
):
    """
    Test that ForecasterStats is excluded, with a note that names the
    `skip_folds` of the strategy, when the profile lists it as a candidate
    and the strategy has any `skip_folds` other than None, an empty list
    included.
    """
    excluded, note = stats_skip_folds_exclusion(profile_h2o, skip_folds)

    assert excluded == frozenset({"ForecasterStats"})
    assert note == (
        f"ForecasterStats left out: the strategy has `skip_folds={shown}`, "
        f"which skforecast does not allow for it (it refits ForecasterStats "
        f"in every fold)."
    )


@pytest.mark.parametrize(
    "profile, skip_folds",
    [(profile_h2o, None), (profile_sales, 2), (profile_sales, None)],
    ids=["no_skip_folds", "stats_not_a_candidate", "neither"],
)
def test_stats_skip_folds_exclusion_output_when_nothing_to_leave_out(
    profile, skip_folds
):
    """
    Test that nothing is excluded, and there is no note, when the strategy
    does not skip folds or the profile does not list ForecasterStats.
    """
    assert stats_skip_folds_exclusion(profile, skip_folds) == (frozenset(), None)
