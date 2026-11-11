# Unit test sample_encoding

import codecs
import re

import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.csv_dialect import ENCODING_HINT, sample_encoding

_TEXT = "fecha;año;zona\r\n01/01/2020;1,5;Cádiz\r\n02/01/2020;2,5;Peñíscola\r\n"


@pytest.mark.parametrize(
    "raw",
    [
        b"date;y\n2020-01-01;1,5\n",
        _TEXT.encode("utf-8"),
        codecs.BOM_UTF8 + _TEXT.encode("utf-8"),
        "zona\nÁVILA\n".encode("utf-8"),
        b"",
    ],
    ids=["ascii", "utf-8", "utf-8 with bom", "utf-8 with byte 0x81", "empty"],
)
def test_sample_encoding_output_is_utf8(raw):
    """
    Test that a start that decodes as UTF-8 is UTF-8, with or without a
    byte order mark, also when it holds bytes that cp1252 does not define
    ('Á' is written with 0x81), and when it is empty.
    """
    assert sample_encoding(raw, "data.csv") == "utf-8"


@pytest.mark.parametrize(
    "raw",
    [
        _TEXT.encode("cp1252"),
        "date,x\n2020-01-01,café\n".encode("latin-1"),
        "precio\n10 €\n".encode("cp1252"),
    ],
    ids=["excel spanish", "latin-1", "euro sign"],
)
def test_sample_encoding_output_is_cp1252(raw):
    """
    Test that a start that is not UTF-8 is cp1252: the CSV that Excel saves
    on Windows, which also reads Latin-1 text, and its euro sign (0x80).
    """
    assert sample_encoding(raw, "data.csv") == "cp1252"


@pytest.mark.parametrize(
    "encoding, name",
    [
        ("utf-16", "UTF-16"),
        ("utf-16-le", "UTF-16"),
        ("utf-16-be", "UTF-16"),
        ("utf-32", "UTF-32"),
        ("utf-32-be", "UTF-32"),
    ],
    ids=["utf-16", "utf-16 le", "utf-16 be", "utf-32", "utf-32 be"],
)
@pytest.mark.parametrize("field", ["data", "exog"])
def test_sample_encoding_InvalidInputError_when_utf16_or_utf32(encoding, name, field):
    """
    Test that UTF-16 and UTF-32, which cp1252 would read with null bytes,
    raise an InvalidInputError with the code 'data_unreadable', the field
    and the hint that asks for a copy in UTF-8: named after their byte order
    mark when they start with one (the little endian mark of UTF-16 starts
    the one of UTF-32), and for their null bytes otherwise.
    """
    raw = _TEXT.encode(encoding)
    if encoding in ("utf-16-le", "utf-16-be", "utf-32-be"):
        bom = {
            "utf-16-le": codecs.BOM_UTF16_LE,
            "utf-16-be": codecs.BOM_UTF16_BE,
            "utf-32-be": codecs.BOM_UTF32_BE,
        }[encoding]
        raw = bom + raw

    err_msg = re.escape(
        f"The CSV file 'data.csv' could not be read: it is written in {name} "
        f"(its first bytes say so), and only files in UTF-8 or in cp1252 "
        f"(Windows-1252) are read."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        sample_encoding(raw, "data.csv", field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == ENCODING_HINT


@pytest.mark.parametrize(
    "raw",
    [
        _TEXT.encode("utf-16-le"),
        _TEXT.encode("utf-32-be"),
        b"date,y\n2020-01-01,\x00\n",
        bytes(range(256)),
    ],
    ids=["utf-16 without bom", "utf-32 without bom", "null in utf-8", "binary"],
)
def test_sample_encoding_InvalidInputError_when_null_bytes(raw):
    """
    Test that a start with a null byte, which no CSV file in UTF-8 or
    cp1252 holds, raises an InvalidInputError with the code
    'data_unreadable': UTF-16 or UTF-32 without a byte order mark, or a
    file that is not text.
    """
    err_msg = re.escape(
        "The CSV file 'data.csv' could not be read: it holds null bytes, so it "
        "is not text in UTF-8 or in cp1252 (Windows-1252); it may be UTF-16 "
        "without its byte order mark, or not a text file."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        sample_encoding(raw, "data.csv")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.hint == ENCODING_HINT


@pytest.mark.parametrize("byte", [b"\x81", b"\x8d", b"\x8f", b"\x90", b"\x9d"])
def test_sample_encoding_InvalidInputError_when_byte_undefined_in_cp1252(byte):
    """
    Test that a start that is not UTF-8 and holds one of the five bytes
    that cp1252 does not define raises an InvalidInputError with the code
    'data_unreadable' that names the byte.
    """
    raw = "zona\nCádiz\n".encode("cp1252") + byte + b"\n"

    err_msg = re.escape(
        f"The CSV file 'https://example.com/a.csv' could not be read: it is "
        f"not UTF-8, and its byte 0x{byte[0]:02x} is not a character of cp1252 "
        f"(Windows-1252), the other encoding read."
    )
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        sample_encoding(raw, "https://example.com/a.csv")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == ENCODING_HINT
