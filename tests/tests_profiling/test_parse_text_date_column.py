# Unit test _parse_text_date_column

import re

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import (
    DAYFIRST_FRAME_HINT,
    _parse_text_date_column,
)


def test_parse_text_date_column_output_when_day_first_text():
    """
    Test that day-first text dates are read day first throughout (the first
    of February after the 13th of January) and the day-first format is
    returned, as the script names it, and that the data given keeps its text
    and the other columns are untouched.
    """
    data = pd.DataFrame(
        {"date": ["13/01/2020", "01/02/2020", "02/02/2020"], "y": [1.0, 2.0, 3.0]}
    )
    data_copy = data.copy()

    result, date_format = _parse_text_date_column(data, "date")

    expected = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-13", "2020-02-01", "2020-02-02"]),
            "y": [1.0, 2.0, 3.0],
        }
    )
    pd.testing.assert_frame_equal(result, expected)
    assert date_format == "%d/%m/%Y"
    pd.testing.assert_frame_equal(data, data_copy)


@pytest.mark.parametrize(
    "dates, expected_dates, expected_format",
    [
        (["01/13/2020", "01/14/2020"], ["2020-01-13", "2020-01-14"], "%m/%d/%Y"),
        (["2020-01-13", "2020-01-14"], ["2020-01-13", "2020-01-14"], None),
        (["13 Jan 2020", "14 Jan 2020"], ["2020-01-13", "2020-01-14"], None),
        (["13/01/2020 10:00", "14/01/2020 11:30"],
         ["2020-01-13 10:00", "2020-01-14 11:30"], "%d/%m/%Y %H:%M"),
    ],
    ids=["month first", "iso", "month name", "day first with time"],
)
def test_parse_text_date_column_output_when_other_text_formats(
    dates, expected_dates, expected_format
):
    """
    Test that text dates are parsed as the script parses them, and that the
    format returned is the one of their order when they write the day and
    the month as numbers (month first, day first with time), and None for
    ISO 8601 and month names, which read one way only.
    """
    data = pd.DataFrame({"date": dates})

    result, date_format = _parse_text_date_column(data, "date")

    expected = pd.DataFrame({"date": pd.to_datetime(expected_dates)})
    pd.testing.assert_frame_equal(result, expected)
    assert date_format == expected_format


@pytest.mark.parametrize(
    "date_format, expected_dates",
    [
        ("%d/%m/%Y", ["2020-01-01", "2020-02-01", "2020-03-01"]),
        ("%m/%d/%Y", ["2020-01-01", "2020-01-02", "2020-01-03"]),
    ],
    ids=lambda dt: f"date_format: {dt}",
)
def test_parse_text_date_column_output_when_date_format_decides_ambiguous_dates(
    date_format, expected_dates
):
    """
    Test that text dates that read day first and month first take the order
    of the `date_format` given (the format of a profile of the data), and
    that format is the one returned.
    """
    data = pd.DataFrame({"date": ["01/01/2020", "01/02/2020", "01/03/2020"]})

    result, found_format = _parse_text_date_column(data, "date", date_format)

    expected = pd.DataFrame({"date": pd.to_datetime(expected_dates)})
    pd.testing.assert_frame_equal(result, expected)
    assert found_format == date_format


def test_parse_text_date_column_output_when_whole_numbers_of_eight_digits():
    """
    Test that a column of whole numbers that are all dates of eight digits is
    read with '%Y%m%d' in a copy, and that format is returned.
    """
    data = pd.DataFrame({"date": [20200101, 20200102], "y": [1.0, 2.0]})
    data_copy = data.copy()

    result, date_format = _parse_text_date_column(data, "date")

    expected = pd.DataFrame(
        {"date": pd.to_datetime(["2020-01-01", "2020-01-02"]), "y": [1.0, 2.0]}
    )
    pd.testing.assert_frame_equal(result, expected)
    assert date_format == "%Y%m%d"
    pd.testing.assert_frame_equal(data, data_copy)


@pytest.mark.parametrize(
    "date_column, date_format, expected_format",
    [
        ("date", None, None),
        ("date", "%d/%m/%Y", "%d/%m/%Y"),
        (None, None, None),
        (None, "%d/%m/%Y", None),
        ("missing", "%d/%m/%Y", None),
    ],
    ids=[
        "dates already parsed",
        "dates already parsed with the format of a profile",
        "no date column",
        "no date column with a format",
        "date column not in the data",
    ],
)
def test_parse_text_date_column_returns_data_when_dates_are_not_text(
    date_column, date_format, expected_format
):
    """
    Test that the same object is returned when there is nothing to parse:
    dates already parsed (with the `date_format` given as format, as it is
    the one they were read with), no date column, or a date column that the
    data does not hold (and then no format).
    """
    data = pd.DataFrame(
        {"date": pd.date_range("2020-01-01", periods=2), "y": [1.0, 2.0]}
    )

    result, found_format = _parse_text_date_column(data, date_column, date_format)

    assert result is data
    assert found_format == expected_format


