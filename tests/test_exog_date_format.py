# Unit test exog_date_format

import re
import warnings

import pandas as pd
import pytest

from skforecast_ai._future_exog import exog_date_format
from skforecast_ai.exceptions import DataContentError
from skforecast_ai.profiling.data_profile import EXOG_DATES_HINT

from tests.fixtures_future_exog import exog_day_first, profile_day_first


def test_exog_date_format_output_when_exog_is_None():
    """
    Test that without future exogenous variables there is no format: the
    script reads `exog_future.csv` as pandas guesses it.
    """
    assert exog_date_format(None, profile_day_first) is None


@pytest.mark.parametrize(
    "dates, expected",
    [
        (["2021-02-01", "2021-02-02"], None),
        (["12/02/2021", "13/02/2021"], "%d/%m/%Y"),
        (["02/12/2021", "02/13/2021"], "%m/%d/%Y"),
        ([20210201, 20210202], "%Y%m%d"),
        (pd.date_range("2021-02-01", periods=2), None),
    ],
    ids=["iso", "day first", "month first", "whole numbers", "datetimes"],
)
def test_exog_date_format_output_when_dates_tell_their_format(dates, expected):
    """
    Test that the text dates of the date column of the future values are
    read with the rules of the data, whatever the format of the data
    (day first here): ISO 8601 needs no format, dates whose order the days
    after the 12th tell have the format of that order, whole numbers of
    eight digits are '%Y%m%d', and dates already parsed need none. No
    warning is emitted.
    """
    exog = pd.DataFrame({"date": dates, "promo": [0.0, 1.0]})

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = exog_date_format(exog, profile_day_first)

    assert result == expected


def test_exog_date_format_output_when_dates_are_in_the_index():
    """
    Test that future values dated by their index, which `to_csv()` writes in
    ISO 8601, need no format.
    """
    exog = pd.DataFrame(
        {"promo": [0.0, 1.0]},
        index=pd.DatetimeIndex(["2021-02-01", "2021-02-02"], name="date"),
    )

    assert exog_date_format(exog, profile_day_first) is None


def test_exog_date_format_output_when_format_of_the_data_decides_the_order():
    """
    Test that dates that read both day first and month first ('01/02/2021'
    to '07/02/2021') take the order of the format of the data, day first,
    without a warning.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = exog_date_format(exog_day_first, profile_day_first)

    assert result == "%d/%m/%Y"


def test_exog_date_format_output_when_text_dates_are_in_the_index():
    """
    Test that text dates in the index of the future values, which the
    executed code takes as the date column of the data, are read with the
    same rules: a horizon written day first that reads both ways takes the
    order of the data.
    """
    exog = exog_day_first.set_index("date")

    assert exog_date_format(exog, profile_day_first) == "%d/%m/%Y"


def test_exog_date_format_UserWarning_when_order_told_from_regularity():
    """
    Test that, when the format of the data does not decide (none), the same
    dates take the only order in which they have a regular frequency (day
    first, daily), with a UserWarning that says so.
    """
    profile = profile_day_first.model_copy(update={"date_format": None})

    warn_msg = re.escape(
        "`exog`: The dates of column 'date' read both day first and month "
        "first (no day is after the 12th): they were read day first, the only "
        "order in which they have a regular frequency ('D'), so '01/02/2021' "
        "is '2021-02-01' and not '2021-01-02'. If they are written month "
        "first, write them in ISO 8601 (such as '2021-01-02')."
    )
    with pytest.warns(UserWarning, match="^" + warn_msg + "$"):
        result = exog_date_format(exog_day_first, profile)

    assert result == "%d/%m/%Y"


def test_exog_date_format_DataContentError_when_dates_read_in_both_orders():
    """
    Test that dates that read both day first and month first, regular in
    both orders and with no format of the data to decide, raise a
    DataContentError with the code 'data_unreadable', the field 'exog' and
    the hint that asks for dates in ISO 8601.
    """
    exog = pd.DataFrame({
        "date": ["01/01/2021", "01/02/2021", "01/03/2021"],
        "promo": [0.0, 1.0, 0.0],
    })
    profile = profile_day_first.model_copy(update={"date_format": None})

    err_msg = re.escape(
        "`exog`: The dates of column 'date' read both day first and month "
        "first: no day is after the 12th, so '01/02/2021' may be '2021-02-01' "
        "or '2021-01-02', and both readings have a regular frequency ('MS' "
        "day first and 'D' month first), so the order is not guessed. Write "
        "them in ISO 8601, which reads one way only."
    )
    with pytest.raises(DataContentError, match="^" + err_msg + "$") as exc_info:
        exog_date_format(exog, profile)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"
    assert exc_info.value.hint == EXOG_DATES_HINT
