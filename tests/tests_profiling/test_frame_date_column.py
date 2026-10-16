# Unit test frame_date_column

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import frame_date_column

_DOTTED = ["15.01.2020", "16.01.2020", "17.01.2020"]


@pytest.mark.parametrize(
    "data, expected",
    [
        (pd.DataFrame({"datum": _DOTTED, "umsatz": [1.5, 2.5, 3.5]}), "datum"),
        (pd.DataFrame({"d": ["2020-01-15", "2020-01-16"], "y": [1, 2]}), "d"),
        (pd.DataFrame({"d": ["15/01/2020", "16-01-2020"], "y": [1, 2]}), "d"),
        (pd.DataFrame({"d": ["2020.01.15", "2020.01.16"], "y": [1, 2]}), "d"),
        (pd.DataFrame({"d": [" 15.01.2020", "16.01.2020 "], "y": [1, 2]}), "d"),
        (
            pd.DataFrame({"d": ["15.01.2020 10:00", "16.01.2020 11:00:30"]}),
            "d",
        ),
        (pd.DataFrame({"d": ["15.01.2020", None, "17.01.2020"]}), "d"),
        (pd.DataFrame({"n": ["a", "b", "c"], "d": _DOTTED}), "d"),
        (pd.DataFrame({"n": [1.5, 2.5, 3.5], "d": _DOTTED}), "d"),
        (pd.DataFrame({"d": _DOTTED, "e": ["01.02.2020"] * 3}), "d"),
    ],
    ids=[
        "dotted dates",
        "iso dates",
        "slashes and dashes",
        "year first with points",
        "spaces around",
        "with time",
        "empty cell",
        "after a column of text",
        "after a column of numbers",
        "first of two columns of dates",
    ],
)
def test_frame_date_column_output_when_column_holds_dates_written_with_numbers(
    data, expected
):
    """
    Test that the column of the dates is the first one read as text whose
    values are all dates written with numbers, as `sample_date_column` finds
    it in the first lines of the file, ignoring spaces around and the empty
    cells.
    """
    assert frame_date_column(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        pd.DataFrame({"d": [1.5, 2.5], "y": [1, 2]}),
        pd.DataFrame({"d": ["15.01.2020", "text"], "y": [1, 2]}),
        pd.DataFrame({"d": ["15 Jan 2020", "16 Jan 2020"]}),
        pd.DataFrame({"d": ["15.01.20", "16.01.20"]}),
        pd.DataFrame({"d": [None, None]}),
        pd.DataFrame({"d": pd.date_range("2020-01-15", periods=2)}),
        pd.DataFrame({"d": [20200115, 20200116]}),
        pd.DataFrame({"d": []}),
        pd.DataFrame(),
    ],
    ids=[
        "numbers",
        "one value that is not a date",
        "month name",
        "two digits year",
        "empty cells",
        "datetimes",
        "whole numbers",
        "no rows",
        "no columns",
    ],
)
def test_frame_date_column_output_is_None_when_no_column_holds_dates(data):
    """
    Test that None is returned when no column read as text has all its
    values as dates written with numbers: numbers and datetimes are not
    text, and one value that is not a date is enough.
    """
    assert frame_date_column(data) is None


def test_frame_date_column_output_when_series_id_column_given():
    """
    Test that the column of the series ids is never the dates, even when its
    values are written as dates: the next column that holds them is, and
    without `series_id_column` the ids are the first.
    """
    data = pd.DataFrame(
        {"id": _DOTTED, "date": _DOTTED, "y": [1.5, 2.5, 3.5]},
    )

    assert frame_date_column(data) == "id"
    assert frame_date_column(data, series_id_column="id") == "date"
    assert frame_date_column(data, series_id_column="other") == "id"
