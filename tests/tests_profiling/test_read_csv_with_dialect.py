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
    ENCODING_HINT,
    EXOG_DIALECT_HINT,
    THOUSANDS_HINT,
)
from skforecast_ai.profiling.data_profile import read_csv_with_dialect

from ..fixtures_csv_dialect import (
    df_dialect_cp1252,
    df_dialect_thousands_long,
    write_cp1252,
    write_thousands,
)

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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

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

    data, result_sep, result_decimal, thousands, _ = read_csv_with_dialect(str(path))

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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path, index_first=True)

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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

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

    data, result_sep, result_decimal, thousands, _ = read_csv_with_dialect(
        path, sep=sep, decimal=decimal
    )

    pd.testing.assert_frame_equal(data, _EXPECTED)
    assert (result_sep, result_decimal, thousands) == (
        expected_sep, expected_decimal, None
    )


def test_read_csv_with_dialect_does_not_detect_the_dialect_when_both_given(
    tmp_path, monkeypatch
):
    """
    Test that the dialect is not told from the start of the file when the
    caller gives the separator and the decimal mark; the start is still
    read, for the encoding.
    """
    path = tmp_path / "data.csv"
    _EXPECTED.to_csv(path, index=False, sep=";", decimal=",")
    detected = []
    monkeypatch.setattr(
        data_profile_module,
        "detect_csv_dialect",
        lambda *args, **kwargs: detected.append(args),
    )

    data, sep, decimal, thousands, encoding = read_csv_with_dialect(
        path, sep=";", decimal=","
    )

    assert detected == []
    pd.testing.assert_frame_equal(data, _EXPECTED)
    assert (sep, decimal, thousands, encoding) == (";", ",", None, "utf-8")


def test_read_csv_with_dialect_gives_the_given_sep_even_when_it_does_not_fit(
    tmp_path,
):
    """
    Test that a separator given by the caller is not corrected: a
    semicolon file read with ',' is one column named after the header.
    """
    path = tmp_path / "data.csv"
    path.write_text("date;y\n2020-01-01;1.5\n")

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path, sep=",")

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
    ids=["empty", "damaged gzip", "truncated gzip"],
)
@pytest.mark.parametrize("field", ["data", "exog"])
def test_read_csv_with_dialect_InvalidInputError_when_file_unreadable(
    tmp_path, name, content, reason, field
):
    """
    Test that an empty or damaged compressed file raises an
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
    Test that a file pandas cannot read is reported as unreadable when the
    caller gives a thousands separator or a decimal mark ',' and no
    separator, instead of as an argument that does not fit the default
    separator ','.
    """
    path = tmp_path / "data.csv.gz"
    path.write_bytes(b"this is not gzip at all")

    err_msg = re.escape(
        f"The CSV file '{path}' could not be read: Not a gzipped file (b'th')"
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_with_dialect(path, **kwargs)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (
            {"thousands": "."},
            "`thousands` cannot be '.' when `sep` is ',': '.' separates the "
            "thousands where ',' is the decimal mark, which cannot also "
            "separate the fields.",
        ),
        (
            {"decimal": ","},
            "`decimal` cannot be ',' when `sep` is ',': the same character "
            "would separate the fields and the decimals.",
        ),
    ],
    ids=["thousands", "decimal comma"],
)
def test_read_csv_with_dialect_InvalidInputError_when_no_sample_and_dialect_given(
    tmp_path, monkeypatch, kwargs, message
):
    """
    Test that a file pandas reads although its start could not be sampled
    (the separator is then ',') is rejected when the thousands separator or
    the decimal mark given does not fit that separator.
    """
    monkeypatch.setattr(
        data_profile_module, "read_sample", lambda path, field: None
    )
    path = tmp_path / "data.csv"
    path.write_text("date,y\n2020-01-01,1\n")

    with pytest.raises(InvalidInputError, match=re.escape(message)):
        read_csv_with_dialect(path, **kwargs)


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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path, decimal=".")

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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert calls == [
        (
            (path,),
            {"sep": ";", "decimal": ",", "thousands": ".", "dtype": {"date": str}},
        )
    ]


