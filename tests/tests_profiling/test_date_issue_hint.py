# Unit test date_issue_hint

import pytest

from skforecast_ai.profiling.data_profile import DateIssue, date_issue_hint


@pytest.mark.parametrize(
    "hint",
    [
        "Every row needs a date: fill in or drop the rows without one.",
        "Write every date in one time zone: in UTC for data recorded within "
        "the day, or without the time zone for daily or coarser data.",
    ],
    ids=["empty cells", "mixed time zones"],
)
def test_date_issue_hint_output_when_date_issue(hint):
    """
    Test that the hint of a DateIssue, the remedy without the pandas calls
    that only apply in Python, is returned as it is.
    """
    issue = DateIssue(
        "The dates of column 'date' have 1 empty cell(s)",
        ": every row needs a date. Fill in or drop those rows.",
        hint = hint,
    )

    assert date_issue_hint(issue) == hint


def test_date_issue_hint_output_when_plain_tuple():
    """
    Test that an issue that is a plain tuple has no hint.
    """
    assert date_issue_hint(("found", " fix")) is None
