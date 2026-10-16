# Unit test _try_parse_first_date_column

import re
import warnings

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import (
    DAYFIRST_HINT,
    _try_parse_first_date_column,
)

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

    parsed, _ = _try_parse_first_date_column(data)

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

    parsed, _ = _try_parse_first_date_column(data)

    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])
    assert parsed["other"].tolist() == ["2024-01-01", "2024-01-02"]


def test_try_parse_first_date_column_reads_day_first_dates_as_the_script():
    """
    Test that the dates are parsed with the format of the first date, as
    pandas.to_datetime does in the generated script, so '01/02/2012' after
    '13/01/2012' is the first of February, and that the day-first format is
    returned, as the script names it.
    """
    data = pd.DataFrame({
        "date": ["13/01/2012", "01/02/2012", "02/02/2012"],
        "y": [1.0, 2.0, 3.0],
    })

    parsed, date_format = _try_parse_first_date_column(data)

    expected = pd.Series(
        pd.to_datetime(["2012-01-13", "2012-02-01", "2012-02-02"]), name="date"
    )
    pd.testing.assert_series_equal(parsed["date"], expected)
    assert date_format == "%d/%m/%Y"


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
        parsed, _ = _try_parse_first_date_column(data)

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
        parsed, _ = _try_parse_first_date_column(data, date_column="period_end")

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

    parsed, _ = _try_parse_first_date_column(data)

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

    parsed, _ = _try_parse_first_date_column(data)

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

    parsed, _ = _try_parse_first_date_column(data)

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
        parsed, _ = _try_parse_first_date_column(data)

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
        parsed, _ = _try_parse_first_date_column(data)

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
        parsed, _ = _try_parse_first_date_column(data)

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


@pytest.mark.parametrize("date_column", [None, "date"], ids=["detected", "named"])
def test_try_parse_first_date_column_InvalidInputError_when_zone_names_change(
    date_column
):
    """
    Test that dates with zone names that change at a daylight saving time
    change (CET then CEST) raise the error of dates in several time zones,
    detected or named: the generated script reads every date with the
    format of the first one, which holds 'CET', and fails on the others,
    which were read one by one before. pandas still warns that it does not
    recognize the zone names.
    """
    dates = pd.date_range("2012-03-24", periods=72, freq="h", tz="Europe/Madrid")
    data = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "y": range(72),
    })

    err_msg = re.escape(
        "The dates of column 'date' mix time zones (CET, CEST), so they cannot "
        "be placed on one time axis (local time does that across a daylight "
        "saving time change). Write every date in one time zone: in UTC for "
        "data recorded within the day, or without the time zone for daily or "
        "coarser data."
    )
    warn_msg = re.escape("included an un-recognized timezone")
    with (
        pytest.raises(InvalidInputError, match=err_msg) as exc_info,
        pytest.warns(FutureWarning, match=warn_msg),
    ):
        _try_parse_first_date_column(data, date_column=date_column)

    assert exc_info.value.field == "data"


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
        parsed, _ = _try_parse_first_date_column(data)

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
        parsed, _ = _try_parse_first_date_column(data)

    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])


