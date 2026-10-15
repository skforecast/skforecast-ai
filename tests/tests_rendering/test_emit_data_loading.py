# Unit test _emit_data_loading

import pytest

from skforecast_ai.rendering import render_forecast_single_series
from skforecast_ai.rendering._helpers import _emit_data_loading

from .fixtures_rendering import plan_single_predict_exog, profile_single


def _lines(profile, **kwargs) -> list[str]:
    """
    Return the lines `_emit_data_loading` appends for a profile, without the
    empty line that ends them.
    """
    lines: list[str] = []
    _emit_data_loading(lines, profile, **kwargs)
    assert lines[-1] == ""

    return lines[:-1]


@pytest.mark.parametrize(
    "sep, decimal, call",
    [
        (";", ",", "pd.read_csv('eu.csv', sep=';', decimal=',')"),
        (";", ".", "pd.read_csv('eu.csv', sep=';', decimal='.')"),
        ("\t", ".", "pd.read_csv('eu.csv', sep='\\t', decimal='.')"),
        ("\t", ",", "pd.read_csv('eu.csv', sep='\\t', decimal=',')"),
        (",", ".", "pd.read_csv('eu.csv')"),
    ],
    ids=["semicolon and comma", "semicolon and dot", "tab", "tab and comma", "default"],
)
def test_emit_data_loading_output_when_csv_has_a_dialect(sep, decimal, call):
    """
    Test that the call to `pd.read_csv` names `sep` and `decimal` when the
    file is not written with ',' and '.', and names none for the default.
    """
    profile = profile_single.model_copy(
        update={"data_path": "eu.csv", "csv_sep": sep, "csv_decimal": decimal}
    )

    result = _lines(profile)

    assert result == ["# Load data", f"data = {call}"]


def test_emit_data_loading_output_when_dialect_and_index_is_read():
    """
    Test that the dialect goes before `index_col` and `parse_dates` when the
    index is stored in the file.
    """
    profile = profile_single.model_copy(
        update={
            "data_path": "eu.csv",
            "csv_sep": ";",
            "csv_decimal": ",",
            "date_column": None,
        }
    )

    result = _lines(profile)

    assert result == [
        "# Load data",
        "data = pd.read_csv('eu.csv', sep=';', decimal=',', index_col=0, "
        "parse_dates=True)",
    ]


def test_emit_data_loading_output_when_dialect_and_long_format():
    """
    Test that the dialect is named also for the long format.
    """
    profile = profile_single.model_copy(
        update={"data_path": "eu.csv", "csv_sep": "\t", "csv_decimal": "."}
    )

    result = _lines(profile, long_format=True)

    assert result[-1] == "data = pd.read_csv('eu.csv', sep='\\t', decimal='.')"


def test_emit_data_loading_output_is_unchanged_for_the_default_dialect():
    """
    Test that a profile with the default dialect is rendered byte for byte as
    before: a path, and the placeholder that stands for data in memory.
    """
    path = profile_single.model_copy(update={"data_path": "sales.csv"})
    placeholder = profile_single

    assert _lines(path) == ["# Load data", "data = pd.read_csv('sales.csv')"]
    assert _lines(placeholder) == ["# Load data", "data = pd.read_csv('data.csv')"]


@pytest.mark.parametrize(
    "date_column, expected",
    [
        (None, "data = pd.read_csv('data.csv', index_col=0, parse_dates=True)"),
        ("date", "data = pd.read_csv('data.csv')"),
    ],
    ids=["index stored", "date column"],
)
def test_emit_data_loading_names_no_dialect_for_the_placeholder_path(
    date_column, expected
):
    """
    Test that data in memory (the placeholder path 'data.csv', saved with
    `to_csv()`) is read without `sep` and `decimal` even when the profile
    holds another dialect.
    """
    profile = profile_single.model_copy(
        update={"csv_sep": ";", "csv_decimal": ",", "date_column": date_column}
    )

    assert _lines(profile)[-1] == expected


