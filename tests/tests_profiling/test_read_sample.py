# Unit test read_sample

import bz2
import gzip
import lzma

import re

import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.csv_dialect import (
    ENCODING_HINT,
    SAMPLE_BYTES,
    read_sample,
)

# The files are written as bytes: in text mode Windows turns each '\n' into
# '\r\n', and `read_sample` returns the bytes of the file as they are.
_TEXT = "date;y\n2020-01-01;1,5\n2020-01-02;2,5\n"


def test_read_sample_output_when_plain_file(tmp_path):
    """
    Test that the text of a plain file is returned whole when it is shorter
    than the limit, without the BOM of a UTF-8 file, with the encoding
    'utf-8' with or without it.
    """
    plain = tmp_path / "plain.csv"
    plain.write_bytes(_TEXT.encode("utf-8"))
    bom = tmp_path / "bom.csv"
    bom.write_bytes(b"\xef\xbb\xbf" + _TEXT.encode("utf-8"))

    assert read_sample(plain) == (_TEXT, "utf-8")
    assert read_sample(str(plain)) == (_TEXT, "utf-8")
    assert read_sample(bom) == (_TEXT, "utf-8")


@pytest.mark.parametrize(
    "name, opener",
    [
        ("data.csv.gz", gzip.open),
        ("DATA.CSV.GZ", gzip.open),
        ("data.tsv.gz", gzip.open),
        ("data.csv.bz2", bz2.open),
        ("data.csv.xz", lzma.open),
    ],
    ids=lambda dt: f"{getattr(dt, '__module__', dt)}",
)
def test_read_sample_output_when_file_is_compressed(tmp_path, name, opener):
    """
    Test that a file compressed with gzip, bzip2 or xz is read decompressed,
    the format told from the extension without regard to its case.
    """
    path = tmp_path / name
    with opener(path, "wb") as handle:
        handle.write(_TEXT.encode("utf-8"))

    assert read_sample(path) == (_TEXT, "utf-8")


def test_read_sample_output_when_file_is_longer_than_the_limit(tmp_path):
    """
    Test that only the complete lines within the first `SAMPLE_BYTES` bytes
    are returned: 17475 rows of 15 bytes after a header of 7 bytes.
    """
    path = tmp_path / "long.csv"
    path.write_bytes(("date;y\n" + "2020-01-01;1,5\n" * 20000).encode("utf-8"))

    result = read_sample(path).text

    assert SAMPLE_BYTES == 262144
    assert len(result) == 262132
    assert result.endswith("2020-01-01;1,5\n")
    assert result.count("\n") == 17476


def test_read_sample_output_when_the_limit_cuts_a_character(tmp_path):
    """
    Test that the limit may fall inside a character of several bytes without
    making the sample unreadable: 43690 lines of 6 bytes are kept.
    """
    path = tmp_path / "accents.csv"
    path.write_bytes(("é;é\n" * 50000).encode("utf-8"))

    result = read_sample(path).text

    assert len(result.encode("utf-8")) == 262140
    assert result.count("\n") == 43690


def test_read_sample_output_when_file_is_exactly_the_limit(tmp_path):
    """
    Test that a file of exactly `SAMPLE_BYTES` bytes is returned whole, not
    cut as a longer file is.
    """
    path = tmp_path / "exact.csv"
    path.write_bytes(b"x" * SAMPLE_BYTES)

    result = read_sample(path).text

    assert len(result) == SAMPLE_BYTES
    assert result.endswith("x")


@pytest.mark.parametrize(
    "name, content",
    [
        ("garbage.csv.gz", b"this is not gzip at all"),
        ("truncated.csv.gz", gzip.compress(b"date;y\n" + b"1;2\n" * 5000)[:30]),
        ("garbage.csv.bz2", b"this is not bzip2 at all"),
        ("garbage.csv.xz", b"this is not xz at all"),
    ],
    ids=lambda dt: f"{dt}" if isinstance(dt, str) else "",
)
def test_read_sample_output_is_None_when_file_cannot_be_read_here(
    tmp_path, name, content
):
    """
    Test that a file compressed and damaged (not gzip, cut) gives None, left
    for `pandas.read_csv` to report.
    """
    path = tmp_path / name
    path.write_bytes(content)

    assert read_sample(path) is None


def test_read_sample_output_is_None_when_file_does_not_exist(tmp_path):
    """
    Test that a missing file gives None instead of raising.
    """
    assert read_sample(tmp_path / "missing.csv") is None


def test_read_sample_output_is_empty_when_gzip_file_is_empty(tmp_path):
    """
    Test that a gzip file of zero bytes reads as an empty text, which pandas
    reports as an empty file.
    """
    path = tmp_path / "empty.csv.gz"
    path.write_bytes(b"")

    assert read_sample(path) == ("", "utf-8")


@pytest.mark.parametrize(
    "name",
    ["data.zip", "data.csv.zst", "data.tar", "data.tar.gz", "DATA.TAR.XZ"],
    ids=lambda dt: dt,
)
def test_read_sample_output_is_None_when_archive_or_not_opened_here(tmp_path, name):
    """
    Test that a file pandas decompresses but that is not opened here (an
    archive, zstd) gives None, read by pandas as before, even when its bytes
    hold null bytes, which would raise for a plain file.
    """
    path = tmp_path / name
    path.write_bytes(b"PK\x03\x04\x00\x00 not text")

    assert read_sample(path) is None


@pytest.mark.parametrize(
    "name, opener",
    [("excel.csv", open), ("excel.csv.gz", gzip.open)],
    ids=["plain", "gzip"],
)
def test_read_sample_output_when_file_is_cp1252(tmp_path, name, opener):
    """
    Test that a file that is not UTF-8 (the CSV that Excel saves on Windows,
    with 'ñ' and accents in the header and the categories) is decoded as
    cp1252 and says so, also compressed with gzip.
    """
    text = "año;ventas;zona\r\n01/01/2020;1,5;Cádiz\r\n02/01/2020;2,5;Peñíscola\r\n"
    path = tmp_path / name
    with opener(path, "wb") as handle:
        handle.write(text.encode("cp1252"))

    assert read_sample(path) == (text, "cp1252")


def test_read_sample_InvalidInputError_when_file_is_utf16(tmp_path):
    """
    Test that a file in UTF-16 raises with the argument that named it.
    """
    path = tmp_path / "unicode.csv"
    path.write_bytes(_TEXT.encode("utf-16"))

    err_msg = re.escape(f"The CSV file '{path}' could not be read: it is written in UTF-16")
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        read_sample(path, field="exog")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "exog"
    assert exc_info.value.hint == ENCODING_HINT
