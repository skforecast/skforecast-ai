# Unit test read_csv_with_dialect

import gzip
import re

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling import data_profile as data_profile_module
from skforecast_ai.profiling.csv_dialect import DIALECT_HINT, EXOG_DIALECT_HINT
from skforecast_ai.profiling.data_profile import read_csv_with_dialect

_EXPECTED = pd.DataFrame(
    {
        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "y": [1.5, 2.25, 3.0],
        "z": [10, 20, 30],
    }
)
_UNREADABLE_HINT = (
    "Pass a text file in UTF-8 separated by ',', ';' or tabulators, with a "
    "header row and the same number of fields in every row."
)


def _record_read_csv(monkeypatch) -> list:
    """
    Record the calls to `pd.read_csv` (arguments and keyword arguments) while
    it keeps reading.
    """
    calls = []
    read_csv = pd.read_csv

    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return read_csv(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", recorder)

    return calls


@pytest.mark.parametrize(
    "name, text, expected_sep, expected_decimal, kwargs",
    [
        (
            "comma.csv",
            "date,y,z\n2020-01-01,1.5,10\n2020-01-02,2.25,20\n2020-01-03,3.0,30\n",
            ",",
            ".",
            {},
        ),
        (
            "semicolon.csv",
            "date;y;z\n2020-01-01;1.5;10\n2020-01-02;2.25;20\n2020-01-03;3.0;30\n",
            ";",
            ".",
            {"sep": ";", "decimal": "."},
        ),
        (
            "semicolon_comma.csv",
            "date;y;z\n2020-01-01;1,5;10\n2020-01-02;2,25;20\n2020-01-03;3,0;30\n",
            ";",
            ",",
            {"sep": ";", "decimal": ","},
        ),
        (
            "tab.csv",
            "date\ty\tz\n2020-01-01\t1.5\t10\n2020-01-02\t2.25\t20\n"
            "2020-01-03\t3.0\t30\n",
            "\t",
            ".",
            {"sep": "\t", "decimal": "."},
        ),
        (
            "tab_comma.tsv",
            "date\ty\tz\n2020-01-01\t1,5\t10\n2020-01-02\t2,25\t20\n"
            "2020-01-03\t3,0\t30\n",
            "\t",
            ",",
            {"sep": "\t", "decimal": ","},
        ),
    ],
    ids=["comma", "semicolon", "semicolon and decimal comma", "tab", "tsv"],
)
def test_read_csv_with_dialect_output(
    tmp_path, monkeypatch, name, text, expected_sep, expected_decimal, kwargs
):
    """
    Test that the dialect of a file is detected, the data are the same for
    every dialect, and `pd.read_csv` receives only the arguments the dialect
    needs: none for ',' and '.'.
    """
    path = tmp_path / name
    path.write_text(text)
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal = read_csv_with_dialect(path)

    pd.testing.assert_frame_equal(data, _EXPECTED)
    assert (sep, decimal) == (expected_sep, expected_decimal)
    assert calls == [((path,), kwargs)]


@pytest.mark.parametrize(
    "name, sep, decimal, kwargs",
    [
        ("data.csv.gz", ",", ".", {}),
        ("data.csv.gz", ";", ",", {"sep": ";", "decimal": ","}),
        ("data.tsv.gz", "\t", ".", {"sep": "\t", "decimal": "."}),
    ],
    ids=["comma", "semicolon and decimal comma", "tab"],
)
def test_read_csv_with_dialect_output_when_file_is_gzip(
    tmp_path, monkeypatch, name, sep, decimal, kwargs
):
    """
    Test that a gzip file is decompressed to detect its dialect and read by
    pandas from its extension.
    """
    path = tmp_path / name
    _EXPECTED.to_csv(path, index=False, sep=sep, decimal=decimal)
    assert path.read_bytes()[:2] == b"\x1f\x8b"
    calls = _record_read_csv(monkeypatch)

    data, result_sep, result_decimal = read_csv_with_dialect(str(path))

    pd.testing.assert_frame_equal(data, _EXPECTED)
    assert (result_sep, result_decimal) == (sep, decimal)
    assert calls == [((str(path),), kwargs)]


def test_read_csv_with_dialect_comma_file_is_read_with_pd_read_csv_of_the_path(
    tmp_path, monkeypatch
):
    """
    Test that a comma file with decimal point, including one with commas and
    semicolons inside quoted fields, is read exactly as `pd.read_csv(path)`:
    one call, no keyword arguments.
    """
    path = tmp_path / "data.csv"
    path.write_text('date,note\n2020-01-01,"a;b,c"\n2020-01-02,"d;e"\n')
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal = read_csv_with_dialect(path)

    expected = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02"], "note": ["a;b,c", "d;e"]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal) == (",", ".")
    assert calls == [((path,), {})]


def test_read_csv_with_dialect_output_when_quoted_fields_hold_other_separators(
    tmp_path,
):
    """
    Test that a semicolon file whose quoted fields hold commas is read with
    ';' and keeps '.' as decimal mark, because the quoted text is not a
    number.
    """
    path = tmp_path / "data.csv"
    path.write_text('date;note;y\n2020-01-01;"a,b";1.5\n2020-01-02;"c,d";2.5\n')

    data, sep, decimal = read_csv_with_dialect(path)

    expected = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02"],
            "note": ["a,b", "c,d"],
            "y": [1.5, 2.5],
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal) == (";", ".")