def test_read_csv_with_dialect_output_when_thousands_detected_in_tab_file(tmp_path):
    """
    Test that a file separated by tabulators whose numbers have '.' between
    thousands and a ',' for the decimals is read with ',' and '.'.
    """
    path = tmp_path / "thousands.tsv"
    path.write_text("date\ty\n2020-01-01\t1.705,11\n2020-01-02\t2.870,5\n")

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(
        path, sep=";", decimal=","
    )

    expected = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02"], "y": [1705, 1870]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert calls == [
        ((path,), {"sep": ";", "decimal": ","}),
        (
            (path,),
            {"sep": ";", "decimal": ",", "thousands": ".", "dtype": {"date": str}},
        ),
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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

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
        (
            (path,),
            {"sep": ";", "decimal": ",", "thousands": ".", "dtype": {"date": str}},
        ),
    ]


def test_read_csv_with_dialect_thousands_of_whole_numbers_after_the_sample(
    tmp_path, monkeypatch
):
    """
    Test that a ';' file whose column holds whole numbers below 1,000 in the
    lines the dialect is told from and numbers such as '1.020' after them,
    which pandas reads as 1.02, has its columns of numbers read again as text
    and is read with ',' as decimal mark and '.' as thousands separator.
    """
    monkeypatch.setattr("skforecast_ai.profiling.csv_dialect.SAMPLE_BYTES", 40)
    path = tmp_path / "late.csv"
    path.write_text(
        "date;y\n2020-01-01;870\n2020-01-02;945\n2020-01-03;1.020\n"
        "2020-01-04;2.015\n"
    )
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

    assert data["y"].tolist() == [870, 945, 1020, 2015]
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert len(calls) == 3
    assert calls[0] == ((path,), {"sep": ";", "decimal": "."})
    assert calls[1][1]["dtype"] is str
    assert calls[2] == (
        (path,),
        {"sep": ";", "decimal": ",", "thousands": ".", "dtype": {"date": str}},
    )


def test_read_csv_with_dialect_reads_once_when_the_sample_holds_the_file(
    tmp_path, monkeypatch
):
    """
    Test that a ';' file read with '.' as decimal mark is read once when the
    lines its dialect is told from are the whole file: its columns of
    numbers are not read again as text.
    """
    path = tmp_path / "semi.csv"
    path.write_text("date;y\n2020-01-01;1.5\n2020-01-02;2.25\n")
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

    assert data["y"].tolist() == [1.5, 2.25]
    assert (sep, decimal, thousands) == (";", ".", None)
    assert calls == [((path,), {"sep": ";", "decimal": "."})]


def test_read_csv_with_dialect_InvalidInputError_when_dotted_values_after_the_sample(
    tmp_path, monkeypatch
):
    """
    Test that a number with '.' between thousands after the lines the dialect
    is told from, in a file with a number such as '0.5', raises an
    InvalidInputError with the code 'data_unreadable' and the hint of the
    values, because pandas would read it as a number without the '.'. The
    dates such as '15.01.2020' are not the reason: their column is read as
    text.
    """
    monkeypatch.setattr(
        "skforecast_ai.profiling.csv_dialect.SAMPLE_BYTES", 40
    )
    path = tmp_path / "late.csv"
    path.write_text(
        "date;y;x\n15.01.2020;1;10\n16.01.2020;2;0.5\n17.01.2020;3;1.705,11\n"
    )

    err_msg = re.escape(
        f"The CSV file '{path}' cannot be read: it holds numbers with '.' "
        f"between the thousands (such as '1.705,11') and values with a '.' "
        f"that does not separate thousands (such as '0.5'), which pandas "
        f"would read as numbers without it."
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

    data, result_sep, decimal, thousands, _ = read_csv_with_dialect(
        path, sep=sep, thousands="."
    )

    expected = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02"], "y": [870, 1020]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (result_sep, decimal, thousands) == (";", ",", ".")
    assert calls == [
        (
            (path,),
            {"sep": ";", "decimal": ",", "thousands": ".", "dtype": {"date": str}},
        )
    ]


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

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path, decimal=".")

    expected = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02"], "y": [1.87, 1.02]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ".", None)
    assert calls == [((path,), {"sep": ";", "decimal": "."})]


