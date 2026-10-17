# Unit test csv_read_kwargs

import pytest

from skforecast_ai.profiling.data_profile import csv_read_kwargs


@pytest.mark.parametrize(
    "sep, decimal, expected",
    [
        (",", ".", {}),
        (";", ".", {"sep": ";", "decimal": "."}),
        (";", ",", {"sep": ";", "decimal": ","}),
        ("\t", ".", {"sep": "\t", "decimal": "."}),
        ("\t", ",", {"sep": "\t", "decimal": ","}),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_csv_read_kwargs_output(sep, decimal, expected):
    """
    Test that no argument is returned for the default dialect (so the file is
    read with exactly `pd.read_csv(path)`), and both `sep` and `decimal`
    otherwise.
    """
    assert csv_read_kwargs(sep, decimal) == expected


@pytest.mark.parametrize(
    "sep, decimal, thousands, expected",
    [
        (",", ".", None, {}),
        (";", ",", None, {"sep": ";", "decimal": ","}),
        (";", ",", ".", {"sep": ";", "decimal": ",", "thousands": "."}),
        ("\t", ",", ".", {"sep": "\t", "decimal": ",", "thousands": "."}),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_csv_read_kwargs_output_when_thousands(sep, decimal, thousands, expected):
    """
    Test that `thousands` is returned only when it is not None, next to `sep`
    and `decimal`, and that no argument is returned for the default dialect
    without thousands separator.
    """
    assert csv_read_kwargs(sep, decimal, thousands) == expected


@pytest.mark.parametrize(
    "sep, decimal, thousands, expected",
    [
        (",", ".", None, {"dtype": {"store": str}}),
        (";", ".", None, {"sep": ";", "decimal": ".", "dtype": {"store": str}}),
        (";", ",", None, {"sep": ";", "decimal": ",", "dtype": {"store": str}}),
        (
            ";",
            ",",
            ".",
            {"sep": ";", "decimal": ",", "thousands": ".", "dtype": {"store": str}},
        ),
        (
            "\t",
            ",",
            ".",
            {"sep": "\t", "decimal": ",", "thousands": ".", "dtype": {"store": str}},
        ),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_csv_read_kwargs_output_when_series_id_column(
    sep, decimal, thousands, expected
):
    """
    Test that the column of series ids is read as text (`dtype`) whatever the
    dialect, including the default one, where nothing else is needed, and
    next to `sep`, `decimal` and `thousands` otherwise.
    """
    result = csv_read_kwargs(sep, decimal, thousands, series_id_column="store")

    assert result == expected


@pytest.mark.parametrize(
    "sep, decimal, thousands, series_id_column, expected",
    [
        (
            ";",
            ",",
            ".",
            None,
            {"sep": ";", "decimal": ",", "thousands": ".", "dtype": {"date": str}},
        ),
        (
            "\t",
            ",",
            ".",
            None,
            {"sep": "\t", "decimal": ",", "thousands": ".", "dtype": {"date": str}},
        ),
        (
            ";",
            ",",
            ".",
            "store",
            {
                "sep": ";",
                "decimal": ",",
                "thousands": ".",
                "dtype": {"store": str, "date": str},
            },
        ),
        (
            ";",
            ",",
            ".",
            "date",
            {"sep": ";", "decimal": ",", "thousands": ".", "dtype": {"date": str}},
        ),
    ],
    ids=[
        "semicolon",
        "tabulator",
        "series ids",
        "series ids that are the date column",
    ],
)
def test_csv_read_kwargs_output_when_thousands_and_date_column(
    sep, decimal, thousands, series_id_column, expected
):
    """
    Test that the column of the dates is read as text (`dtype`) when there is
    a thousands separator, next to the column of series ids when there is
    one (once if they are the same column), because with '.' pandas would
    read '15.01.2020' as the number 15012020.
    """
    result = csv_read_kwargs(
                 sep, decimal, thousands, series_id_column, date_column="date"
             )

    assert result == expected


@pytest.mark.parametrize(
    "sep, decimal, series_id_column, expected",
    [
        (",", ".", None, {}),
        (";", ",", None, {"sep": ";", "decimal": ","}),
        (",", ".", "store", {"dtype": {"store": str}}),
        (";", ",", "store", {"sep": ";", "decimal": ",", "dtype": {"store": str}}),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_csv_read_kwargs_date_column_is_ignored_when_no_thousands(
    sep, decimal, series_id_column, expected
):
    """
    Test that the column of the dates is not read as text without a thousands
    separator, where pandas does not drop the points of '15.01.2020': the
    arguments are those of a call without `date_column`, so the default
    dialect is still read with exactly `pd.read_csv(path)`.
    """
    result = csv_read_kwargs(
                 sep, decimal, None, series_id_column, date_column="date"
             )

    assert result == expected



@pytest.mark.parametrize(
    "sep, decimal, thousands, encoding, expected",
    [
        (",", ".", None, "utf-8", {}),
        (",", ".", None, "cp1252", {"encoding": "cp1252"}),
        (
            ";", ",", ".", "cp1252",
            {"sep": ";", "decimal": ",", "thousands": ".", "encoding": "cp1252"},
        ),
    ],
    ids=["utf-8", "cp1252", "cp1252 with dialect"],
)
def test_csv_read_kwargs_output_when_encoding(
    sep, decimal, thousands, encoding, expected
):
    """
    Test that `encoding` is returned only when it is not UTF-8, the default
    of `pd.read_csv`, after the dialect, so a UTF-8 file is read as before.
    """
    assert csv_read_kwargs(sep, decimal, thousands, encoding=encoding) == expected