def test_parse_text_date_column_returns_data_when_numbers_are_not_dates():
    """
    Test that whole numbers that are not all dates of eight digits are left
    as they are, with the `date_format` given.
    """
    data = pd.DataFrame({"date": [1, 2, 3], "y": [1.0, 2.0, 3.0]})

    result, found_format = _parse_text_date_column(data, "date", "%Y%m%d")

    assert result is data
    assert found_format == "%Y%m%d"


def test_parse_text_date_column_InvalidInputError_when_dates_read_in_both_orders():
    """
    Test that text dates that read day first and month first, with no
    `date_format` to decide and both readings regular, raise an
    InvalidInputError that asks for `dayfirst`, with the code
    'data_unreadable', the field 'data' and the hint of a DataFrame: the
    order is never guessed.
    """
    data = pd.DataFrame({"date": ["01/01/2020", "01/02/2020", "01/03/2020"]})

    err_msg = re.escape(
        "The dates of column 'date' read both day first and month first: no "
        "day is after the 12th, so '01/02/2020' may be '2020-02-01' or "
        "'2020-01-02', and both readings have a regular frequency ('MS' day "
        "first and 'D' month first), so the order is not guessed. Profile the "
        "data saying which it is, with `dayfirst`."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        _parse_text_date_column(data, "date")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == DAYFIRST_FRAME_HINT


@pytest.mark.parametrize(
    "dayfirst, expected_dates, expected_format",
    [
        (True, ["2020-01-01", "2020-02-01", "2020-03-01"], "%d/%m/%Y"),
        (False, ["2020-01-01", "2020-01-02", "2020-01-03"], "%m/%d/%Y"),
    ],
    ids=["dayfirst true", "dayfirst false"],
)
def test_parse_text_date_column_output_when_dayfirst_decides_ambiguous_dates(
    dayfirst, expected_dates, expected_format
):
    """
    Test that text dates that read day first and month first, regular in
    both orders, take the order of `dayfirst`, whose format is returned,
    without a note.
    """
    data = pd.DataFrame({"date": ["01/01/2020", "01/02/2020", "01/03/2020"]})
    notes = []

    result, found_format = _parse_text_date_column(
                               data,
                               "date",
                               dayfirst = dayfirst,
                               notes    = notes,
                           )

    expected = pd.DataFrame({"date": pd.to_datetime(expected_dates)})
    pd.testing.assert_frame_equal(result, expected)
    assert found_format == expected_format
    assert notes == []


def test_parse_text_date_column_notes_when_only_one_reading_is_regular():
    """
    Test that text dates that read in both orders and are regular in only
    one (five years of monthly dates of a US file, month first) are read in
    it, and the note that says so, with the remedy for data passed in
    memory, is appended to `notes`.
    """
    months = pd.date_range("2015-01-01", periods=60, freq="MS")
    data = pd.DataFrame({"date": months.strftime("%m/%d/%Y")})
    notes = []

    result, found_format = _parse_text_date_column(data, "date", notes=notes)

    pd.testing.assert_frame_equal(
        result, pd.DataFrame({"date": months}), check_freq=False
    )
    assert found_format == "%m/%d/%Y"
    assert notes == [
        "The dates of column 'date' read both day first and month first (no "
        "day is after the 12th): they were read month first, the only order "
        "in which they have a regular frequency ('MS'), so '02/01/2015' is "
        "'2015-02-01' and not '2015-01-02'. If they are written day first, "
        "profile the data again with `dayfirst=True`."
    ]


def test_parse_text_date_column_InvalidInputError_when_dates_have_empty_cells():
    """
    Test that a text date column with an empty cell raises an
    InvalidInputError that says where it is, as the other date issues do.
    """
    data = pd.DataFrame({"date": ["2020-01-01", None, "2020-01-03"]})

    err_msg = re.escape(
        "The dates of column 'date' have 1 empty cell(s), at row position(s) "
        "1 (counting from 0, header excluded): every row needs a date. Fill "
        "in or drop those rows."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$"):
        _parse_text_date_column(data, "date")


def test_parse_text_date_column_InvalidInputError_when_dates_in_more_than_one_format():
    """
    Test that dates that do not all follow the format of the first one raise
    an InvalidInputError that quotes both, as the script reads every date
    with the format of the first.
    """
    data = pd.DataFrame({"date": ["2020-01-13", "14/01/2020"]})

    err_msg = re.escape(
        "The dates of column 'date' do not all follow the format of the first "
        "one ('%Y-%m-%d', read from '2020-01-13'), such as '14/01/2020': the "
        "generated script reads every date with the format of the first one. "
        "Write every date in the same format, such as '2020-01-14'."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$"):
        _parse_text_date_column(data, "date")


def test_parse_text_date_column_ValueError_when_text_is_not_dates():
    """
    Test that text that is not dates raises the ValueError of pandas, as the
    generated script does when it reads the column (after the warning that
    no format could be inferred).
    """
    data = pd.DataFrame({"date": ["abc", "def"]})

    with pytest.raises(ValueError, match="Unknown datetime string format"):
        with pytest.warns(UserWarning, match="Could not infer format"):
            _parse_text_date_column(data, "date")