def test_emit_data_loading_names_no_dialect_for_the_future_exog_file():
    """
    Test that `exog_future.csv` is read without `sep` and `decimal` whatever
    the dialect of the data, because it is the frame saved with `to_csv()`.
    """
    profile = profile_single.model_copy(
        update={"data_path": "eu.csv", "csv_sep": ";", "csv_decimal": ","}
    )

    result = _lines(
        profile, var="exog_future", path="exog_future.csv", comment="# Future exog"
    )

    assert result[0] == "# Future exog"
    assert result[1].startswith("exog_future = pd.read_csv('exog_future.csv'")
    assert "sep=" not in result[1]
    assert "decimal=" not in result[1]


def test_emit_data_loading_in_a_full_script_with_future_exog():
    """
    Test that the script of a prediction with exogenous variables reads the
    data with the dialect of the profile and `exog_future.csv` as before.
    """
    profile = profile_single.model_copy(
        update={"data_path": "eu.csv", "csv_sep": ";", "csv_decimal": ","}
    )

    result = render_forecast_single_series(plan_single_predict_exog, profile)

    assert "data = pd.read_csv('eu.csv', sep=';', decimal=',')\n" in result.data_loading
    assert "exog_future = pd.read_csv('exog_future.csv')\n" in result.data_loading
    assert result.full_script.count("sep=';'") == 1


@pytest.mark.parametrize(
    "date_column, long_format, call",
    [
        (
            "date",
            False,
            "data = pd.read_csv('eu.csv', sep=';', decimal=',', thousands='.')",
        ),
        (
            None,
            False,
            "data = pd.read_csv('eu.csv', sep=';', decimal=',', thousands='.', "
            "index_col=0, parse_dates=True)",
        ),
        (
            "date",
            True,
            "data = pd.read_csv('eu.csv', sep=';', decimal=',', thousands='.')",
        ),
    ],
    ids=["date column", "index stored", "long format"],
)
def test_emit_data_loading_output_when_csv_has_thousands(
    date_column, long_format, call
):
    """
    Test that the call to `pd.read_csv` names `thousands` after `sep` and
    `decimal` when the file separates thousands with '.', before
    `index_col` and `parse_dates` when the index is stored in the file.
    """
    profile = profile_single.model_copy(
        update={
            "data_path": "eu.csv",
            "csv_sep": ";",
            "csv_decimal": ",",
            "csv_thousands": ".",
            "date_column": date_column,
        }
    )

    result = _lines(profile, long_format=long_format)

    assert result == ["# Load data", call]


def test_emit_data_loading_names_no_thousands_for_the_placeholder_or_exog_file():
    """
    Test that data in memory (the placeholder path) and `exog_future.csv`,
    the frames saved with `to_csv()`, are read without `thousands` whatever
    the thousands separator of the profile.
    """
    profile = profile_single.model_copy(
        update={"csv_sep": ";", "csv_decimal": ",", "csv_thousands": "."}
    )
    with_path = profile.model_copy(update={"data_path": "eu.csv"})

    placeholder = _lines(profile)
    exog = _lines(
        with_path, var="exog_future", path="exog_future.csv", comment="# Future exog"
    )

    assert placeholder == ["# Load data", "data = pd.read_csv('data.csv')"]
    assert exog[1].startswith("exog_future = pd.read_csv('exog_future.csv'")
    assert "thousands=" not in exog[1]


def test_emit_data_loading_in_a_full_script_with_thousands_and_future_exog():
    """
    Test that the script of a prediction with exogenous variables reads the
    data with the thousands separator of the profile, and only the data.
    """
    profile = profile_single.model_copy(
        update={
            "data_path": "eu.csv",
            "csv_sep": ";",
            "csv_decimal": ",",
            "csv_thousands": ".",
        }
    )

    result = render_forecast_single_series(plan_single_predict_exog, profile)

    assert (
        "data = pd.read_csv('eu.csv', sep=';', decimal=',', thousands='.')\n"
        in result.data_loading
    )
    assert "exog_future = pd.read_csv('exog_future.csv')\n" in result.data_loading
    assert result.full_script.count("thousands='.'") == 1
