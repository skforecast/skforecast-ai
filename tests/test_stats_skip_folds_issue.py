# Unit test stats_skip_folds_issue

import pytest

from skforecast_ai._utils import stats_skip_folds_issue


@pytest.mark.parametrize(
    "skip_folds, shown",
    [(2, "2"), ([1, 3], "[1, 3]"), ([], "[]")],
    ids=["integer", "list", "empty_list"],
)
def test_stats_skip_folds_issue_output_when_forecaster_stats_skips_folds(
    skip_folds, shown
):
    """
    Test that a ForecasterStats plan with any `skip_folds` other than None,
    an empty list included, gets the text that says why it cannot run.
    """
    result = stats_skip_folds_issue("ForecasterStats", skip_folds)

    assert result == (
        f"`skip_folds={shown}` is not allowed for ForecasterStats: skforecast "
        f"refits it in every fold and rejects any `skip_folds`, an empty "
        f"list included"
    )


@pytest.mark.parametrize(
    "forecaster, skip_folds",
    [
        ("ForecasterStats", None),
        ("ForecasterRecursive", 2),
        ("ForecasterDirect", [1]),
        ("ForecasterFoundation", []),
    ],
    ids=["stats_without_skip", "recursive", "direct", "foundation"],
)
def test_stats_skip_folds_issue_output_is_none_when_it_can_run(
    forecaster, skip_folds
):
    """
    Test that None is returned when the forecaster is not ForecasterStats or
    the strategy does not skip folds.
    """
    assert stats_skip_folds_issue(forecaster, skip_folds) is None
