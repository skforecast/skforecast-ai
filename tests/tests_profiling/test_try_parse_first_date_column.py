# Unit test _try_parse_first_date_column

import re
import warnings

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import _try_parse_first_date_column

from ..fixtures_datasets import df_h2o_text, df_madrid_hourly_text


def test_try_parse_first_date_column_skips_unparseable_columns():
    """
    Test that a leading text column that is not a date is left untouched
    and the next parseable column is converted instead.
    """
    data = pd.DataFrame({
        "name": ["a", "b", "c"],
        "date": ["2023-01-01", "2023-01-02", "2023-01-03"],
        "y": [1.0, 2.0, 3.0],
    })

    parsed = _try_parse_first_date_column(data)

    assert parsed["name"].tolist() == ["a", "b", "c"]
    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])


def test_try_parse_first_date_column_converts_only_the_first_date_column():
    """
    Test that once a column is parsed the remaining text columns are left
    as they are, even when they would also parse.
    """
    data = pd.DataFrame({
        "date": ["2023-01-01", "2023-01-02"],
        "other": ["2024-01-01", "2024-01-02"],
    })

    parsed = _try_parse_first_date_column(data)

    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])
    assert parsed["other"].tolist() == ["2024-01-01", "2024-01-02"]


def test_try_parse_first_date_column_reads_day_first_dates_as_the_script():
    """
    Test that the dates are parsed with the format of the first date, as
    pandas.to_datetime does in the generated script, so '01/02/2012' after
    '13/01/2012' is the first of February.
    """
    data = pd.DataFrame({
        "date": ["13/01/2012", "01/02/2012", "02/02/2012"],
        "y": [1.0, 2.0, 3.0],
    })

    parsed = _try_parse_first_date_column(data)

    expected = pd.Series(
        pd.to_datetime(["2012-01-13", "2012-02-01", "2012-02-02"]), name="date"
    )
    pd.testing.assert_series_equal(parsed["date"], expected)


@pytest.mark.parametrize(
    "empty_value", [None, " ", "NaT"], ids=["missing", "blank", "nat_text"]
)
def test_try_parse_first_date_column_ValueError_when_dates_have_empty_cells(
    empty_value
):
    """
    Test that a CSV date column with one empty cell raises an error that
    says where it is.
    """
    data = df_h2o_text.copy()
    data.loc[100, "date"] = empty_value

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "100 (counting from 0, header excluded): every row needs a date. Fill "
        "in or drop those rows. If the dates are in another column, pass its "
        "name as `date_column`; if 'date' is an exogenous variable and the data "
        "has no dates, read the CSV with pandas and pass the DataFrame instead "
        "of its path."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        _try_parse_first_date_column(data)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"


