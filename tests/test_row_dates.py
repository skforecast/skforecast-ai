# Unit test row_dates

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai._dates import row_dates

_dates = pd.date_range("2023-01-01", periods=3, freq="D")


@pytest.mark.parametrize(
    "data, date_column",
    [
        (pd.DataFrame({"date": _dates, "y": [1.0, 2.0, 3.0]}), "date"),
        (
            pd.DataFrame({
                "date": ["2023-01-01", "2023-01-02", "2023-01-03"],
                "y": [1.0, 2.0, 3.0],
            }),
            "date",
        ),
        (pd.DataFrame({"y": [1.0, 2.0, 3.0]}, index=_dates), None),
        (
            pd.DataFrame(
                {"y": [1.0, 2.0, 3.0]},
                index=pd.MultiIndex.from_arrays(
                    [["a", "a", "a"], _dates], names=["series", "date"]
                ),
            ),
            "date",
        ),
    ],
    ids=["datetime_column", "text_column", "datetime_index", "multiindex_level"],
)
def test_row_dates_output(data, date_column):
    """
    Test that the date of every row is read from the date column (parsed when
    it holds text), the level of a MultiIndex or the DatetimeIndex.
    """
    dates = row_dates(data, date_column)

    assert isinstance(dates, pd.DatetimeIndex)
    np.testing.assert_array_equal(dates.to_numpy(), _dates.to_numpy())


def test_row_dates_column_wins_over_index_of_same_name():
    """
    Test that a date column is used even when the index is a different
    DatetimeIndex, or has the same name as the column.
    """
    data = pd.DataFrame(
        {"date": _dates[::-1], "y": [1.0, 2.0, 3.0]},
        index=pd.DatetimeIndex(_dates, name="date"),
    )

    dates = row_dates(data, "date")

    np.testing.assert_array_equal(dates.to_numpy(), _dates[::-1].to_numpy())


@pytest.mark.parametrize(
    "names",
    [["series", "when"], ["series", None]],
    ids=["other_name", "unnamed"],
)
def test_row_dates_output_when_no_multiindex_level_matches(names):
    """
    Test that a MultiIndex without a level named as the date column has no
    dates, also when its second level has no name: profiling rejects it
    instead of reading it as the dates.
    """
    data = pd.DataFrame(
        {"y": [1.0, 2.0, 3.0]},
        index=pd.MultiIndex.from_arrays([["a", "a", "a"], _dates], names=names),
    )

    assert row_dates(data, "date") is None


def test_row_dates_output_when_text_dates_day_first():
    """
    Test that a text date column is parsed with the format of its first
    date, so '01/02/2023' is the first of February after '13/01/2023'.
    """
    data = pd.DataFrame({
        "date": ["13/01/2023", "01/02/2023", "02/02/2023"],
        "y": [1.0, 2.0, 3.0],
    })

    dates = row_dates(data, "date")

    np.testing.assert_array_equal(
        dates.to_numpy(),
        pd.to_datetime(["2023-01-13", "2023-02-01", "2023-02-02"]).to_numpy(),
    )


def test_row_dates_output_when_multiindex_level_holds_text_dates_day_first():
    """
    Test that a MultiIndex level of text dates is parsed as a date column
    is, with the format of its first date and without the warning pandas
    emits for day-first formats.
    """
    data = pd.DataFrame(
        {"y": [1.0, 2.0, 3.0]},
        index=pd.MultiIndex.from_arrays(
            [["a", "a", "a"], ["13/01/2023", "01/02/2023", "02/02/2023"]],
            names=["series", "date"],
        ),
    )

    dates = row_dates(data, "date")

    np.testing.assert_array_equal(
        dates.to_numpy(),
        pd.to_datetime(["2023-01-13", "2023-02-01", "2023-02-02"]).to_numpy(),
    )


def test_row_dates_output_when_no_datetime_source():
    """
    Test that data without a date column or a DatetimeIndex has no dates.
    """
    data = pd.DataFrame({"y": [1.0, 2.0, 3.0]})

    assert row_dates(data, None) is None
    assert row_dates(data, "missing") is None


@pytest.mark.parametrize(
    "date_format, expected",
    [
        ("%d/%m/%Y", ["2023-02-01", "2023-02-02", "2023-02-03"]),
        ("%m/%d/%Y", ["2023-01-02", "2023-02-02", "2023-03-02"]),
    ],
    ids=["day_first", "month_first"],
)
def test_row_dates_output_when_date_format_and_text_column(date_format, expected):
    """
    Test that the text of the date column is read with `date_format`, as the
    generated script reads it with `format=`: dates that read in both orders
    ('01/02/2023') are read in the one the format says.
    """
    data = pd.DataFrame({
        "date": ["01/02/2023", "02/02/2023", "03/02/2023"],
        "y": [1.0, 2.0, 3.0],
    })

    dates = row_dates(data, "date", date_format)

    np.testing.assert_array_equal(dates.to_numpy(), pd.to_datetime(expected).to_numpy())


def test_row_dates_output_when_date_format_and_integer_column():
    """
    Test that a column of integers is read as dates with `date_format`
    ('%Y%m%d' for 20230131), as the generated script reads them.
    """
    data = pd.DataFrame({"date": [20230131, 20230201, 20230202], "y": [1.0, 2.0, 3.0]})

    dates = row_dates(data, "date", "%Y%m%d")

    np.testing.assert_array_equal(
        dates.to_numpy(),
        pd.to_datetime(["2023-01-31", "2023-02-01", "2023-02-02"]).to_numpy(),
    )


def test_row_dates_output_when_date_format_and_multiindex_level_holds_text():
    """
    Test that the text of a MultiIndex level is read with `date_format` as a
    date column is.
    """
    data = pd.DataFrame(
        {"y": [1.0, 2.0, 3.0]},
        index=pd.MultiIndex.from_arrays(
            [["a", "a", "a"], ["01/02/2023", "02/02/2023", "03/02/2023"]],
            names=["series", "date"],
        ),
    )

    dates = row_dates(data, "date", "%d/%m/%Y")

    np.testing.assert_array_equal(
        dates.to_numpy(),
        pd.to_datetime(["2023-02-01", "2023-02-02", "2023-02-03"]).to_numpy(),
    )


def test_row_dates_output_when_date_format_and_dates_already_parsed():
    """
    Test that dates that are already datetimes are not read again with
    `date_format`, which a profile of text dates may still carry.
    """
    data = pd.DataFrame({"date": _dates, "y": [1.0, 2.0, 3.0]})

    dates = row_dates(data, "date", "%d/%m/%Y")

    np.testing.assert_array_equal(dates.to_numpy(), _dates.to_numpy())


def test_row_dates_ValueError_when_date_does_not_follow_date_format():
    """
    Test that a date that does not follow `date_format` raises the error of
    pandas.to_datetime, as the generated script does.
    """
    data = pd.DataFrame({"date": ["01/02/2023", "2023-02-02"], "y": [1.0, 2.0]})

    err_msg = re.escape('time data "2023-02-02" doesn\'t match format "%d/%m/%Y"')
    with pytest.raises(ValueError, match=err_msg):
        row_dates(data, "date", "%d/%m/%Y")
