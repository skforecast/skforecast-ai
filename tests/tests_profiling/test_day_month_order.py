# Unit test _day_month_order

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import (
    DAYFIRST_FRAME_HINT,
    DAYFIRST_HINT,
    _day_month_order,
    date_issue_hint,
)

# No day is after the 12th: every date reads day first and month first.
_AMBIGUOUS = pd.Series(["01/01/2015", "01/02/2015", "01/03/2015"])
_FOUND = (
    "The dates of column 'date' read both day first and month first: no day "
    "is after the 12th, so "
)


@pytest.mark.parametrize(
    "values, expected",
    [
        (["13/01/2020", "14/01/2020"], ("%d/%m/%Y", "%d/%m/%Y")),
        (["01/02/2020", "13/02/2020"], ("%d/%m/%Y", "%d/%m/%Y")),
        (["13.01.2020", "14.01.2020"], ("%d.%m.%Y", "%d.%m.%Y")),
        (["13-01-2020 10:00", "14-01-2020 11:30"], ("%d-%m-%Y %H:%M",) * 2),
        (["13/01/2020", None, "14/01/2020"], ("%d/%m/%Y", "%d/%m/%Y")),
        (["01/13/2020", "01/14/2020"], ("%m/%d/%Y", None)),
        (["01/02/2020", "01/13/2020"], ("%m/%d/%Y", None)),
    ],
    ids=[
        "day first from the first date",
        "day first after a first date that reads both",
        "day first with points",
        "day first with time",
        "day first with an empty cell",
        "month first",
        "month first after a first date that reads both",
    ],
)
def test_day_month_order_output_when_dates_read_in_one_order(values, expected):
    """
    Test that dates that read in only one order are read in it, without a
    decision from the caller, and that the recorded format is the day-first
    one whenever the dates are day first (even when the first date already
    says so, as pandas reads them month first unless told) and None for
    month first, which is what pandas reads.
    """
    chosen, recorded, issue = _day_month_order("date", pd.Series(values), True)

    assert (chosen, recorded) == expected
    assert issue is None


@pytest.mark.parametrize(
    "values, named, expected",
    [
        (["13/01/18", "14/01/18"], True, ("%d/%m/%y", "%d/%m/%y")),
        (["01/01/18", "13/01/18"], False, ("%d/%m/%y", "%d/%m/%y")),
        (["01/13/18", "01/14/18"], True, ("%m/%d/%y", "%m/%d/%y")),
        (["13.01.18 10:00", "14.01.18 11:00"], True, ("%d.%m.%y %H:%M",) * 2),
    ],
    ids=["day first", "day first found", "month first", "points with time"],
)
def test_day_month_order_output_when_year_has_two_digits(values, named, expected):
    """
    Test that dates with a year of two digits ('13/01/18'), for which pandas
    guesses no format, are read in the only order that fits, also when the
    column is not named, and that the format is recorded in either order:
    the script would otherwise read them one by one.
    """
    chosen, recorded, issue = _day_month_order("date", pd.Series(values), named)

    assert (chosen, recorded) == expected
    assert issue is None


def test_day_month_order_issue_when_year_has_two_digits_and_both_orders_read():
    """
    Test that dates with a year of two digits that read both day first and
    month first ('01/02/18') are an issue too, quoting both readings.
    """
    values = pd.Series(["01/01/18", "01/02/18", "01/03/18"])

    chosen, recorded, issue = _day_month_order("date", values, True)

    assert (chosen, recorded) == (None, None)
    assert issue[0] == (
        _FOUND + "'01/02/18' may be '2018-02-01' or '2018-01-02', and the "
        "order is not guessed"
    )
    assert issue.code == "data_unreadable"