def test_read_csv_with_dialect_series_ids_are_text_with_default_dialect(
    tmp_path, monkeypatch
):
    """
    Test that the column of series ids is read as text, with the default
    dialect too: '001', '1' and '10' keep their zeros and stay three series,
    and `pd.read_csv` receives only `dtype` for that column. Without the
    column, the ids are read as the integers 1, 1 and 10.
    """
    path = tmp_path / "ids.csv"
    path.write_text(
        "store,date,y\n001,2020-01-01,1.5\n1,2020-01-02,2.5\n10,2020-01-03,3.5\n"
    )
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(
        path, series_id_column="store"
    )

    expected = pd.DataFrame(
        {
            "store": ["001", "1", "10"],
            "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "y": [1.5, 2.5, 3.5],
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (",", ".", None)
    assert calls == [((path,), {"dtype": {"store": str}})]

    data, *_ = read_csv_with_dialect(path)

    assert data["store"].tolist() == [1, 1, 10]


def test_read_csv_with_dialect_series_ids_are_text_with_thousands(
    tmp_path, monkeypatch
):
    """
    Test that a ';' file whose numbers have '.' between thousands is read
    with ',' and '.', its target as numbers and its series ids ('001', '1',
    '10') as text, in one call to `pd.read_csv`. Without the column, the ids
    are read as the integers 1, 1 and 10.
    """
    path = write_thousands(
        tmp_path, df_dialect_thousands_long, series_id_column="store"
    )
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(
        path, series_id_column="store"
    )

    rows = [0, 1, 47, 48, 49, 96, 143]
    expected = pd.DataFrame(
        {
            "store": ["001", "001", "001", "1", "1", "10", "10"],
            "date": [
                "2018-01-01", "2018-02-01", "2021-12-01", "2018-01-01",
                "2018-02-01", "2018-01-01", "2021-12-01",
            ],
            "y": [870.0, 920.24, 2048.71, 1120.0, 1170.24, 600.0, 1778.71],
        },
        index=rows,
    )
    pd.testing.assert_frame_equal(data.loc[rows], expected)
    assert len(data) == 144
    assert data["store"].value_counts(sort=False).to_dict() == {
        "001": 48, "1": 48, "10": 48
    }
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert calls == [
        (
            (path,),
            {
                "sep": ";",
                "decimal": ",",
                "thousands": ".",
                "dtype": {"store": str, "date": str},
            },
        )
    ]

    data, *_ = read_csv_with_dialect(path)

    assert data["store"].tolist() == [1] * 96 + [10] * 48


def test_read_csv_with_dialect_series_ids_with_point_do_not_tell_the_thousands(
    tmp_path, monkeypatch
):
    """
    Test that series ids such as '1.020' are not touched by the thousands
    separator the target needs: they stay '1.020'. Without the column, the
    thousands separator is applied to them and they are read as the integer
    1020.
    """
    path = tmp_path / "ids.csv"
    path.write_text(
        "store;date;y\n1.020;2015-01-01;870\n1.020;2015-02-01;945\n"
        "1.020;2015-03-01;1.020\n1.020;2015-04-01;2.015\n"
    )
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(
        path, series_id_column="store"
    )

    expected = pd.DataFrame(
        {
            "store": ["1.020"] * 4,
            "date": ["2015-01-01", "2015-02-01", "2015-03-01", "2015-04-01"],
            "y": [870, 945, 1020, 2015],
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert calls == [
        (
            (path,),
            {
                "sep": ";",
                "decimal": ",",
                "thousands": ".",
                "dtype": {"store": str, "date": str},
            },
        )
    ]

    data, *_ = read_csv_with_dialect(path)

    assert data["store"].tolist() == [1020, 1020, 1020, 1020]


def test_read_csv_with_dialect_series_ids_with_point_when_thousands_after_the_sample(
    tmp_path, monkeypatch
):
    """
    Test that every read of a file whose thousands only come after the lines
    the dialect is told from keeps the series ids as text ('1.020' stays
    '1.020'): the first read with '.' as decimal mark, and the last one with
    ',' and '.'.
    """
    monkeypatch.setattr("skforecast_ai.profiling.csv_dialect.SAMPLE_BYTES", 40)
    path = tmp_path / "late.csv"
    path.write_text(
        "store;date;y\n1.020;2015-01-01;870\n1.020;2015-02-01;945\n"
        "1.020;2015-03-01;1.020\n1.020;2015-04-01;2.015\n"
    )
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(
        path, series_id_column="store"
    )

    expected = pd.DataFrame(
        {
            "store": ["1.020"] * 4,
            "date": ["2015-01-01", "2015-02-01", "2015-03-01", "2015-04-01"],
            "y": [870, 945, 1020, 2015],
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert len(calls) == 3
    assert calls[0] == (
        (path,), {"sep": ";", "decimal": ".", "dtype": {"store": str}}
    )
    assert calls[2] == (
        (path,),
        {
            "sep": ";",
            "decimal": ",",
            "thousands": ".",
            "dtype": {"store": str, "date": str},
        },
    )


def test_read_csv_with_dialect_series_ids_with_comma_do_not_tell_the_decimal_mark(
    tmp_path,
):
    """
    Test that series ids written with ',' ('1,5'), which are text, do not
    make ',' the decimal mark of a file after the lines the dialect is told
    from. Without the column, the ids are read as the number 1.5 with ','.
    """
    path = tmp_path / "ids.csv"
    path.write_text(
        "store;date;y\n1,5;2020-01-01;1\n1,5;2020-01-02;2\n1,5;2020-01-03;3\n"
    )

    data, sep, decimal, thousands, _ = read_csv_with_dialect(
        path, series_id_column="store"
    )

    expected = pd.DataFrame(
        {
            "store": ["1,5", "1,5", "1,5"],
            "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "y": [1, 2, 3],
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ".", None)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

    assert data["store"].tolist() == [1.5, 1.5, 1.5]
    assert (sep, decimal, thousands) == (";", ",", None)


def test_read_csv_with_dialect_series_ids_with_point_do_not_tell_thousands_when_decimal_given(
    tmp_path,
):
    """
    Test that, with ',' given as decimal mark, series ids such as '1.020' are
    not taken for thousands: the file is read once and the ids stay '1.020'.
    Without the column, the file is read again with '.' as thousands
    separator and the ids are the integer 1020.
    """
    path = tmp_path / "ids.csv"
    path.write_text(
        "store;date;y\n1.020;2020-01-01;1,5\n1.020;2020-01-02;2,5\n"
        "1.020;2020-01-03;3,5\n"
    )

    data, sep, decimal, thousands, _ = read_csv_with_dialect(
        path, decimal=",", series_id_column="store"
    )

    expected = pd.DataFrame(
        {
            "store": ["1.020", "1.020", "1.020"],
            "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "y": [1.5, 2.5, 3.5],
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", None)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path, decimal=",")

    assert data["store"].tolist() == [1020, 1020, 1020]
    assert (sep, decimal, thousands) == (";", ",", ".")


_GERMAN_SPREADSHEET = (
    "datum;umsatz\n15.01.2020;1.234,56\n16.01.2020;2.345,67\n17.01.2020;870,5\n"
)
_GERMAN_EXPECTED = pd.DataFrame(
    {
        "datum": ["15.01.2020", "16.01.2020", "17.01.2020"],
        "umsatz": [1234.56, 2345.67, 870.5],
    }
)
_GERMAN_FINAL_CALL = {
    "sep": ";",
    "decimal": ",",
    "thousands": ".",
    "dtype": {"datum": str},
}


@pytest.mark.parametrize(
    "kwargs, expected_kwargs",
    [
        ({}, [_GERMAN_FINAL_CALL]),
        ({"date_column": "datum"}, [_GERMAN_FINAL_CALL]),
        ({"thousands": "."}, [_GERMAN_FINAL_CALL]),
        ({"decimal": ","}, [_GERMAN_FINAL_CALL]),
        (
            {"sep": ";", "decimal": ","},
            [{"sep": ";", "decimal": ","}, _GERMAN_FINAL_CALL],
        ),
    ],
    ids=[
        "dialect detected",
        "date column given",
        "thousands given",
        "decimal given",
        "separator and decimal given",
    ],
)
def test_read_csv_with_dialect_output_when_german_spreadsheet(
    tmp_path, monkeypatch, kwargs, expected_kwargs
):
    """
    Test that a ';' file with dates written with points ('15.01.2020') and
    amounts with '.' between thousands ('1.234,56') is read with ',' as
    decimal mark and '.' as thousands separator, and its dates stay text
    (`dtype`), as the generated script reads them: pandas would read the
    dates as the number 15012020. The column of the dates is told from the
    first lines of the file, or from the file read when no lines are read
    (the separator and the decimal mark given), or is the `date_column`
    given.
    """
    path = tmp_path / "german.csv"
    path.write_text(_GERMAN_SPREADSHEET)
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path, **kwargs)

    pd.testing.assert_frame_equal(data, _GERMAN_EXPECTED)
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert calls == [((path,), call) for call in expected_kwargs]


def test_read_csv_with_dialect_output_when_german_spreadsheet_with_series_ids(
    tmp_path, monkeypatch
):
    """
    Test that the series ids ('001') and the dates of a German spreadsheet are
    both read as text, with the amounts as numbers, in one call.
    """
    path = tmp_path / "german_long.csv"
    path.write_text(
        "store;datum;umsatz\n001;15.01.2020;1.234,56\n002;16.01.2020;2.345,67\n"
    )
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(
        path, series_id_column="store"
    )

    expected = pd.DataFrame(
        {
            "store": ["001", "002"],
            "datum": ["15.01.2020", "16.01.2020"],
            "umsatz": [1234.56, 2345.67],
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert calls == [
        (
            (path,),
            {
                "sep": ";",
                "decimal": ",",
                "thousands": ".",
                "dtype": {"store": str, "datum": str},
            },
        )
    ]


def test_read_csv_with_dialect_dates_with_points_do_not_tell_the_thousands_when_given(
    tmp_path, monkeypatch
):
    """
    Test that dates written with points in a file whose separator and decimal
    mark ',' are given, and whose amounts have no '.' between thousands, do
    not make the file be read again with '.' as thousands separator (or fail
    for values with a '.' that is not one): it is read once, with the dates
    as text.
    """
    path = tmp_path / "german_plain.csv"
    path.write_text("datum;umsatz\n15.01.2020;870,5\n16.01.2020;945,25\n")
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(
        path, sep=";", decimal=","
    )

    expected = pd.DataFrame(
        {"datum": ["15.01.2020", "16.01.2020"], "umsatz": [870.5, 945.25]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", None)
    assert calls == [((path,), {"sep": ";", "decimal": ","})]


def test_read_csv_with_dialect_date_column_is_not_read_as_text_without_thousands(
    tmp_path, monkeypatch
):
    """
    Test that a `date_column` given changes nothing for a file without a
    thousands separator: it is read with exactly `pd.read_csv(path)`.
    """
    path = tmp_path / "plain.csv"
    path.write_text("date,y\n2020-01-15,1.5\n2020-01-16,2.5\n")
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path, date_column="date")

    expected = pd.DataFrame({"date": ["2020-01-15", "2020-01-16"], "y": [1.5, 2.5]})
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (",", ".", None)
    assert calls == [((path,), {})]


@pytest.mark.parametrize(
    "text, expected_umsatz, expected_calls",
    [
        (
            "datum;umsatz\n15.01.2020;870\n16.01.2020;945\n17.01.2020;1.020\n"
            "18.01.2020;2.015\n",
            [870, 945, 1020, 2015],
            3,
        ),
        (
            "datum;umsatz\n15.01.2020;870,5\n16.01.2020;945,5\n"
            "17.01.2020;1.020,5\n18.01.2020;2.015,5\n",
            [870.5, 945.5, 1020.5, 2015.5],
            2,
        ),
    ],
    ids=["whole numbers", "decimals"],
)
def test_read_csv_with_dialect_thousands_after_the_sample_with_dates_with_points(
    tmp_path, monkeypatch, text, expected_umsatz, expected_calls
):
    """
    Test that a German spreadsheet whose numbers with '.' between thousands
    only come after the lines the dialect is told from is read with ',' and
    '.', and its dates with points stay text: they are neither the reason
    for the file to be unreadable nor read as numbers.
    """
    monkeypatch.setattr("skforecast_ai.profiling.csv_dialect.SAMPLE_BYTES", 40)
    path = tmp_path / "late_german.csv"
    path.write_text(text)
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path)

    expected = pd.DataFrame(
        {
            "datum": ["15.01.2020", "16.01.2020", "17.01.2020", "18.01.2020"],
            "umsatz": expected_umsatz,
        }
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", ".")
    assert len(calls) == expected_calls
    assert calls[-1] == ((path,), _GERMAN_FINAL_CALL)


def test_read_csv_with_dialect_InvalidInputError_when_dates_with_points_not_found(
    tmp_path,
):
    """
    Test that dates with points that the first lines do not find as the
    column of the dates (two digits for the year, '15.01.20') raise an
    InvalidInputError with the code 'data_unreadable', unless the
    `date_column` says where they are: then the file is read.
    """
    path = tmp_path / "short_year.csv"
    path.write_text("datum;umsatz\n15.01.20;1.234,56\n16.01.20;2.345,67\n")

    err_msg = re.escape(
        f"The CSV file '{path}' cannot be read: it holds numbers with '.' "
        f"between the thousands (such as '1.234,56') and values with a '.' "
        f"that does not separate thousands (such as '15.01.20'), which pandas "
        f"would read as numbers without it."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_with_dialect(path)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.hint == DOTTED_VALUES_HINT

    data, sep, decimal, thousands, _ = read_csv_with_dialect(path, date_column="datum")

    expected = pd.DataFrame(
        {"datum": ["15.01.20", "16.01.20"], "umsatz": [1234.56, 2345.67]}
    )
    pd.testing.assert_frame_equal(data, expected)
    assert (sep, decimal, thousands) == (";", ",", ".")


@pytest.mark.parametrize("name", ["excel.csv", "excel.csv.gz"], ids=["plain", "gzip"])
@pytest.mark.parametrize(
    "kwargs",
    [{}, {"sep": ";", "decimal": ","}],
    ids=["detected", "dialect given"],
)
def test_read_csv_with_dialect_output_when_file_is_cp1252(
    tmp_path, monkeypatch, name, kwargs
):
    """
    Test that the CSV that Excel saves on Windows in Spanish (cp1252, ';',
    ',' as decimal mark, 'año' in the header and accents in the categories)
    is read as cp1252, also compressed with gzip and with its dialect given,
    and that `pd.read_csv` receives the encoding as the script does.
    """
    path = write_cp1252(tmp_path, name=name)
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, encoding = read_csv_with_dialect(path, **kwargs)

    pd.testing.assert_frame_equal(data, df_dialect_cp1252)
    assert (sep, decimal, thousands, encoding) == (";", ",", None, "cp1252")
    assert calls == [
        ((path,), {"sep": ";", "decimal": ",", "encoding": "cp1252"}),
    ]


def test_read_csv_with_dialect_output_when_file_is_utf8_with_bom(
    tmp_path, monkeypatch
):
    """
    Test that a UTF-8 file with a byte order mark (the 'CSV UTF-8' of
    Excel) is UTF-8: its first column keeps its name, and `pd.read_csv`
    receives no encoding.
    """
    path = tmp_path / "bom.csv"
    df_dialect_cp1252.to_csv(
        path, index=False, sep=";", decimal=",", encoding="utf-8-sig"
    )
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, encoding = read_csv_with_dialect(path)

    pd.testing.assert_frame_equal(data, df_dialect_cp1252)
    assert (sep, decimal, thousands, encoding) == (";", ",", None, "utf-8")
    assert calls == [((path,), {"sep": ";", "decimal": ","})]


def test_read_csv_with_dialect_output_when_cp1252_bytes_after_the_sample(
    tmp_path, monkeypatch
):
    """
    Test that a file whose first lines are UTF-8 (only ASCII) and whose
    bytes that are not UTF-8 come after them is read again as cp1252, with
    the categories that hold them read right.
    """
    rows = ["2020-01-01;1,5;Madrid"] * 20000 + ["2020-01-02;2,5;Cádiz"]
    path = tmp_path / "late.csv"
    path.write_bytes(("date;y;zona\n" + "\n".join(rows) + "\n").encode("cp1252"))
    calls = _record_read_csv(monkeypatch)

    data, sep, decimal, thousands, encoding = read_csv_with_dialect(path)

    assert data["zona"].iloc[-1] == "Cádiz"
    assert (sep, decimal, thousands, encoding) == (";", ",", None, "cp1252")
    assert [kwargs.get("encoding") for _, kwargs in calls] == [None, "cp1252"]


@pytest.mark.parametrize(
    "encoding, name",
    [("utf-16", "UTF-16"), ("utf-16-be", None), ("utf-32", "UTF-32")],
    ids=["utf-16 with bom", "utf-16 without bom", "utf-32"],
)
@pytest.mark.parametrize("field", ["data", "exog"])
def test_read_csv_with_dialect_InvalidInputError_when_file_is_utf16(
    tmp_path, encoding, name, field
):
    """
    Test that a file in UTF-16 or UTF-32, which cp1252 would read with a
    null byte in every character, raises an InvalidInputError with the code
    'data_unreadable' and the hint that asks for a copy in UTF-8: told by
    its byte order mark, or by its null bytes without one.
    """
    path = tmp_path / "unicode.csv"
    path.write_bytes("fecha;año\n01/01/2020;1,5\n".encode(encoding))

    if name is None:
        err_msg = (
            f"The CSV file '{path}' could not be read: it holds null bytes, so "
            f"it is not text in UTF-8 or in cp1252 (Windows-1252); it may be "
            f"UTF-16 without its byte order mark, or not a text file."
        )
    else:
        err_msg = (
            f"The CSV file '{path}' could not be read: it is written in {name} "
            f"(its first bytes say so), and only files in UTF-8 or in cp1252 "
            f"(Windows-1252) are read."
        )
    with pytest.raises(InvalidInputError, match="^" + re.escape(err_msg) + "$") as exc_info:
        read_csv_with_dialect(path, field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == ENCODING_HINT


@pytest.mark.parametrize(
    "content",
    [
        b"date;y;zona\n2020-01-01;1,5;caf\xe9\n2020-01-02;2,5;\x81\n",
        (
            b"date;y;zona\n" + b"2020-01-01;1,5;Madrid\n" * 20000
            + b"2020-01-02;2,5;caf\xe9\x81\n"
        ),
    ],
    ids=["in the sample", "after the sample"],
)
def test_read_csv_with_dialect_InvalidInputError_when_byte_undefined_in_cp1252(
    tmp_path, content
):
    """
    Test that a file that is not UTF-8 and holds a byte that cp1252 does
    not define raises an InvalidInputError with the code 'data_unreadable'
    that names the byte, in the first lines or after them.
    """
    path = tmp_path / "other.csv"
    path.write_bytes(content)

    err_msg = re.escape(
        f"The CSV file '{path}' could not be read: it is not UTF-8, and its "
        f"byte 0x81 is not a character of cp1252 (Windows-1252), the other "
        f"encoding read."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        read_csv_with_dialect(path)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.hint == ENCODING_HINT


def test_read_csv_with_dialect_output_when_utf8_file_holds_bytes_undefined_in_cp1252(
    tmp_path,
):
    """
    Test that the bytes cp1252 does not define are only looked for in a file
    that is not UTF-8: 'Á' is written in UTF-8 with the byte 0x81.
    """
    path = tmp_path / "utf8.csv"
    path.write_bytes("date;y;zona\n2020-01-01;1,5;ÁVILA\n".encode("utf-8"))

    data, *_, encoding = read_csv_with_dialect(path)

    assert data["zona"].tolist() == ["ÁVILA"]
    assert encoding == "utf-8"


def test_read_csv_with_dialect_output_when_cp1252_row_longer_than_header(tmp_path):
    """
    Test that the fields of every row of a cp1252 file are counted in that
    encoding: a header one field short (`to_csv(index_label=False)`) of
    future values in cp1252 is read with its first field as the index.
    """
    path = tmp_path / "exog.csv"
    path.write_bytes(
        "zona\n2023-03-02;Cádiz\n2023-03-03;Peñíscola\n".replace(";", ",")
        .encode("cp1252")
    )

    data, *_, encoding = read_csv_with_dialect(path, field="exog", index_first=True)

    assert data["zona"].tolist() == ["Cádiz", "Peñíscola"]
    assert data.index.tolist() == ["2023-03-02", "2023-03-03"]
    assert encoding == "cp1252"


def test_read_csv_with_dialect_thousands_after_the_sample_when_file_is_cp1252(
    tmp_path,
):
    """
    Test that the columns of a cp1252 file larger than its sample are read
    again as text in cp1252 to look for '.' between thousands after the
    sample ('870' in it, '1.020' after it).
    """
    rows = ["2020-01-01;870;Cádiz"] * 15000 + ["2020-01-02;1.020;Peñíscola"]
    path = tmp_path / "large.csv"
    path.write_bytes(("date;y;zona\n" + "\n".join(rows) + "\n").encode("cp1252"))

    data, sep, decimal, thousands, encoding = read_csv_with_dialect(path)

    assert data["y"].iloc[-1] == 1020
    assert data["zona"].iloc[-1] == "Peñíscola"
    assert (sep, decimal, thousands, encoding) == (";", ",", ".", "cp1252")
