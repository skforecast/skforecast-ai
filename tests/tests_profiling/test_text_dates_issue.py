# Unit test _text_dates_issue

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _text_dates_issue

from ..fixtures_datasets import df_h2o_text, df_madrid_hourly_text


@pytest.mark.parametrize(
    "values",
    [
        ["2023-01-01", "2023-01-02", "2023-01-03"],
        ["2012-01-01T00:00:00+01:00", "2012-01-01T01:00:00+0100"],
        ["2012-01-01T00:00:00Z", "2012-01-01T01:00:00+00:00"],
    ],
    ids=["dates", "one_offset_two_spellings", "utc_two_spellings"],
)
def test_text_dates_issue_output_when_column_can_be_the_date_column(values):
    """
    Test that a complete column of dates in one time zone, in any spelling
    of it, has no issue.
    """
    values = pd.Series(values, dtype=object)

    assert _text_dates_issue("date", values, named=False) is None


@pytest.mark.parametrize("named", [True, False], ids=lambda dt: f"named: {dt}")
def test_text_dates_issue_output_when_dates_have_empty_cells(named):
    """
    Test that a column of dates with empty cells (missing, blank or 'NaT')
    says where they are.
    """
    values = df_h2o_text["date"].copy()
    values[[0, 100, 150]] = [None, " ", "NaT"]

    issue = "".join(_text_dates_issue("date", values, named))

    assert issue == (
        "The dates of column 'date' have 3 empty cell(s), at row position(s) "
        "0, 100, 150 (counting from 0, header excluded): every row needs a "
        "date. Fill in or drop those rows."
    )


def test_text_dates_issue_output_lists_five_positions_at_most():
    """
    Test that the message quotes the first five empty cells and counts the
    rest.
    """
    values = df_h2o_text["date"].copy()
    values[list(range(10, 17))] = None

    issue = "".join(_text_dates_issue("date", values, named=False))

    assert issue == (
        "The dates of column 'date' have 7 empty cell(s), at row position(s) "
        "10, 11, 12, 13, 14 and 2 more (counting from 0, header excluded): "
        "every row needs a date. Fill in or drop those rows."
    )


@pytest.mark.parametrize(
    "n_empty, expected_issue",
    [(3, True), (4, False)],
    ids=["half_empty", "more_empty_than_dates"],
)
def test_text_dates_issue_output_when_more_empty_cells_than_dates(
    n_empty, expected_issue
):
    """
    Test that a column that was not named as the date column is reported
    with as many empty cells as dates, and not with more empty cells than
    dates (the end date of a promotion), while a named one is in both cases.
    """
    values = pd.Series(
        [None] * n_empty + ["2023-01-31", "2023-02-28", "2023-03-31"],
        dtype=object,
    )

    issue_not_named = _text_dates_issue("promo_end", values, named=False)
    issue_named = _text_dates_issue("promo_end", values, named=True)

    assert (issue_not_named is not None) is expected_issue
    assert "".join(issue_named).startswith(
        f"The dates of column 'promo_end' have {n_empty} empty cell(s)"
    )


def test_text_dates_issue_output_when_time_zones_change():
    """
    Test that dates in local time across a daylight saving time change
    ('+01:00' then '+02:00') name the time zones found.
    """
    issue = _text_dates_issue(
        "date", df_madrid_hourly_text["date"], named=False
    )

    assert "".join(issue) == (
        "The dates of column 'date' mix time zones (+01:00, +02:00), so they "
        "cannot be placed on one time axis (local time does that across a "
        "daylight saving time change). Write every date in one time zone: in "
        "UTC for data recorded within the day (pandas.to_datetime(values, "
        "utc=True) converts them), or without the time zone for daily or "
        "coarser data."
    )


def test_text_dates_issue_output_names_four_time_zones_at_most():
    """
    Test that the message names the first four time zones found and marks
    the rest, and that mixed time zones are reported before empty cells.
    """
    offsets = ["+01:00", "+02:00", "+03:00", "+04:00", "+05:00", "+06:00"]
    values = pd.Series(
        [f"2023-01-0{i + 1}T00:00:00{offset}" for i, offset in enumerate(offsets)]
        + [None],
        dtype=object,
    )

    issue = "".join(_text_dates_issue("date", values, named=False))

    assert issue.startswith(
        "The dates of column 'date' mix time zones (+01:00, +02:00, +03:00, "
        "+04:00, ...), so they cannot be placed on one time axis"
    )


@pytest.mark.parametrize(
    "values",
    [
        ["a", "b", "c"],
        ["2023-01-01", "b", None],
        ["  ", "  ", "  "],
        [None, None, None],
        ["Jan", "Feb", "Mar"],
        ["2023-01-01 00:00 Sun", "2023-01-02 00:00 Mon", "2023-01-03 00:00 Tue"],
    ],
    ids=[
        "text", "text_after_a_date", "blanks", "empty", "month_names",
        "weekday_after_time",
    ],
)
def test_text_dates_issue_output_when_column_does_not_hold_dates(values):
    """
    Test that a column whose cells that are not empty are not all dates, or
    that has no such cell, has no issue, named or not; nor has a complete
    column with a weekday after the time, which is not a time zone.
    """
    values = pd.Series(values, dtype=object)

    assert _text_dates_issue("col", values, named=False) is None
    assert _text_dates_issue("col", values, named=True) is None


@pytest.mark.parametrize(
    "values",
    [
        ["09:30", None, "10:30"],
        ["4.17.21", None, "4.17.21"],
        ["01:30 hrs", "00:45 min", "01:30 hrs"],
        ["2019/1", None, "2019/2"],
        ["1990", None, "1991"],
        ["1/6/20 0:00", None, "1/6/20 2:00"],
    ],
    ids=[
        "time_of_day", "version_numbers", "durations", "codes", "years",
        "two_digit_years",
    ],
)
def test_text_dates_issue_output_when_not_clearly_dates_and_not_named(values):
    """
    Test that a column that was not named as the date column has no issue
    when its first value is not clearly a date (no day, month and year of
    four digits), although pandas could read it as one.
    """
    values = pd.Series(values, dtype=object)

    assert _text_dates_issue("col", values, named=False) is None


def test_text_dates_issue_output_when_named_two_digit_years_have_empty_cell():
    """
    Test that a named column of dates with two-digit years reports its empty
    cell, as it is not checked to be clearly a date.
    """
    values = pd.Series(["1/6/20 0:00", None, "1/6/20 2:00"], dtype=object)

    issue = "".join(_text_dates_issue("date", values, named=True))

    assert issue.startswith("The dates of column 'date' have 1 empty cell(s)")


def test_text_dates_issue_output_when_some_dates_have_no_time_zone():
    """
    Test that dates with and without an offset ask for a time zone on every
    date, without the pandas call, which fails on them, as what was found
    and how to fix it.
    """
    values = pd.Series(
        ["2020-01-01 00:00:00", "2020-01-01 01:00:00+01:00"], dtype=object
    )

    issue = _text_dates_issue("date", values, named=False)

    assert issue == (
        "The dates of column 'date' mix time zones (no time zone, +01:00)",
        ", so they cannot be placed on one time axis (local time does that "
        "across a daylight saving time change). Write every date in one time "
        "zone: in UTC for data recorded within the day, or without the time "
        "zone for daily or coarser data. Some dates have no time zone that "
        "pandas reads (it drops zone names such as 'CET'), so they must be "
        "given one first.",
    )