@pytest.mark.parametrize(
    "issue", ["empty_cells", "time_zones"], ids=lambda dt: f"issue: {dt}"
)
def test_try_parse_first_date_column_UserWarning_when_later_column_holds_dates(
    issue
):
    """
    Test that a column of dates that cannot be the date column (an empty
    cell, or time zones that change) is left as text when a later column
    holds complete dates, which is parsed as before, with a warning that
    names both columns.
    """
    if issue == "empty_cells":
        data = df_h2o_text.copy()
        data["period_end"] = (
            pd.to_datetime(data["date"]) + pd.offsets.MonthEnd(0)
        ).dt.strftime("%Y-%m-%d")
        data.loc[100, "date"] = None
        warn_msg = re.escape(
            "The dates of column 'date' have 1 empty cell(s), at row "
            "position(s) 100 (counting from 0, header excluded). Column "
            "'period_end' is used as the date column instead; pass "
            "`date_column` to choose another one."
        )
    else:
        data = df_madrid_hourly_text.rename(columns={"date": "local"})
        data.insert(
            1, "date",
            pd.to_datetime(data["local"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        warn_msg = re.escape(
            "The dates of column 'local' mix time zones (+01:00, +02:00)"
        )
    expected_first = data.iloc[:, 0].copy()

    with pytest.warns(UserWarning, match=warn_msg):
        parsed = _try_parse_first_date_column(data)

    pd.testing.assert_series_equal(parsed.iloc[:, 0], expected_first)
    assert pd.api.types.is_datetime64_any_dtype(
        parsed["period_end" if issue == "empty_cells" else "date"]
    )


def test_try_parse_first_date_column_ValueError_when_time_zones_change():
    """
    Test that dates in local time across a daylight saving time change raise
    an error that names the time zones, instead of being left as text.
    """
    data = df_madrid_hourly_text.copy()

    err_msg = re.escape(
        "The dates of column 'date' mix time zones (+01:00, +02:00), so they "
        "cannot be placed on one time axis"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        _try_parse_first_date_column(data)


def test_try_parse_first_date_column_skips_other_columns_when_date_column():
    """
    Test that, when `date_column` is given, a column of dates with an issue
    that is not the named one is left as text without a warning, and the
    named column is parsed.
    """
    data = df_h2o_text.copy()
    data["period_end"] = (
        pd.to_datetime(data["date"]) + pd.offsets.MonthEnd(0)
    ).dt.strftime("%Y-%m-%d")
    data.loc[100, "date"] = None

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parsed = _try_parse_first_date_column(data, date_column="period_end")

    assert parsed["date"].isna().sum() == 1
    assert pd.api.types.is_object_dtype(parsed["date"])
    assert pd.api.types.is_datetime64_any_dtype(parsed["period_end"])


@pytest.mark.parametrize(
    "n_empty", [1, 150], ids=lambda dt: f"empty cells: {dt}"
)
def test_try_parse_first_date_column_ValueError_when_date_column_has_issue(
    n_empty
):
    """
    Test that the named `date_column` raises its issue without the advice to
    pass `date_column`, also when it has more empty cells than dates, so a
    profile reused on another CSV does not reach the generated script.
    """
    data = df_h2o_text.copy()
    data.loc[list(range(10, 10 + n_empty)), "date"] = None

    err_msg = re.escape(
        f"The dates of column 'date' have {n_empty} empty cell(s), at row "
        f"position(s) 10"
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        _try_parse_first_date_column(data, date_column="date")

    assert "date_column" not in str(exc_info.value)


@pytest.mark.parametrize(
    "position", ["first", "last"], ids=lambda dt: f"promo_end: {dt}"
)
def test_try_parse_first_date_column_skips_sparse_date_columns(position):
    """
    Test that a column with more empty cells than dates (the end date of a
    promotion on three rows) is left as text, before or after the date
    column, which is parsed.
    """
    data = df_h2o_text.copy()
    data["promo_end"] = None
    data.loc[[10, 50, 120], "promo_end"] = "2000-01-31"
    if position == "first":
        data = data[["promo_end", "date", "x"]]

    parsed = _try_parse_first_date_column(data)

    assert parsed["promo_end"].notna().sum() == 3
    assert pd.api.types.is_object_dtype(parsed["promo_end"])
    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])


def test_try_parse_first_date_column_skips_blank_columns():
    """
    Test that a text column made only of blanks, which holds no date, is
    left as it is and the date column after it is parsed.
    """
    data = df_h2o_text.copy()
    data.insert(0, "notes", "  ")

    parsed = _try_parse_first_date_column(data)

    assert (parsed["notes"] == "  ").all()
    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])


@pytest.mark.parametrize(
    "dates, expected_tz",
    [
        (
            ["2012-01-01T00:00:00+01:00", "2012-01-01T01:00:00+0100",
             "2012-01-01T02:00:00+01:00"],
            "UTC+01:00",
        ),
        (
            ["2012-01-01T00:00:00Z", "2012-01-01T01:00:00+00:00",
             "2012-01-01T02:00:00Z"],
            "UTC",
        ),
    ],
    ids=["one_offset", "utc"],
)
def test_try_parse_first_date_column_parses_dates_of_one_time_zone(
    dates, expected_tz
):
    """
    Test that dates in one time zone, written with one offset in two
    spellings, are parsed as dates of that time zone.
    """
    data = pd.DataFrame({"date": dates, "y": [1.0, 2.0, 3.0]})

    parsed = _try_parse_first_date_column(data)

    assert str(parsed["date"].dt.tz) == expected_tz


def test_try_parse_first_date_column_skips_times_of_day():
    """
    Test that a column holding only times of day with empty cells, before
    the date column, is not taken for a date column with empty cells: it is
    left as text and the date column is parsed, without a warning.
    """
    data = df_h2o_text.copy()
    data.insert(0, "open_time", "09:30")
    data.loc[[3, 7], "open_time"] = None

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parsed = _try_parse_first_date_column(data)

    assert parsed["open_time"].isna().sum() == 2
    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])


