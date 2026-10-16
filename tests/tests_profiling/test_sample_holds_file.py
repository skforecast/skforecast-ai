# Unit test sample_holds_file

import bz2
import gzip
import lzma

import pytest

from skforecast_ai.profiling import csv_dialect
from skforecast_ai.profiling.csv_dialect import sample_holds_file


@pytest.mark.parametrize(
    "size, expected",
    [(40, True), (41, False), (100, False)],
    ids=["as long as the sample", "one byte longer", "longer"],
)
@pytest.mark.parametrize(
    "name, compress",
    [
        ("data.csv", bytes),
        ("data.tsv", bytes),
        ("data.csv.gz", gzip.compress),
        ("data.csv.bz2", bz2.compress),
        ("data.csv.xz", lzma.compress),
    ],
    ids=["csv", "tsv", "gzip", "bz2", "xz"],
)
def test_sample_holds_file_output(
    tmp_path, monkeypatch, name, compress, size, expected
):
    """
    Test that the sample holds a file whose content, decompressed for the
    extensions pandas decompresses, is at most `SAMPLE_BYTES` bytes, and not
    a longer one.
    """
    monkeypatch.setattr(csv_dialect, "SAMPLE_BYTES", 40)
    path = tmp_path / name
    path.write_bytes(compress(b"x" * size))

    assert sample_holds_file(path) is expected
    assert sample_holds_file(str(path)) is expected


@pytest.mark.parametrize(
    "name, content",
    [("missing.csv", None), ("damaged.csv.gz", b"this is not gzip")],
    ids=["missing", "damaged gzip"],
)
def test_sample_holds_file_False_when_file_cannot_be_read(tmp_path, name, content):
    """
    Test that the sample does not hold a file that cannot be opened or
    decompressed here.
    """
    path = tmp_path / name
    if content is not None:
        path.write_bytes(content)

    assert sample_holds_file(path) is False
