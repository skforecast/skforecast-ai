# Unit test parse_text_dates

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai._dates import parse_text_dates


@pytest.mark.parametrize(
    "values, expected",
    [
        (
            ["13/01/2012", "01/02/2012", "02/02/2012"],
            ["2012-01-13", "2012-02-01", "2012-02-02"],
        ),
        (
            ["01/02/2012", "02/02/2012", "03/02/2012"],
            ["2012-01-02", "2012-02-02", "2012-03-02"],
        ),
    ],
    ids=["day_first", "month_first"],
)
def test_parse_text_dates_output(values, expected):
    """
    Test that text dates are parsed with the format guessed from the first
    date, as pandas.to_datetime does in the generated script ('13/01/2012'
    makes '01/02/2012' the first of February).
    """
    parsed = parse_text_dates(pd.Series(values))

    pd.testing.assert_series_equal(
        parsed, pd.Series(pd.to_datetime(expected, format="mixed")), check_names=False
    )


def test_parse_text_dates_ValueError_when_date_does_not_follow_format():
    """
    Test that a date that does not follow the format of the first date
    raises the error of pandas.to_datetime, as the generated script does,
    instead of being parsed on its own.
    """
    values = pd.Series(["2012-01-01", "2012-01-02 10:30", "2012-01-03"])

    err_msg = re.escape(
        'unconverted data remains when parsing with format "%Y-%m-%d": " 10:30", '
        "at position 1."
    )
    with pytest.raises(ValueError, match=err_msg):
        parse_text_dates(values)


def test_parse_text_dates_output_when_first_date_is_numpy_str():
    """
    Test that numpy str dates are parsed without guessing a format, as
    pandas.to_datetime does, instead of failing in the format guess.
    """
    values = pd.Series(
        list(np.array(["2012-01-13", "2012-01-14", "2012-01-15"], dtype=str))
    )

    parsed = parse_text_dates(values)

    pd.testing.assert_series_equal(
        parsed, pd.Series(pd.to_datetime(["2012-01-13", "2012-01-14", "2012-01-15"]))
    )


def test_parse_text_dates_output_when_first_date_is_not_text():
    """
    Test that no format is guessed when the first date is a Timestamp, as in
    pandas.to_datetime: the day-first text after it is parsed date by date,
    so '01/02/2012' is the second of January, as the script reads it.
    """
    values = pd.Series(
        [pd.Timestamp("2012-01-12"), "13/01/2012", "01/02/2012"], dtype=object
    )

    parsed = parse_text_dates(values)

    pd.testing.assert_series_equal(
        parsed, pd.Series(pd.to_datetime(["2012-01-12", "2012-01-13", "2012-01-02"]))
    )


@pytest.mark.parametrize(
    "values, date_format, expected",
    [
        (
            ["01/02/2020", "02/02/2020", "03/02/2020"],
            "%d/%m/%Y",
            ["2020-02-01", "2020-02-02", "2020-02-03"],
        ),
        (
            ["01/02/2020", "02/02/2020", "03/02/2020"],
            "%m/%d/%Y",
            ["2020-01-02", "2020-02-02", "2020-03-02"],
        ),
        (
            ["01/02/2020", "13/02/2020", "01/03/2020"],
            "%d/%m/%Y",
            ["2020-02-01", "2020-02-13", "2020-03-01"],
        ),
    ],
    ids=["ambiguous_day_first", "ambiguous_month_first", "day_first_not_first"],
)
def test_parse_text_dates_output_when_date_format(values, date_format, expected):
    """
    Test that every date is read with `date_format`, instead of the format
    guessed from the first one: an ambiguous '01/02/2020' is the first of
    February with '%d/%m/%Y' and the second of January with '%m/%d/%Y', and
    a later day-first date such as '13/02/2020' is read with it too.
    """
    parsed = parse_text_dates(pd.Series(values), date_format)

    pd.testing.assert_series_equal(parsed, pd.Series(pd.to_datetime(expected)))


@pytest.mark.parametrize(
    "values, err_msg",
    [
        (
            ["01/02/2020", "2020-02-02"],
            'time data "2020-02-02" doesn\'t match format "%d/%m/%Y", at '
            "position 1.",
        ),
        (
            ["01/02/2020", "31/02/2020"],
            "day is out of range for month, at position 1.",
        ),
        (
            ["01/02/2020", "13/02/2020 10:30"],
            'unconverted data remains when parsing with format "%d/%m/%Y": '
            '" 10:30", at position 1.',
        ),
    ],
    ids=["other_format", "day_out_of_range", "unconverted_data"],
)
def test_parse_text_dates_ValueError_when_date_does_not_follow_date_format(
    values, err_msg
):
    """
    Test that, with `date_format`, a date that does not follow it raises the
    error of pandas.to_datetime, as the generated script does with
    `format=`, instead of falling back to the format guessed from the first
    date.
    """
    with pytest.raises(ValueError, match=re.escape(err_msg)):
        parse_text_dates(pd.Series(values), "%d/%m/%Y")
