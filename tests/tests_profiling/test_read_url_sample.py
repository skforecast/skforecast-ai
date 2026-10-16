# Unit test read_url_sample

import bz2
import gzip
import io
import lzma
import re
import tarfile
import urllib.error
import zipfile
import urllib.request

import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.csv_dialect import SAMPLE_BYTES, read_url_sample

_TEXT = "date;y\n2020-01-01;1,5\n2020-01-02;2,5\n"


class _Response:
    """
    Response of `urlopen` that serves bytes and keeps what was asked.
    """

    def __init__(self, content: bytes):
        self.content = content
        self.requested = []

    def read(self, size=-1):
        self.requested.append(size)
        return self.content if size < 0 else self.content[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _serve(monkeypatch, content: bytes) -> dict:
    """
    Replace `urllib.request.urlopen` by a fake that serves `content`; return
    what it was called with.
    """
    seen = {"urls": []}
    response = _Response(content)
    seen["response"] = response

    def urlopen(url, *args, **kwargs):
        seen["urls"].append(url)
        return response

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    return seen


def test_read_url_sample_output_when_plain_content(monkeypatch):
    """
    Test that the text served at a URL is returned, reading at most one byte
    more than the limit, with the BOM removed.
    """
    seen = _serve(monkeypatch, b"\xef\xbb\xbf" + _TEXT.encode("utf-8"))

    result = read_url_sample("https://example.com/a.csv")

    assert result == (_TEXT, "utf-8")
    assert seen["urls"] == ["https://example.com/a.csv"]
    assert seen["response"].requested == [SAMPLE_BYTES + 1]


def test_read_url_sample_output_when_content_is_gzip(monkeypatch):
    """
    Test that a gzip content (told from its first two bytes, whatever the
    URL) is decompressed.
    """
    _serve(monkeypatch, gzip.compress(_TEXT.encode("utf-8")))

    assert read_url_sample("https://example.com/download") == (_TEXT, "utf-8")


def test_read_url_sample_output_when_content_is_longer_than_the_limit(monkeypatch):
    """
    Test that only the complete lines within the first `SAMPLE_BYTES` bytes
    are returned: 17475 rows of 15 bytes after a header of 7 bytes.
    """
    _serve(monkeypatch, ("date;y\n" + "2020-01-01;1,5\n" * 20000).encode("utf-8"))

    result = read_url_sample("https://example.com/a.csv").text

    assert len(result) == 262132
    assert result.endswith("2020-01-01;1,5\n")


def test_read_url_sample_output_when_gzip_content_is_longer_than_the_limit(
    monkeypatch,
):
    """
    Test that a gzip file that is small but expands beyond the limit is cut
    at the limit of its content: 16384 lines of 16 bytes.
    """
    content = ("2020-01-01;1,25\n" * 20000).encode("utf-8")
    assert len(gzip.compress(content)) < SAMPLE_BYTES
    _serve(monkeypatch, gzip.compress(content))

    result = read_url_sample("https://example.com/a.csv.gz").text

    assert len(result) == 262144
    assert result.count("\n") == 16384


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("unreachable"),
        urllib.error.HTTPError("https://example.com/a.csv", 404, "x", {}, None),
        TimeoutError("timed out"),
        ValueError("unknown url type"),
    ],
    ids=["URLError", "HTTPError", "TimeoutError", "ValueError"],
)
def test_read_url_sample_output_is_None_when_url_cannot_be_read(monkeypatch, error):
    """
    Test that a URL that cannot be reached gives None instead of raising,
    left for `pandas.read_csv` to report.
    """

    def urlopen(url, *args, **kwargs):
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    assert read_url_sample("https://example.com/a.csv") is None


def test_read_url_sample_output_is_None_when_content_cannot_be_read_here(
    monkeypatch,
):
    """
    Test that a damaged gzip gives None.
    """
    _serve(monkeypatch, b"\x1f\x8bthis is not gzip")

    assert read_url_sample("https://example.com/a.csv") is None


@pytest.mark.parametrize("gzipped", [False, True], ids=["plain", "gzip"])
def test_read_url_sample_output_when_content_is_cp1252(monkeypatch, gzipped):
    """
    Test that a content that is not UTF-8 is decoded as cp1252 and says so,
    also when it is gzip.
    """
    text = "año;ventas\n01/01/2020;1,5\n"
    content = text.encode("cp1252")
    _serve(monkeypatch, gzip.compress(content) if gzipped else content)

    assert read_url_sample("https://example.com/a.csv") == (text, "cp1252")


def test_read_url_sample_InvalidInputError_when_content_is_utf16(monkeypatch):
    """
    Test that a content in UTF-16 raises, naming the URL.
    """
    url = "https://example.com/a.csv"
    _serve(monkeypatch, _TEXT.encode("utf-16"))

    err_msg = re.escape(f"The CSV file '{url}' could not be read: it is written in UTF-16")
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        read_url_sample(url)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == "data"


@pytest.mark.parametrize(
    "compress",
    [
        bz2.compress,
        lzma.compress,
        lambda content: _zip(content),
        lambda content: gzip.compress(_tar(content)),
        lambda content: _tar(content),
    ],
    ids=["bzip2", "xz", "zip", "tar.gz", "tar"],
)
def test_read_url_sample_output_is_None_when_content_is_not_opened_here(
    monkeypatch, compress
):
    """
    Test that content of a compression or an archive that pandas reads and
    that is not opened here (bzip2, xz, zip, tar, also tar in gzip) gives
    None, read by pandas as before, instead of raising for its null bytes
    or being read as cp1252.
    """
    _serve(monkeypatch, compress(_TEXT.encode("utf-8")))

    assert read_url_sample("https://example.com/download") is None


def _zip(content: bytes) -> bytes:
    """Return `content` as the only file of a zip archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data.csv", content)
    return buffer.getvalue()


def _tar(content: bytes) -> bytes:
    """Return `content` as the only file of a tar archive."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo("data.csv")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()
