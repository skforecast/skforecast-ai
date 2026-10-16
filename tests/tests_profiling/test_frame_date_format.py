# Unit test frame_date_format

import re

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import DAYFIRST_FRAME_HINT, frame_date_format

_DAY_FIRST = ["13/01/2020", "14/01/2020", "01/02/2020"]
_AMBIGUOUS = ["01/01/2020", "01/02/2020", "01/03/2020"]


@pytest.mark.parametrize(
    "dates, expected",
    [
        (_DAY_FIRST, "%d/%m/%Y"),
        (["13.01.2020", "14.01.2020"], "%d.%m.%Y"),
        (["13/01/2020 10:00", "14/01/2020 11:00"], "%d/%m/%Y %H:%M"),
        (["01/13/2020", "01/14/2020"], None),
        (["2020-01-13", "2020-01-14"], None),
        (["13 Jan 2020", "14 Jan 2020"], None),
        ([20200113, 20200114], "%Y%m%d"),
        (pd.date_range("2020-01-13", periods=2), None),
        ([1.5, 2.5], None),
    ],
    ids=[
        "day first",
        "day first with points",
        "day first with time",
        "month first",
        "iso",
        "month name",
        "whole numbers of eight digits",
        "datetimes",
        "numbers",
    ],
)
def test_frame_date_format_output(dates, expected):
    """
    Test that the format of the dates of a DataFrame passed in memory is the
    day-first one for day-first text, '%Y%m%d' for whole numbers of eight
    digits, and None when the script reads the dates without one (month
    first, ISO, month names, dates already parsed, numbers).
    """
    data = pd.DataFrame({"date": dates})

    assert frame_date_format(data, "date") == expected


@pytest.mark.parametrize(
    "date_format, expected",
    [("%d/%m/%Y", "%d/%m/%Y"), ("%m/%d/%Y", "%m/%d/%Y")],
    ids=lambda dt: f"date_format: {dt}",
)
def test_frame_date_format_output_when_date_format_decides_ambiguous_dates(
    date_format, expected
):
    """
    Test that text dates that read day first and month first take the order
    of the format of the profile given, which is then the format the script
    reads them with.
    """
    data = pd.DataFrame({"date": _AMBIGUOUS, "y": [1.0, 2.0, 3.0]})

    assert frame_date_format(data, "date", date_format) == expected


@pytest.mark.parametrize(
    "dates",
    [pd.date_range("2020-01-13", periods=3), ["2020-01-13", "2020-01-14"]],
    ids=["datetimes", "iso"],
)
def test_frame_date_format_output_is_None_when_dates_need_no_format(dates):
    """
    Test that the format of the profile given is ignored for dates the script
    reads without one, because it runs on the DataFrame as it was passed:
    dates already parsed and text in ISO 8601.
    """
    data = pd.DataFrame({"date": dates})

    assert frame_date_format(data, "date", "%d/%m/%Y") is None


def test_frame_date_format_output_when_dates_are_a_multiindex_level():
    """
    Test that the dates held by a level of a MultiIndex are read as a column.
    """
    data = pd.DataFrame(
        {"y": [1.0, 2.0, 3.0]},
        index=pd.MultiIndex.from_arrays(
            [["a", "a", "a"], _DAY_FIRST], names=["id", "date"]
        ),
    )

    assert frame_date_format(data, "date") == "%d/%m/%Y"


def test_frame_date_format_output_is_None_when_no_date_column():
    """
    Test that None is returned when the data is not a DataFrame, there is no
    date column, the date column is not in the data or its name is repeated
    (left to the checks that report it).
    """
    data = pd.DataFrame({"date": _DAY_FIRST, "y": [1.0, 2.0, 3.0]})
    repeated = pd.DataFrame(
        [["13/01/2020", "14/01/2020"]], columns=["date", "date"]
    )

    assert frame_date_format(data, None) is None
    assert frame_date_format(data, "missing") is None
    assert frame_date_format(data["date"], "date") is None
    assert frame_date_format(["13/01/2020"], "date") is None
    assert frame_date_format(repeated, "date") is None


def test_frame_date_format_InvalidInputError_when_dates_read_in_both_orders():
    """
    Test that text dates that read day first and month first, with no format
    of a profile to decide, raise an InvalidInputError that asks for the
    dates to be converted, with the default code, the field 'data' and the
    hint of a DataFrame: the order is never guessed.
    """
    data = pd.DataFrame({"date": _AMBIGUOUS, "y": [1.0, 2.0, 3.0]})

    err_msg = re.escape(
        "The dates of column 'date' read both day first and month first: no "
        "day is after the 12th, so '01/02/2020' may be '2020-02-01' or "
        "'2020-01-02', and the order is not guessed: convert them with "
        "pandas.to_datetime(..., format='%d/%m/%Y') or format='%m/%d/%Y' "
        "before passing the data."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        frame_date_format(data, "date")

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == DAYFIRST_FRAME_HINT


def test_frame_date_format_does_not_modify_input():
    """
    Test that the DataFrame given keeps its text dates.
    """
    data = pd.DataFrame({"date": _DAY_FIRST, "y": [1.0, 2.0, 3.0]})
    data_copy = data.copy()

    frame_date_format(data, "date")

    pd.testing.assert_frame_equal(data, data_copy)