def test_read_csv_with_dialect_output_when_header_is_one_field_short(tmp_path):
    """
    Test that a semicolon file whose header has one field less than its rows
    (the first column is then the index, as `to_csv(index_label=False)`
    writes it) is read with ';', as pandas reads the comma file.
    """
    path = tmp_path / "data.csv"
    path.write_text("y;z\n2020-01-01;1,5;10\n2020-01-02;2,5;20\n")

    data, sep, decimal = read_csv_with_dialect(path)

    expected = pd.DataFrame(
        {"y": [1.5, 2.5], "z": [10, 20]},
        index=pd.Index(["2020-01-01", "2020-01-02"]),
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal) == (";", ",")


def test_read_csv_with_dialect_output_when_single_column(tmp_path, monkeypatch):
    """
    Test that a file of one column is read as before, with ',' and '.'.
    """
    path = tmp_path / "data.csv"
    path.write_text("y\n1\n2\n3\n")
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal = read_csv_with_dialect(path)

    pd.testing.assert_frame_equal(data, pd.DataFrame({"y": [1, 2, 3]}))
    assert (sep, decimal) == (",", ".")
    assert calls == [((path,), {})]


@pytest.mark.parametrize(
    "sep, decimal, expected_sep, expected_decimal",
    [
        (";", None, ";", ","),
        (None, ",", ";", ","),
        (";", ",", ";", ","),
    ],
    ids=["sep given", "decimal given", "both given"],
)
def test_read_csv_with_dialect_output_when_sep_or_decimal_given(
    tmp_path, sep, decimal, expected_sep, expected_decimal
):
    """
    Test that the separator and the decimal mark given by the caller are
    used, and the one not given is detected.
    """
    path = tmp_path / "data.csv"
    _EXPECTED.to_csv(path, index=False, sep=";", decimal=",")

    data, result_sep, result_decimal = read_csv_with_dialect(
        path, sep=sep, decimal=decimal
    )

    pd.testing.assert_frame_equal(data, _EXPECTED)
    assert (result_sep, result_decimal) == (expected_sep, expected_decimal)


def test_read_csv_with_dialect_does_not_read_the_file_twice_when_both_given(
    tmp_path, monkeypatch
):
    """
    Test that the start of the file is not sampled when the caller gives the
    separator and the decimal mark.
    """
    path = tmp_path / "data.csv"
    _EXPECTED.to_csv(path, index=False, sep=";", decimal=",")
    sampled = []
    monkeypatch.setattr(
        data_profile_module, "read_sample", lambda path: sampled.append(path)
    )

    read_csv_with_dialect(path, sep=";", decimal=",")

    assert sampled == []


def test_read_csv_with_dialect_gives_the_given_sep_even_when_it_does_not_fit(
    tmp_path,
):
    """
    Test that a separator given by the caller is not corrected: a
    semicolon file read with ',' is one column named after the header.
    """
    path = tmp_path / "data.csv"
    path.write_text("date;y\n2020-01-01;1.5\n")

    data, sep, decimal = read_csv_with_dialect(path, sep=",")

    assert list(data.columns) == ["date;y"]
    assert (sep, decimal) == (",", ".")