@pytest.mark.parametrize(
    "date_format",
    ["%Y-%m-%d %H:%M %a", "%m/%d/%Y %I:%M %p"],
    ids=["weekday_after_time", "am_pm"],
)
def test_try_parse_first_date_column_parses_words_after_the_time(date_format):
    """
    Test that a complete date column with a word after the time that is not
    a time zone (a weekday, AM or PM) is parsed as before, without a
    warning.
    """
    dates = pd.date_range("2023-01-01", periods=48, freq="h")
    data = pd.DataFrame({"date": dates.strftime(date_format), "y": range(48)})

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parsed = _try_parse_first_date_column(data)

    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])
    assert parsed["date"].iloc[-1] == dates[-1]


@pytest.mark.parametrize(
    "values",
    [
        ["4.17.21", None, "4.17.21", "4.17.21"],
        ["01:30 hrs", "00:45 min", "01:30 hrs", "00:45 min"],
    ],
    ids=["version_numbers", "durations"],
)
def test_try_parse_first_date_column_skips_text_that_is_not_clearly_dates(values):
    """
    Test that text pandas could read as dates but that has no year of four
    digits (version numbers, durations) is left as text without an error,
    in data without a date column.
    """
    data = pd.DataFrame({"col": values, "y": [1.0, 2.0, 3.0, 4.0]})

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parsed = _try_parse_first_date_column(data)

    assert parsed["col"].tolist() == values


def test_try_parse_first_date_column_ValueError_when_date_column_after_parsed_column():
    """
    Test that the named `date_column` is checked even when an earlier column
    holds complete dates and is parsed, so a profile reused on a CSV whose
    date column has an empty cell does not reach the generated script.
    """
    data = df_h2o_text.copy()
    data.insert(0, "period_start", data["date"])
    data.loc[100, "date"] = None

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "100 (counting from 0, header excluded): every row needs a date. Fill "
        "in or drop those rows."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$"):
        _try_parse_first_date_column(data, date_column="date")


def test_try_parse_first_date_column_ValueError_when_later_column_is_not_dates():
    """
    Test that a later column that is not clearly dates (times of day) does
    not take the place of a date column with an empty cell, which is
    reported.
    """
    data = df_h2o_text.copy()
    data.loc[100, "date"] = None
    data["shift"] = ["09:30", "21:00"] * (len(data) // 2)

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "100"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        _try_parse_first_date_column(data)


def test_try_parse_first_date_column_leaves_zone_names_to_pandas():
    """
    Test that zone names that change at a daylight saving time change (CET
    then CEST) are not read as time zones: pandas parses the dates without
    them and warns that it drops them.
    """
    dates = pd.date_range("2012-03-24", periods=72, freq="h", tz="Europe/Madrid")
    data = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "y": range(72),
    })

    warn_msg = re.escape("included an un-recognized timezone")
    with pytest.warns(FutureWarning, match=warn_msg):
        parsed = _try_parse_first_date_column(data)

    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])
    assert parsed["date"].iloc[0] == pd.Timestamp("2012-03-24 00:00:00")