def test_day_month_order_output_when_day_is_the_month_in_every_date():
    """
    Test that dates whose day is their month in every row ('01/01/2000' of
    annual data) read the same in both orders: there is nothing to tell,
    so no format and no issue, even with `dayfirst`.
    """
    values = pd.Series([f"01/01/{year}" for year in range(2000, 2010)])

    assert _day_month_order("date", values, True) == (None, None, None)
    assert _day_month_order("date", values, True, dayfirst=True) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    "values",
    [
        pd.Series(["2020-01-01", "2020-01-02"]),
        pd.Series(["2020/01/02", "2020/01/13"]),
        pd.Series(["01 Jan 2020", "02 Jan 2020"]),
        pd.Series(["13/13/2020", "14/14/2020"]),
        pd.Series(["abc", "def"]),
        pd.Series(pd.date_range("2020-01-01", periods=3)),
        pd.Series([1, 2, 3]),
    ],
    ids=[
        "iso",
        "year first with slashes",
        "month name",
        "no order reads",
        "not dates",
        "datetimes",
        "integers",
    ],
)
def test_day_month_order_output_when_order_is_not_in_question(values):
    """
    Test that dates whose format leaves no doubt (year first, month name),
    dates that read in neither order, text that is not dates and values that
    are not text give no format and no issue, even with `dayfirst`.
    """
    assert _day_month_order("date", values, True) == (None, None, None)
    assert _day_month_order("date", values, True, dayfirst=True) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    "dayfirst, date_format, expected",
    [
        (True, None, "%d/%m/%Y"),
        (False, None, "%m/%d/%Y"),
        (None, "%d/%m/%Y", "%d/%m/%Y"),
        (None, "%m/%d/%Y", "%m/%d/%Y"),
        (False, "%d/%m/%Y", "%d/%m/%Y"),
        (True, "%m/%d/%Y", "%m/%d/%Y"),
        (True, "%Y%m%d", "%d/%m/%Y"),
        (False, "%Y%m%d", "%m/%d/%Y"),
    ],
    ids=[
        "dayfirst true",
        "dayfirst false",
        "format day first",
        "format month first",
        "format over dayfirst false",
        "format over dayfirst true",
        "other format leaves dayfirst true",
        "other format leaves dayfirst false",
    ],
)
def test_day_month_order_output_when_both_orders_read_and_order_given(
    dayfirst, date_format, expected
):
    """
    Test that dates that read day first and month first take the order the
    caller gives: the format of a profile of the data when it is one of the
    two (it wins over `dayfirst`), otherwise `dayfirst`. The format is
    recorded in either order, as the decision is what the script must name.
    """
    result = _day_month_order(
                 name        = "date",
                 values      = _AMBIGUOUS,
                 named       = True,
                 dayfirst    = dayfirst,
                 date_format = date_format,
             )

    assert result == (expected, expected, None)


@pytest.mark.parametrize(
    "values, dayfirst, expected",
    [
        (["13/01/2020", "14/01/2020"], True, ("%d/%m/%Y", "%d/%m/%Y")),
        (["01/02/2020", "13/02/2020"], True, ("%d/%m/%Y", "%d/%m/%Y")),
        (["01/13/2020", "01/14/2020"], False, ("%m/%d/%Y", None)),
        (["01/02/2020", "01/13/2020"], False, ("%m/%d/%Y", None)),
    ],
    ids=[
        "day first",
        "day first after a first date that reads both",
        "month first",
        "month first after a first date that reads both",
    ],
)
def test_day_month_order_output_when_dayfirst_agrees_with_the_dates(
    values, dayfirst, expected
):
    """
    Test that a `dayfirst` that agrees with dates that read in only one order
    changes nothing: the same format is chosen and recorded as without it.
    """
    chosen, recorded, issue = _day_month_order(
                                  name     = "date",
                                  values   = pd.Series(values),
                                  named    = True,
                                  dayfirst = dayfirst,
                              )

    assert (chosen, recorded) == expected
    assert issue is None