@pytest.mark.parametrize(
    "date_column", [None, "date"], ids=lambda dt: f"date_column: {dt}"
)
def test_try_parse_first_date_column_skips_series_id_column(date_column):
    """
    Test that the column of series ids, read as text, is not taken for the
    date column when its ids ('2001', '2002') read as years: it stays text
    and the later column of dates is parsed. Without `series_id_column`, the
    ids are the ones parsed as dates, and a `date_column` given is parsed
    too.
    """
    data = pd.DataFrame({
        "store": ["2001", "2001", "2002", "2002"],
        "date": ["2020-01-01", "2020-01-02", "2020-01-01", "2020-01-02"],
        "y": [1.0, 2.0, 3.0, 4.0],
    })

    parsed, _ = _try_parse_first_date_column(
        data.copy(), date_column=date_column, series_id_column="store"
    )

    expected = pd.DataFrame({
        "store": ["2001", "2001", "2002", "2002"],
        "date": pd.to_datetime(
            ["2020-01-01", "2020-01-02", "2020-01-01", "2020-01-02"]
        ),
        "y": [1.0, 2.0, 3.0, 4.0],
    })
    pd.testing.assert_frame_equal(parsed, expected)

    parsed, _ = _try_parse_first_date_column(data.copy(), date_column=date_column)

    assert pd.api.types.is_datetime64_any_dtype(parsed["store"])
    assert parsed["store"].tolist() == [
        pd.Timestamp("2001-01-01"),
        pd.Timestamp("2001-01-01"),
        pd.Timestamp("2002-01-01"),
        pd.Timestamp("2002-01-01"),
    ]
    expected_dates = ["2020-01-01", "2020-01-02", "2020-01-01", "2020-01-02"]
    if date_column is not None:
        expected_dates = [pd.Timestamp(date) for date in expected_dates]
    assert parsed["date"].tolist() == expected_dates


def test_try_parse_first_date_column_ignores_series_id_column_that_is_not_a_column():
    """
    Test that a `series_id_column` that the data does not hold changes
    nothing: the first column of dates is parsed as without the argument.
    """
    data = pd.DataFrame({
        "date": ["2020-01-01", "2020-01-02"],
        "y": [1.0, 2.0],
    })

    parsed, _ = _try_parse_first_date_column(data, series_id_column="store")

    expected = pd.DataFrame({
        "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
        "y": [1.0, 2.0],
    })
    pd.testing.assert_frame_equal(parsed, expected)


_AMBIGUOUS_ERROR = (
    "The dates of column 'date' read both day first and month first: no day "
    "is after the 12th, so '01/02/2020' may be '2020-02-01' or '2020-01-02', "
    "and the order is not guessed. Profile the file saying which it is, with "
    "`dayfirst`."
)


@pytest.mark.parametrize(
    "date_column", [None, "date"], ids=lambda dt: f"date_column: {dt}"
)
def test_try_parse_first_date_column_InvalidInputError_when_dates_read_in_both_orders(
    date_column,
):
    """
    Test that dates that read day first and month first, with neither
    `dayfirst` nor `date_format` to decide, raise an InvalidInputError with
    the code 'data_unreadable', the field 'data' and the hint that names
    `dayfirst`, whether the column is named or found, because the order is
    never guessed.
    """
    data = pd.DataFrame({
        "date": ["01/01/2020", "01/02/2020", "01/03/2020"],
        "y": [1.0, 2.0, 3.0],
    })

    with pytest.raises(
        InvalidInputError, match="^" + re.escape(_AMBIGUOUS_ERROR) + "$"
    ) as exc_info:
        _try_parse_first_date_column(data, date_column=date_column)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == DAYFIRST_HINT


def test_try_parse_first_date_column_InvalidInputError_when_ambiguous_after_parsed():
    """
    Test that the named `date_column` is checked for the order of its dates
    even when an earlier column holds complete dates and is parsed, so a
    profile reused on a file whose dates read in both orders does not reach
    the generated script.
    """
    data = pd.DataFrame({
        "start": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "date": ["01/01/2020", "01/02/2020", "01/03/2020"],
    })

    with pytest.raises(
        InvalidInputError, match="^" + re.escape(_AMBIGUOUS_ERROR) + "$"
    ) as exc_info:
        _try_parse_first_date_column(data, date_column="date")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.hint == DAYFIRST_HINT


