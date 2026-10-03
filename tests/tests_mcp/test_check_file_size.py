# Unit test check_file_size

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
