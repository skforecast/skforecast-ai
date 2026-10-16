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