@pytest.mark.parametrize(
    "date_column", [None, "date"], ids=lambda dt: f"date_column: {dt}"
)
@pytest.mark.parametrize(
    "dayfirst, date_format, expected_dates, expected_format",
    [
        (True, None, ["2020-01-01", "2020-02-01", "2020-03-01"], "%d/%m/%Y"),
        (False, None, ["2020-01-01", "2020-01-02", "2020-01-03"], "%m/%d/%Y"),
        (None, "%d/%m/%Y", ["2020-01-01", "2020-02-01", "2020-03-01"], "%d/%m/%Y"),
        (None, "%m/%d/%Y", ["2020-01-01", "2020-01-02", "2020-01-03"], "%m/%d/%Y"),
        (False, "%d/%m/%Y", ["2020-01-01", "2020-02-01", "2020-03-01"], "%d/%m/%Y"),
    ],
    ids=[
        "dayfirst true",
        "dayfirst false",
        "format day first",
        "format month first",
        "format over dayfirst",
    ],
)
def test_try_parse_first_date_column_output_when_both_orders_read_and_order_given(
    dayfirst, date_format, expected_dates, expected_format, date_column
):
    """
    Test that dates that read day first and month first are read in the order
    that `dayfirst` or the `date_format` of a profile give (the format wins),
    and that the format returned is the one the dates were read with, in
    either order.
    """
    data = pd.DataFrame({
        "date": ["01/01/2020", "01/02/2020", "01/03/2020"],
        "y": [1.0, 2.0, 3.0],
    })

    parsed, found_format = _try_parse_first_date_column(
                               data,
                               date_column = date_column,
                               dayfirst    = dayfirst,
                               date_format = date_format,
                           )

    expected = pd.DataFrame({
        "date": pd.to_datetime(expected_dates),
        "y": [1.0, 2.0, 3.0],
    })
    pd.testing.assert_frame_equal(parsed, expected)
    assert found_format == expected_format


@pytest.mark.parametrize(
    "dates, expected_dates, expected_format",
    [
        (["13/01/2020", "14/01/2020"], ["2020-01-13", "2020-01-14"], "%d/%m/%Y"),
        (["01/02/2020", "13/02/2020"], ["2020-02-01", "2020-02-13"], "%d/%m/%Y"),
        (["01/13/2020", "01/14/2020"], ["2020-01-13", "2020-01-14"], None),
        (["01/02/2020", "01/13/2020"], ["2020-01-02", "2020-01-13"], None),
        (["2020-01-13", "2020-01-14"], ["2020-01-13", "2020-01-14"], None),
    ],
    ids=[
        "day first",
        "day first after a date that reads both",
        "month first",
        "month first after a date that reads both",
        "iso",
    ],
)
def test_try_parse_first_date_column_output_when_dates_read_in_one_order(
    dates, expected_dates, expected_format
):
    """
    Test that dates that read in only one order are read in it with no
    `dayfirst`, even when the first date reads both ways, and that the
    format returned is the day-first one for day-first dates (the script
    must name it) and None for month-first dates and ISO 8601, which pandas
    reads without being told.
    """
    data = pd.DataFrame({"date": dates, "y": [1.0, 2.0]})

    parsed, found_format = _try_parse_first_date_column(data)

    expected = pd.DataFrame({"date": pd.to_datetime(expected_dates), "y": [1.0, 2.0]})
    pd.testing.assert_frame_equal(parsed, expected)
    assert found_format == expected_format


@pytest.mark.parametrize(
    "dates, expected_dates",
    [
        (["01/01/2020", "01/02/2020"], ["2020-01-01", "2020-01-02"]),
        (["13/01/2020", "01/02/2020"], ["2020-01-13", "2020-02-01"]),
    ],
    ids=["dates that read in both orders", "day first dates"],
)
def test_try_parse_first_date_column_output_when_check_order_is_False(
    dates, expected_dates
):
    """
    Test that the order of the day and the month is not told without
    `check_order`: dates that read in both orders do not raise, and the
    dates are read as pandas reads them, with the format of the first one,
    which is then not returned (the data needs no format).
    """
    data = pd.DataFrame({"date": dates, "y": [1.0, 2.0]})

    parsed, found_format = _try_parse_first_date_column(data, check_order=False)

    expected = pd.DataFrame({"date": pd.to_datetime(expected_dates), "y": [1.0, 2.0]})
    pd.testing.assert_frame_equal(parsed, expected)
    assert found_format is None