@pytest.mark.parametrize("named", [True, False], ids=lambda dt: f"named: {dt}")
@pytest.mark.parametrize(
    "in_file, fix, code, hint",
    [
        (
            True,
            ". Profile the file saying which it is, with `dayfirst`.",
            "data_unreadable",
            DAYFIRST_HINT,
        ),
        (
            False,
            ": convert them with pandas.to_datetime(..., format='%d/%m/%Y') or "
            "format='%m/%d/%Y' before passing the data.",
            None,
            DAYFIRST_FRAME_HINT,
        ),
    ],
    ids=["csv file", "dataframe"],
)
def test_day_month_order_issue_when_both_orders_read_and_order_not_given(
    in_file, fix, code, hint, named
):
    """
    Test that dates that read day first and month first, with no order given,
    are an issue and never guessed: it quotes the first date and both
    readings, asks for `dayfirst` and has the code 'data_unreadable' and the
    hint of the CSV file, or asks for the dates of a DataFrame to be
    converted, with the default code and the hint of the DataFrame.
    """
    chosen, recorded, issue = _day_month_order(
                                  name    = "date",
                                  values  = _AMBIGUOUS,
                                  named   = named,
                                  in_file = in_file,
                              )

    assert (chosen, recorded) == (None, None)
    assert "".join(issue) == (
        _FOUND + "'01/02/2015' may be '2015-02-01' or '2015-01-02', and the "
        "order is not guessed" + fix
    )
    assert issue.code == code
    assert issue.field == "data"
    assert date_issue_hint(issue) == hint


@pytest.mark.parametrize(
    "values, quoted, readings",
    [
        (
            ["01/01/2020", "03/03/2020", "01/02/2020"],
            "01/02/2020",
            "'2020-02-01' or '2020-01-02'",
        ),
        (
            ["01/02/2020 10:00", "01/03/2020 11:00"],
            "01/02/2020 10:00",
            "'2020-02-01 10:00:00' or '2020-01-02 10:00:00'",
        ),
        (
            ["04/05/2020", None, "05/06/2020"],
            "04/05/2020",
            "'2020-05-04' or '2020-04-05'",
        ),
    ],
    ids=["first date whose day is not its month", "with time", "empty cell"],
)
def test_day_month_order_issue_quotes_a_date_that_reads_differently(
    values, quoted, readings
):
    """
    Test that the issue of dates that read in both orders quotes the first
    date whose two readings differ (a date such as '01/01/2020' reads the
    same either way), with the time when the readings have one, and skips
    the empty cells.
    """
    _, _, issue = _day_month_order("date", pd.Series(values), True)

    assert "".join(issue) == (
        _FOUND + f"{quoted!r} may be {readings}, and the order is not guessed. "
        "Profile the file saying which it is, with `dayfirst`."
    )


@pytest.mark.parametrize(
    "values, dayfirst, other, given, read",
    [
        (["01/13/2020", "01/14/2020"], True, "01/13/2020", "day", "month"),
        (["13/01/2020", "14/01/2020"], False, "13/01/2020", "month", "day"),
        (["01/02/2020", "13/02/2020"], False, "13/02/2020", "month", "day"),
        (["01/02/2020", "01/13/2020"], True, "01/13/2020", "day", "month"),
    ],
    ids=[
        "day first against month first dates",
        "month first against day first dates",
        "month first against a late day first date",
        "day first against a late month first date",
    ],
)
def test_day_month_order_issue_when_dayfirst_contradicts_the_dates(
    values, dayfirst, other, given, read
):
    """
    Test that a `dayfirst` against dates that read in only the other order
    is an issue on the field 'dayfirst', not on the data: it quotes the first
    date that does not read in the order given, asks to leave `dayfirst`
    out, and has the default code and the hint that says so.
    """
    chosen, recorded, issue = _day_month_order(
                                  name     = "date",
                                  values   = pd.Series(values),
                                  named    = True,
                                  dayfirst = dayfirst,
                              )

    assert (chosen, recorded) == (None, None)
    assert "".join(issue) == (
        f"`dayfirst` is {dayfirst}, but the dates of column 'date' do not "
        f"read {given} first: {other!r} only reads {read} first. Leave "
        f"`dayfirst` out to tell the order from the dates."
    )
    assert issue.code is None
    assert issue.field == "dayfirst"
    assert date_issue_hint(issue) == (
        "Leave `dayfirst` out, so the order is told from the dates."
    )
