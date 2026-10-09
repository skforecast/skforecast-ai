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
