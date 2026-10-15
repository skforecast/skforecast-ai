# Unit test read_csv_with_dialect

import gzip
import re

import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling import data_profile as data_profile_module
from skforecast_ai.profiling.csv_dialect import (
    DIALECT_HINT,
    DOTTED_VALUES_HINT,
    EXOG_DIALECT_HINT,
    THOUSANDS_HINT,
)
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

    data, sep, decimal, thousands = read_csv_with_dialect(path)

    pd.testing.assert_frame_equal(data, _EXPECTED)
    assert (sep, decimal, thousands) == (expected_sep, expected_decimal, None)
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

    data, result_sep, result_decimal, thousands = read_csv_with_dialect(str(path))

    pd.testing.assert_frame_equal(data, _EXPECTED)
    assert (result_sep, result_decimal, thousands) == (sep, decimal, None)
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

    data, sep, decimal, thousands = read_csv_with_dialect(path)

    expected = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02"], "note": ["a;b,c", "d;e"]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (",", ".", None)
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

    data, sep, decimal, thousands = read_csv_with_dialect(path)

    expected = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02"],
            "note": ["a,b", "c,d"],
            "y": [1.5, 2.5],
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ".", None)


def test_read_csv_with_dialect_output_when_header_is_one_field_short(tmp_path):
    """
    Test that, with `index_first`, a semicolon file whose header has one
    field less than its rows (the first column is then the index, as
    `to_csv(index_label=False)` writes it) is read with ';', as pandas reads
    the comma file.
    """
    path = tmp_path / "data.csv"
    path.write_text("y;z\n2020-01-01;1,5;10\n2020-01-02;2,5;20\n")

    data, sep, decimal, thousands = read_csv_with_dialect(path, index_first=True)

    expected = pd.DataFrame(
        {"y": [1.5, 2.5], "z": [10, 20]},
        index=pd.Index(["2020-01-01", "2020-01-02"]),
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", None)


@pytest.mark.parametrize(
    "text, index_first, fields",
    [
        ("y;z\n2020-01-01;1,5;10\n2020-01-02;2,5;20\n", False, 3),
        ("y;z\n2020-01-01;1,5;10\n2020-01-02;2,5\n", True, 3),
    ],
    ids=["header one field short", "field too many in the first row only"],
)
def test_read_csv_with_dialect_InvalidInputError_when_first_row_longer_than_header(
    tmp_path, text, index_first, fields
):
    """
    Test that a header one field short raises with the code 'data_unreadable'
    without `index_first`, before the decimal mark is looked up, and that a
    field too many only in the first row raises with it.
    """
    path = tmp_path / "data.csv"
    path.write_text(text)

    err_msg = re.escape(
        f"The CSV file '{path}' could not be read: its header has 2 fields and "
        f"its first row {fields}, so the first column would be read as the row "
        f"labels and every other column would move one place (a field too many "
        f"in the first row, or a header without a name for the first column)."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        read_csv_with_dialect(path, index_first=index_first)

    assert exc_info.value.code == "data_unreadable"


def test_read_csv_with_dialect_output_when_single_column(tmp_path, monkeypatch):
    """
    Test that a file of one column is read as before, with ',' and '.'.
    """
    path = tmp_path / "data.csv"
    path.write_text("y\n1\n2\n3\n")
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands = read_csv_with_dialect(path)

    pd.testing.assert_frame_equal(data, pd.DataFrame({"y": [1, 2, 3]}))
    assert (sep, decimal, thousands) == (",", ".", None)
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

    data, result_sep, result_decimal, thousands = read_csv_with_dialect(
        path, sep=sep, decimal=decimal
    )

    pd.testing.assert_frame_equal(data, _EXPECTED)
    assert (result_sep, result_decimal, thousands) == (
        expected_sep, expected_decimal, None
    )


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

    data, sep, decimal, thousands = read_csv_with_dialect(path, sep=",")

    assert list(data.columns) == ["date;y"]
    assert (sep, decimal, thousands) == (",", ".", None)


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
    "sep, decimal, thousands, message",
    [
        (
            ";",
            ",",
            ",",
            "`thousands` must be '.', got ','.",
        ),
        (
            ",",
            None,
            ".",
            "`thousands` cannot be '.' when `sep` is ',': '.' separates the "
            "thousands where ',' is the decimal mark, which cannot also "
            "separate the fields.",
        ),
        (
            ";",
            ".",
            ".",
            "`thousands` cannot be '.' when `decimal` is '.': the same "
            "character would separate the thousands and the decimals.",
        ),
    ],
    ids=["invalid thousands", "sep comma", "decimal point"],
)
def test_read_csv_with_dialect_InvalidInputError_when_thousands_not_valid(
    tmp_path, sep, decimal, thousands, message
):
    """
    Test that a thousands separator that is not valid, or that does not fit
    the separator or the decimal mark given, raises an InvalidInputError
    naming the argument 'thousands', before the file is looked at.
    """
    missing = tmp_path / "missing.csv"

    with pytest.raises(InvalidInputError, match=re.escape(message)) as exc_info:
        read_csv_with_dialect(missing, sep=sep, decimal=decimal, thousands=thousands)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "thousands"


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


@pytest.mark.parametrize(
    "kwargs",
    [{"thousands": "."}, {"decimal": ","}],
    ids=lambda dt: f"{dt}",
)
def test_read_csv_with_dialect_InvalidInputError_when_unreadable_and_dialect_given(
    tmp_path, kwargs
):
    """
    Test that a file whose start cannot be read is reported as unreadable
    when the caller gives a thousands separator or a decimal mark ',' and no
    separator, instead of as an argument that does not fit the default
    separator ','.
    """
    path = tmp_path / "latin1.csv"
    path.write_bytes("date;x;name\n2020-01-01;1;caf\xe9\n".encode("latin-1"))

    err_msg = re.escape(
        f"The CSV file '{path}' could not be read: 'utf-8' codec can't decode "
        f"byte 0xe9 in position 28: invalid continuation byte"
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_with_dialect(path, **kwargs)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"


def test_read_csv_with_dialect_decimal_comma_after_the_sample(tmp_path, monkeypatch):
    """
    Test that a ';' file whose numbers with ',' only come after the lines the
    dialect is told from is read with ',' as decimal mark, so the column is
    numeric and not text.
    """
    monkeypatch.setattr(
        "skforecast_ai.profiling.csv_dialect.SAMPLE_BYTES", 40
    )
    path = tmp_path / "late.csv"
    path.write_text(
        "date;y;x\n2020-01-01;1;10\n2020-01-02;2;20\n2020-01-03;3;2,5\n"
    )

    data, sep, decimal, thousands = read_csv_with_dialect(path)

    expected = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "y": [1, 2, 3],
            "x": [10.0, 20.0, 2.5],
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", None)


def test_read_csv_with_dialect_keeps_decimal_given_after_the_sample(tmp_path):
    """
    Test that a decimal mark given by the caller is kept when a column read
    as text holds numbers written with ','.
    """
    path = tmp_path / "given.csv"
    path.write_text("date;y;x\n2020-01-01;1;10\n2020-01-02;2;2,5\n")

    data, sep, decimal, thousands = read_csv_with_dialect(path, decimal=".")

    assert (sep, decimal, thousands) == (";", ".", None)
    assert data["x"].tolist() == ["10", "2,5"]


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "date;y\n2020-01-01;870\n2020-01-02;1.020\n2020-01-03;2.015\n",
            pd.DataFrame(
                {
                    "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
                    "y": [870, 1020, 2015],
                }
            ),
        ),
        (
            "date;y\n2020-01-01;1.705,11\n2020-01-02;2.870,5\n"
            "2020-01-03;1.234.567\n",
            pd.DataFrame(
                {
                    "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
                    "y": [1705.11, 2870.5, 1234567.0],
                }
            ),
        ),
        (
            "date;y\n2020-01-01;-870\n2020-01-02;-1.020\n",
            pd.DataFrame(
                {"date": ["2020-01-01", "2020-01-02"], "y": [-870, -1020]}
            ),
        ),
    ],
    ids=["whole numbers", "decimals after a comma", "negative numbers"],
)
def test_read_csv_with_dialect_output_when_thousands_detected(
    tmp_path, monkeypatch, text, expected
):
    """
    Test that a ';' file whose numbers have '.' between thousands is read
    with ',' as decimal mark and '.' as thousands separator, in one call to
    `pd.read_csv`, and its numbers are read as numbers.
    """
    path = tmp_path / "thousands.csv"
    path.write_text(text)
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands = read_csv_with_dialect(path)

    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert calls == [((path,), {"sep": ";", "decimal": ",", "thousands": "."})]


