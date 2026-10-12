# Unit test check_file_size

import gzip

import pytest

from skforecast_ai.mcp._errors import ServerError
from skforecast_ai.mcp._inputs import check_file_size


def test_check_file_size_accepts_files_within_the_limit_or_no_limit(tmp_path):
    """
    Test that a file of at most the limit passes, and that 0 accepts any
    size.
    """
    path = tmp_path / "data.csv"
    path.write_bytes(b"x" * 1024)

    assert check_file_size(str(path), 1024, "data_path") is None
    assert check_file_size(str(path), 0, "data_path") is None


def test_check_file_size_ServerError_when_file_too_large(tmp_path):
    """
    Test that a file larger than the limit is `file_too_large`, naming the
    size, the limit and the option that raises it.
    """
    path = tmp_path / "data.csv"
    path.write_bytes(b"x" * (3 * 1024 * 1024 + 1))

    with pytest.raises(ServerError) as info:
        check_file_size(str(path), 2 * 1024 * 1024, "exog_path")

    error = info.value
    assert (error.code, error.field) == ("file_too_large", "exog_path")
    assert str(error) == (
        "The file is 3.0 MB, more than the 2 MB the server reads. Nothing was "
        "read."
    )
    assert "`--max-file-mb`" in error.hint
    assert error.details == {"size_bytes": 3 * 1024 * 1024 + 1, "max_file_mb": 2}


def _write_gzip(path, size: int) -> None:
    """
    Write a gzip file that holds `size` bytes of text and is a few KB.
    """
    path.write_bytes(gzip.compress(b"2020-01-01;1,5\n" * (size // 15)))


def test_check_file_size_ServerError_when_gzip_content_exceeds_the_limit(tmp_path):
    """
    Test that a small '.csv.gz' file whose content is larger than the limit is
    `file_too_large`, with the message of the compressed file, and that it
    passes when the limit is 0 or the content fits.
    """
    path = tmp_path / "data.csv.gz"
    _write_gzip(path, 3 * 1024 * 1024)
    assert path.stat().st_size < 1024 * 1024

    with pytest.raises(ServerError) as info:
        check_file_size(str(path), 2 * 1024 * 1024, "data_path")

    error = info.value
    assert (error.code, error.field) == ("file_too_large", "data_path")
    assert str(error) == (
        f"The file is {path.stat().st_size / (1024 * 1024):.1f} MB compressed "
        f"and more than the 2 MB the server reads once decompressed. Nothing "
        f"was read."
    )
    assert "`--max-file-mb`" in error.hint
    assert error.details == {"size_bytes": path.stat().st_size, "max_file_mb": 2}
    assert check_file_size(str(path), 0, "data_path") is None
    assert check_file_size(str(path), 4 * 1024 * 1024, "data_path") is None


def test_check_file_size_ServerError_when_tsv_gzip_content_exceeds_the_limit(
    tmp_path,
):
    """
    Test that the check of the content applies to '.tsv.gz' and to an
    upper-case '.GZ' extension.
    """
    for name in ("data.tsv.gz", "DATA.CSV.GZ"):
        path = tmp_path / name
        _write_gzip(path, 2 * 1024 * 1024)

        with pytest.raises(ServerError) as info:
            check_file_size(str(path), 1024 * 1024, "data_path")

        assert info.value.code == "file_too_large"


def test_check_file_size_lets_a_damaged_gzip_through(tmp_path):
    """
    Test that a '.csv.gz' file that cannot be decompressed (not gzip, cut,
    empty) passes the check, left for the core to report as unreadable.
    """
    garbage = tmp_path / "garbage.csv.gz"
    garbage.write_bytes(b"this is not gzip at all")
    cut = tmp_path / "cut.csv.gz"
    cut.write_bytes(gzip.compress(b"2020-01-01;1,5\n" * 100000)[:60])
    empty = tmp_path / "empty.csv.gz"
    empty.write_bytes(b"")

    for path in (garbage, cut, empty):
        assert check_file_size(str(path), 1024, "data_path") is None


def test_check_file_size_does_not_decompress_a_plain_file(tmp_path):
    """
    Test that a plain CSV within the limit passes even when its content is
    gzip-looking, because only the extension '.gz' selects the check.
    """
    path = tmp_path / "data.csv"
    path.write_bytes(gzip.compress(b"x" * 100000))

    assert check_file_size(str(path), 1024 * 1024, "data_path") is None

