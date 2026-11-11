# Unit test date_issue_error

import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import DateIssue, date_issue_error


@pytest.mark.parametrize(
    "issue, message, expected",
    [
        (
            DateIssue(
                "The dates of column 'date' read both orders",
                ". Profile the file saying which it is.",
                hint  = "Say the order.",
                code  = "data_unreadable",
                field = "dayfirst",
            ),
            None,
            (
                "The dates of column 'date' read both orders. Profile the file "
                "saying which it is.",
                "data_unreadable",
                "dayfirst",
                "Say the order.",
            ),
        ),
        (
            DateIssue("The dates have empty cells", ": fill them.", hint="Fill."),
            None,
            (
                "The dates have empty cells: fill them.",
                "invalid_argument",
                "data",
                "Fill.",
            ),
        ),
        (
            ("The dates have empty cells", ": fill them."),
            None,
            (
                "The dates have empty cells: fill them.",
                "invalid_argument",
                "data",
                None,
            ),
        ),
        (
            DateIssue(
                "found",
                " fix",
                hint  = "Say the order.",
                code  = "data_unreadable",
                field = "dayfirst",
            ),
            "Another message.",
            ("Another message.", "data_unreadable", "dayfirst", "Say the order."),
        ),
    ],
    ids=[
        "date issue with code and field",
        "date issue with the default code and field",
        "plain tuple",
        "message given",
    ],
)
def test_date_issue_error_output(issue, message, expected):
    """
    Test that the error of a date issue is an InvalidInputError (a
    ValueError) with the joined issue as message, or the `message` given in
    its place, and the code, the field and the hint of the issue: the
    default code 'invalid_argument', the field 'data' and no hint for what
    the issue does not carry, as for a plain tuple.
    """
    error = date_issue_error(issue, message)

    assert isinstance(error, InvalidInputError)
    assert isinstance(error, ValueError)
    assert (str(error), error.code, error.field, error.hint) == expected


def test_date_issue_error_is_returned_and_not_raised():
    """
    Test that the function returns the error for the caller to raise, so
    the issue is kept as it is.
    """
    issue = DateIssue("found", " fix", hint="Hint.")

    error = date_issue_error(issue)

    assert error.args == ("found fix",)
    assert issue == ("found", " fix")
    assert issue.hint == "Hint."