@pytest.mark.parametrize(
    "sep, decimal, message, field",
    [
        (
            "|",
            None,
            "`sep` must be ',', ';' or a tabulator ('\\t'), got '|'.",
            "sep",
        ),
        (
            None,
            ":",
            "`decimal` must be '.' or ',', got ':'.",
            "decimal",
        ),
        (
            ",",
            ",",
            "`decimal` cannot be ',' when `sep` is ',': the same character "
            "would separate the fields and the decimals.",
            "decimal",
        ),
    ],
    ids=["invalid sep", "invalid decimal", "decimal comma with sep comma"],
)
def test_read_csv_with_dialect_InvalidInputError_when_sep_or_decimal_not_valid(
    tmp_path, sep, decimal, message, field
):
    """
    Test that a separator or a decimal mark that is not valid raises an
    InvalidInputError naming the argument, before the file is looked at.
    """
    missing = tmp_path / "missing.csv"

    with pytest.raises(InvalidInputError, match=re.escape(message)) as exc_info:
        read_csv_with_dialect(missing, sep=sep, decimal=decimal)

    assert exc_info.value.field == field


@pytest.mark.parametrize(
    "field, hint",
    [("data", DIALECT_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_read_csv_with_dialect_InvalidInputError_when_separator_is_ambiguous(
    tmp_path, field, hint
):
    """
    Test that a file that reads with ',' and with ';' raises an
    InvalidInputError with the code 'data_unreadable', the path in the
    message, the argument that named the file and its hint.
    """
    path = tmp_path / "data.csv"
    path.write_text("a,b;c\n1,2;3\n")

    err_msg = re.escape(
        f"The separator of the CSV file '{path}' cannot be told: its header "
        f"reads with ',' (2 columns) and ';' (2 columns)."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        read_csv_with_dialect(path, field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


@pytest.mark.parametrize(
    "field, hint",
    [("data", DIALECT_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_read_csv_with_dialect_InvalidInputError_when_decimal_is_ambiguous(
    tmp_path, field, hint
):
    """
    Test that a file with numbers written as '1,5' and as '2.5' raises an
    InvalidInputError with the code 'data_unreadable', an example of each
    mark, the argument that named the file and its hint.
    """
    path = tmp_path / "data.csv"
    path.write_text("date;y;z\n2020-01-01;1,5;2.5\n")

    err_msg = re.escape(
        f"The decimal mark of the CSV file '{path}' cannot be told: it holds "
        f"numbers written with ',' (such as '1,5') and with '.' (such as "
        f"'2.5')."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        read_csv_with_dialect(path, field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


@pytest.mark.parametrize(
    "name, content, reason",
    [
        ("empty.csv", b"", "No columns to parse from file"),
        (
            "latin1.csv",
            "date;x;name\n2020-01-01;1;caf\xe9\n".encode("latin-1"),
            "'utf-8' codec can't decode byte 0xe9 in position 28: invalid "
            "continuation byte",
        ),
        (
            "damaged.csv.gz",
            b"this is not gzip at all",
            "Not a gzipped file (b'th')",
        ),
        (
            "cut.csv.gz",
            gzip.compress(b"date;y\n" + b"2020-01-01;1,5\n" * 5000)[:40],
            "Compressed file ended before the end-of-stream marker was reached",
        ),
    ],
    ids=["empty", "latin-1", "damaged gzip", "truncated gzip"],
)
@pytest.mark.parametrize("field", ["data", "exog"])
def test_read_csv_with_dialect_InvalidInputError_when_file_unreadable(
    tmp_path, name, content, reason, field
):
    """
    Test that an empty, not UTF-8 or damaged compressed file raises an
    InvalidInputError (a ValueError) with the code 'data_unreadable', the
    reason of the first line, the argument that named the file and the hint
    that names the three separators.
    """
    path = tmp_path / name
    path.write_bytes(content)

    err_msg = re.escape(f"The CSV file '{path}' could not be read: {reason}")
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_with_dialect(path, field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == _UNREADABLE_HINT
