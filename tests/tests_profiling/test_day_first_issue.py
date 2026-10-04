# Unit test _day_first_issue

import pandas as pd

from skforecast_ai.profiling.data_profile import _day_first_issue, date_issue_hint


def test_day_first_issue_output():
    """
    Test that the issue says the dates are day-first, quotes the first date,
    the month-first format read from it and the date that does not fit it,
    and gives an ISO 8601 example of that date, read day-first, in the
    message and in the hint.
    """
    values = pd.Series(["01/02/2023", "12/02/2023", "13/02/2023"])
    read_day_first = pd.to_datetime(values, format="%d/%m/%Y")

    issue = _day_first_issue(
                name           = "fecha",
                first          = "01/02/2023",
                date_format    = "%m/%d/%Y",
                other          = "13/02/2023",
                read_day_first = read_day_first,
                date           = read_day_first.iloc[2],
            )

    assert "".join(issue) == (
        "The dates of column 'fecha' are written day first, but the first "
        "one, '01/02/2023', also reads month first ('%m/%d/%Y'), the format "
        "the generated script reads every date with, and '13/02/2023' does "
        "not fit it: write the dates in ISO 8601, such as '2023-02-13', or "
        "read them with pandas.to_datetime(..., dayfirst=True) before "
        "passing them."
    )
    assert date_issue_hint(issue) == (
        "Write the dates of the column in ISO 8601, such as '2023-02-13'."
    )