def test_read_csv_with_dialect_output_when_thousands_detected_in_tab_file(tmp_path):
    """
    Test that a file separated by tabulators whose numbers have '.' between
    thousands and a ',' for the decimals is read with ',' and '.'.
    """
    path = tmp_path / "thousands.tsv"
    path.write_text("date\ty\n2020-01-01\t1.705,11\n2020-01-02\t2.870,5\n")

    data, sep, decimal, thousands = read_csv_with_dialect(path)

    expected = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02"], "y": [1705.11, 2870.5]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == ("\t", ",", ".")


def test_read_csv_with_dialect_output_when_decimal_comma_given_and_thousands(
    tmp_path, monkeypatch
):
    """
    Test that a file read with the separator and the decimal mark given (no
    sample is read) is read again with '.' as thousands separator when a
    column of text holds numbers such as '1.705'.
    """
    path = tmp_path / "given.csv"
    path.write_text("date;y\n2020-01-01;1.705\n2020-01-02;1.870\n")
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands = read_csv_with_dialect(
        path, sep=";", decimal=","
    )

    expected = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02"], "y": [1705, 1870]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert calls == [
        ((path,), {"sep": ";", "decimal": ","}),
        ((path,), {"sep": ";", "decimal": ",", "thousands": "."}),
    ]


