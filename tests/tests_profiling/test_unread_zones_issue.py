# Unit test _unread_zones_issue

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _unread_zones_issue

# Hours across the daylight saving time change of 2012-03-25 in Madrid.
_HOURS = pd.date_range("2012-03-24", periods=72, freq="h", tz="Europe/Madrid")


@pytest.mark.parametrize("named", [True, False], ids=["named", "detected"])
def test_unread_zones_issue_output_when_zone_names_change(named):
    """
    Test that dates with zone names that change ('CET', then 'CEST'), which
    pandas 3 does not read, are reported as dates of several time zones.
    """
    values = pd.Series(_HOURS.strftime("%Y-%m-%d %H:%M:%S %Z"), dtype=object)

    issue = _unread_zones_issue("date", values, named=named)

    assert "".join(issue) == (
        "The dates of column 'date' mix time zones (CET, CEST), so they cannot "
        "be placed on one time axis (local time does that across a daylight "
        "saving time change). Write every date in one time zone: in UTC for "
        "data recorded within the day, or without the time zone for daily or "
        "coarser data."
    )


def test_unread_zones_issue_output_when_one_zone_name():
    """
    Test that dates with one zone name, which pandas 3 does not read, are
    reported with the name and the ways to write them that pandas reads.
    """
    values = pd.Series(_HOURS[:24].strftime("%Y-%m-%d %H:%M:%S %Z"), dtype=object)

    issue = _unread_zones_issue("date", values, named=True)

    assert "".join(issue) == (
        "The dates of column 'date' are written with the time zone name 'CET', "
        "which pandas does not read: write every date with its UTC offset "
        "(such as '+01:00'), in UTC, or without the time zone."
    )
    assert issue.hint == (
        "Write every date with its UTC offset (such as '+01:00'), in UTC, or "
        "without the time zone."
    )
    assert issue.field == "data"


@pytest.mark.parametrize(
    "date_format",
    ["%a %b %d %H:%M:%S %Y %z", "%a, %d %b %Y %H:%M:%S %z (%Z)"],
    ids=["git_log", "rfc_2822_with_comment"],
)
def test_unread_zones_issue_output_when_offsets_change(date_format):
    """
    Test that dates of several UTC offsets written in a spelling the text
    checks do not read (git log dates, email dates with a zone comment),
    which pandas 3 raises on, are reported with their offsets.
    """
    values = pd.Series([date.strftime(date_format) for date in _HOURS], dtype=object)

    issue = _unread_zones_issue("date", values, named=True)

    assert "".join(issue) == (
        "The dates of column 'date' mix time zones (+01:00, +02:00), so they "
        "cannot be placed on one time axis (local time does that across a "
        "daylight saving time change). Write every date in one time zone: in "
        "UTC for data recorded within the day (pandas.to_datetime(values, "
        "utc=True) converts them), or without the time zone for daily or "
        "coarser data."
    )


@pytest.mark.parametrize(
    "values, named",
    [
        (["2020-01-01 open", "2020-01-02 closed"], True),
        (["2020-01-01 10:30 PM", "2020-01-02 11:30 AM"], True),
        (["2020-01-01", "2020-01-02"], True),
        (["abc", "def"], True),
        (["10:30 CET", "11:30 CEST"], False),
        ([None, None], True),
    ],
    ids=["word after a date", "half of the day", "dates", "text",
         "not clearly dates and not named", "empty"],
)
def test_unread_zones_issue_output_is_None_when_zones_are_not_the_reason(
    values, named
):
    """
    Test that there is no issue when the time zones are not why pandas
    cannot read a column: a word after a date without a time is not a zone
    name, nor is the half of the day; dates of one time zone and text that
    holds no dates have none; and a column that was not named needs a first
    value that is clearly a date.
    """
    issue = _unread_zones_issue("date", pd.Series(values, dtype=object), named=named)

    assert issue is None