@pytest.mark.parametrize(
    "date_format",
    ["%a %b %d %H:%M:%S %Y %z", "%a, %d %b %Y %H:%M:%S %z (%Z)"],
    ids=["git_log", "rfc_2822_with_comment"],
)
def test_try_parse_first_date_column_ValueError_when_offsets_change_any_spelling(
    date_format
):
    """
    Test that offsets that change are reported also when they are not
    written right after the time (git log dates, email dates with a zone
    comment), from the Timestamps pandas parses.
    """
    dates = pd.date_range("2020-03-27", periods=72, freq="h", tz="Europe/Madrid")
    data = pd.DataFrame({
        "date": [date.strftime(date_format) for date in dates],
        "y": range(72),
    })

    err_msg = re.escape(
        "The dates of column 'date' mix time zones (+01:00, +02:00), so they "
        "cannot be placed on one time axis (local time does that across a "
        "daylight saving time change). Write every date in one time zone: in "
        "UTC for data recorded within the day (pandas.to_datetime(values, "
        "utc=True) converts them), or without the time zone for daily or "
        "coarser data."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        _try_parse_first_date_column(data)


def test_try_parse_first_date_column_ValueError_when_some_dates_have_no_zone():
    """
    Test that dates with and without an offset ask for a time zone on every
    date, without the pandas call, which fails on them.
    """
    dates = pd.date_range("2020-01-01", periods=96, freq="h")
    data = pd.DataFrame({
        "date": list(dates[:48].strftime("%Y-%m-%d %H:%M:%S"))
        + list(dates[48:].strftime("%Y-%m-%d %H:%M:%S+01:00")),
        "y": range(96),
    })

    err_msg = re.escape(
        "The dates of column 'date' mix time zones (no time zone, +01:00), so "
        "they cannot be placed on one time axis (local time does that across "
        "a daylight saving time change). Write every date in one time zone: "
        "in UTC for data recorded within the day, or without the time zone "
        "for daily or coarser data. Some dates have no time zone that pandas "
        "reads (it drops zone names such as 'CET'), so they must be given one "
        "first."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        _try_parse_first_date_column(data)


@pytest.mark.parametrize(
    "date_format",
    ["%m/%d/%y %H:%M", "%y-%m-%d %H:%M"],
    ids=["us_two_digit_year", "iso_two_digit_year"],
)
def test_try_parse_first_date_column_UserWarning_when_later_date_has_two_digit_year(
    date_format
):
    """
    Test that a date column with two-digit years after a date-valued column
    with empty cells is parsed as before, with the warning that names both
    columns.
    """
    data = df_h2o_text.rename(columns={"date": "promo_end"}).iloc[:120].copy()
    data.loc[list(range(0, 120, 9)), "promo_end"] = None
    data.insert(
        1, "date",
        pd.date_range("2020-01-06", periods=120, freq="h").strftime(date_format),
    )

    warn_msg = re.escape(
        "Column 'date' is used as the date column instead; pass `date_column` "
        "to choose another one."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        parsed = _try_parse_first_date_column(data)

    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])


def test_try_parse_first_date_column_UserWarning_names_every_skipped_column():
    """
    Test that the warning names every column of dates that cannot be the
    date column, when a later column is used.
    """
    data = df_h2o_text.copy()
    data.insert(0, "start", data["date"])
    data.insert(1, "end", data["date"])
    data.loc[[3], "start"] = None
    data.loc[[4], "end"] = None

    warn_msg = re.escape(
        "The dates of column 'start' have 1 empty cell(s), at row position(s) "
        "3 (counting from 0, header excluded). The dates of column 'end' have "
        "1 empty cell(s), at row position(s) 4 (counting from 0, header "
        "excluded). Column 'date' is used as the date column instead; pass "
        "`date_column` to choose another one."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        parsed = _try_parse_first_date_column(data)

    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])