def test_read_csv_with_dialect_thousands_after_the_sample(tmp_path, monkeypatch):
    """
    Test that a ';' file whose numbers with '.' between thousands only come
    after the lines the dialect is told from, in a column of whole numbers,
    is read with ',' as decimal mark and '.' as thousands separator, so the
    column is numeric and not text.
    """
    monkeypatch.setattr(
        "skforecast_ai.profiling.csv_dialect.SAMPLE_BYTES", 40
    )
    path = tmp_path / "late.csv"
    path.write_text(
        "date;y;x\n2020-01-01;1;10\n2020-01-02;2;20\n2020-01-03;3;1.705,11\n"
    )
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands = read_csv_with_dialect(path)

    expected = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "y": [1, 2, 3],
            "x": [10.0, 20.0, 1705.11],
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert calls == [
        ((path,), {"sep": ";", "decimal": "."}),
        ((path,), {"sep": ";", "decimal": ","}),
        ((path,), {"sep": ";", "decimal": ",", "thousands": "."}),
    ]


def test_read_csv_with_dialect_InvalidInputError_when_dotted_values_after_the_sample(
    tmp_path, monkeypatch
):
    """
    Test that a number with '.' between thousands after the lines the dialect
    is told from, in a file with dates such as '15.01.2020', raises an
    InvalidInputError with the code 'data_unreadable' and the hint of the
    values, because pandas would read the dates as numbers without the '.'.
    """
    monkeypatch.setattr(
        "skforecast_ai.profiling.csv_dialect.SAMPLE_BYTES", 40
    )
    path = tmp_path / "late.csv"
    path.write_text(
        "date;y;x\n15.01.2020;1;10\n16.01.2020;2;20\n17.01.2020;3;1.705,11\n"
    )

    err_msg = re.escape(
        f"The CSV file '{path}' cannot be read: it holds numbers with '.' "
        f"between the thousands (such as '1.705,11') and values with a '.' "
        f"that does not separate thousands (such as '15.01.2020'), which "
        f"pandas would read as numbers without it."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_with_dialect(path)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == DOTTED_VALUES_HINT


@pytest.mark.parametrize("sep", [None, ";"], ids=["sep detected", "sep given"])
def test_read_csv_with_dialect_decimal_is_comma_when_thousands_given(
    tmp_path, monkeypatch, sep
):
    """
    Test that '.' given as thousands separator makes ',' the decimal mark,
    which is not given, and that the file is read once with the three.
    """
    path = tmp_path / "given.csv"
    path.write_text("date;y\n2020-01-01;870\n2020-01-02;1.020\n")
    calls = _record_read_csv(monkeypatch)

    data, result_sep, decimal, thousands = read_csv_with_dialect(
        path, sep=sep, thousands="."
    )

    expected = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02"], "y": [870, 1020]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (result_sep, decimal, thousands) == (";", ",", ".")
    assert calls == [((path,), {"sep": ";", "decimal": ",", "thousands": "."})]


@pytest.mark.parametrize(
    "field, hint",
    [("data", DOTTED_VALUES_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_read_csv_with_dialect_InvalidInputError_when_thousands_given_and_dotted_values(
    tmp_path, monkeypatch, field, hint
):
    """
    Test that a file with a value such as '0.5' is not read with '.' as
    thousands separator given by the caller, because pandas would read it as
    5: it raises an InvalidInputError with the code 'data_unreadable', the
    value, the argument that named the file and its hint, before reading it.
    """
    path = tmp_path / "dotted.csv"
    path.write_text("date;y\n2020-01-01;0.5\n2020-01-02;1.020\n")
    calls = _record_read_csv(monkeypatch)

    err_msg = re.escape(
        f"The CSV file '{path}' cannot be read with '.' as thousands "
        f"separator: it holds values with a '.' that does not separate "
        f"thousands (such as '0.5'), which pandas would read as numbers "
        f"without it."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_with_dialect(path, field=field, thousands=".")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint
    assert calls == []


@pytest.mark.parametrize(
    "field, hint",
    [("data", THOUSANDS_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_read_csv_with_dialect_InvalidInputError_when_thousands_is_ambiguous(
    tmp_path, field, hint
):
    """
    Test that a file whose only numbers with a '.' read both as thousands and
    as numbers with three decimals ('1.870') raises an InvalidInputError with
    the code 'data_unreadable', an example, the argument that named the file
    and its hint.
    """
    path = tmp_path / "ambiguous.csv"
    path.write_text("date;y\n2020-01-01;1.870\n2020-01-02;1.020\n")

    err_msg = re.escape(
        f"The thousands separator of the CSV file '{path}' cannot be told: "
        f"its numbers with a '.' (such as '1.870') read both as thousands and "
        f"as numbers with three decimals."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_with_dialect(path, field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


def test_read_csv_with_dialect_output_when_thousands_is_ambiguous_and_decimal_point(
    tmp_path, monkeypatch
):
    """
    Test that the file whose '.' cannot be told is read with '.' as decimal
    mark, and no thousands separator, when the caller gives `decimal` '.'.
    """
    path = tmp_path / "ambiguous.csv"
    path.write_text("date;y\n2020-01-01;1.870\n2020-01-02;1.020\n")
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands = read_csv_with_dialect(path, decimal=".")

    expected = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02"], "y": [1.87, 1.02]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ".", None)
    assert calls == [((path,), {"sep": ";", "decimal": "."})]