def test_try_parse_first_date_column_InvalidInputError_when_dayfirst_against_named():
    """
    Test that `dayfirst` against the dates of the named column, which read
    only in the other order, raises an InvalidInputError on the field
    'dayfirst' that quotes a date that does not fit it, with the hint to
    leave `dayfirst` out.
    """
    data = pd.DataFrame({"date": ["01/13/2020", "01/14/2020"], "y": [1.0, 2.0]})

    err_msg = re.escape(
        "`dayfirst` is True, but the dates of column 'date' do not read day "
        "first: '01/13/2020' only reads month first. Leave `dayfirst` out to "
        "tell the order from the dates."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        _try_parse_first_date_column(data, date_column="date", dayfirst=True)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "dayfirst"
    assert exc_info.value.hint == (
        "Leave `dayfirst` out, so the order is told from the dates."
    )


def test_try_parse_first_date_column_InvalidInputError_when_dayfirst_against_found():
    """
    Test that `dayfirst` against the dates of the column found, which read
    only in the other order, raises an InvalidInputError on the field
    'dayfirst' with the same message start and hint as for a named column.
    """
    data = pd.DataFrame({"date": ["13/01/2020", "14/01/2020"], "y": [1.0, 2.0]})

    err_msg = re.escape(
        "`dayfirst` is False, but the dates of column 'date' do not read "
        "month first: '13/01/2020' only reads day first. Leave `dayfirst` out "
        "to tell the order from the dates."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        _try_parse_first_date_column(data, dayfirst=False)

    assert exc_info.value.field == "dayfirst"
    assert exc_info.value.hint == (
        "Leave `dayfirst` out, so the order is told from the dates."
    )


@pytest.mark.parametrize(
    "dayfirst, dates, code",
    [
        (None, ["01/01/2020", "01/02/2020", "01/03/2020"], "data_unreadable"),
        (True, ["01/13/2020", "01/14/2020", "01/15/2020"], "invalid_argument"),
    ],
    ids=["read in both orders", "dayfirst against the dates"],
)
def test_try_parse_first_date_column_InvalidInputError_when_order_issue_before_dates(
    dayfirst, dates, code
):
    """
    Test that a column whose order of day and month cannot be told, or that
    `dayfirst` contradicts, raises even when a later column holds dates
    ('end'), instead of being skipped for it with a warning: it holds every
    date, so it is the date column.
    """
    data = pd.DataFrame({
        "date": dates,
        "end": ["2020-02-01", "2020-02-02", "2020-02-03"],
        "y": [1.0, 2.0, 3.0],
    })

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(
            InvalidInputError, match="^(The dates of column .date.|`dayfirst`)"
        ) as exc_info:
            _try_parse_first_date_column(data, dayfirst=dayfirst)

    assert exc_info.value.code == code


@pytest.mark.parametrize(
    "date_column", [None, "date"], ids=lambda dt: f"date_column: {dt}"
)
def test_try_parse_first_date_column_output_when_whole_numbers_of_eight_digits(
    date_column,
):
    """
    Test that a column of whole numbers that are all dates of eight digits
    ('20200131') is converted to dates, found in the order of the columns or
    named, and the format '%Y%m%d' is returned.
    """
    data = pd.DataFrame({"date": [20200101, 20200102, 20200131], "y": [1.5, 2.5, 3.5]})

    parsed, found_format = _try_parse_first_date_column(data, date_column=date_column)

    expected = pd.DataFrame({
        "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-31"]),
        "y": [1.5, 2.5, 3.5],
    })
    pd.testing.assert_frame_equal(parsed, expected)
    assert found_format == "%Y%m%d"


def test_try_parse_first_date_column_converts_only_the_first_column_of_whole_numbers():
    """
    Test that, as with text, only the first column of dates is converted: a
    second column of whole numbers that are dates stays as it is, and a text
    column that is not a date before it is skipped.
    """
    data = pd.DataFrame({
        "name": ["a", "b"],
        "day": [20200101, 20200102],
        "other": [20210101, 20210102],
    })

    parsed, found_format = _try_parse_first_date_column(data)

    expected = pd.DataFrame({
        "name": ["a", "b"],
        "day": pd.to_datetime(["2020-01-01", "2020-01-02"]),
        "other": [20210101, 20210102],
    })
    pd.testing.assert_frame_equal(parsed, expected)
    assert found_format == "%Y%m%d"


@pytest.mark.parametrize(
    "data",
    [
        pd.DataFrame({"a": [1, 2], "b": [3, 4]}),
        pd.DataFrame({"a": [20200101.0, 20200102.0], "b": [3, 4]}),
        pd.DataFrame({"a": [20200101, 20200230], "b": [3, 4]}),
        pd.DataFrame({"a": [20200101, 5], "b": [3, 4]}),
        pd.DataFrame({"a": [20200101, None], "b": [3, 4]}),
    ],
    ids=["small numbers", "floats", "day that does not exist", "one small number",
         "missing value"],
)
def test_try_parse_first_date_column_leaves_numbers_that_are_not_dates(data):
    """
    Test that columns of numbers that are not all whole dates of eight digits
    (counts, amounts, floats, a day that does not exist, a missing value) are
    left as they are and no format is returned.
    """
    data_copy = data.copy()

    parsed, found_format = _try_parse_first_date_column(data)

    pd.testing.assert_frame_equal(parsed, data_copy)
    assert found_format is None


def test_try_parse_first_date_column_skips_series_id_column_of_whole_numbers():
    """
    Test that the column of series ids, which are numbers that look like
    dates of eight digits, is never taken for the date column: it stays as it
    is and the later column of dates is converted.
    """
    data = pd.DataFrame({
        "store": [20200101, 20200101, 20200102, 20200102],
        "date": ["2020-01-01", "2020-01-02", "2020-01-01", "2020-01-02"],
    })

    parsed, found_format = _try_parse_first_date_column(
        data, series_id_column="store"
    )

    assert parsed["store"].tolist() == [20200101, 20200101, 20200102, 20200102]
    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])
    assert found_format is None


@pytest.mark.parametrize(
    "values, expected_dates, expected_format",
    [
        (["13/01/2020", "14/01/2020"], ["2020-01-13", "2020-01-14"], "%d/%m/%Y"),
        ([20200113, 20200114], ["2020-01-13", "2020-01-14"], "%Y%m%d"),
        (["2020-01-13", "2020-01-14"], ["2020-01-13", "2020-01-14"], None),
    ],
    ids=["day first text", "whole numbers", "iso text"],
)
def test_try_parse_first_date_column_converts_named_column_after_parsed_column(
    values, expected_dates, expected_format
):
    """
    Test that the named `date_column` is converted itself when an earlier
    column of dates was converted first, and the format returned is the one
    of the named column, not of the earlier one.
    """
    data = pd.DataFrame({
        "start": ["2019-12-01", "2019-12-02"],
        "date": values,
    })

    parsed, found_format = _try_parse_first_date_column(data, date_column="date")

    expected = pd.DataFrame({
        "start": pd.to_datetime(["2019-12-01", "2019-12-02"]),
        "date": pd.to_datetime(expected_dates),
    })
    pd.testing.assert_frame_equal(parsed, expected)
    assert found_format == expected_format


def test_try_parse_first_date_column_dayfirst_decides_named_column_after_parsed():
    """
    Test that `dayfirst` decides the order of the dates of the named column
    that read in both, when an earlier column was converted first.
    """
    data = pd.DataFrame({
        "start": ["2019-12-01", "2019-12-02"],
        "date": ["01/01/2020", "01/02/2020"],
    })

    parsed, found_format = _try_parse_first_date_column(
        data, date_column="date", dayfirst=True
    )

    expected = pd.DataFrame({
        "start": pd.to_datetime(["2019-12-01", "2019-12-02"]),
        "date": pd.to_datetime(["2020-01-01", "2020-02-01"]),
    })
    pd.testing.assert_frame_equal(parsed, expected)
    assert found_format == "%d/%m/%Y"
