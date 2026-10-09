# Unit test check_unchanged

import pytest

from skforecast_ai.mcp._errors import ServerError
from skforecast_ai.mcp._inputs import check_unchanged, file_sha256


def test_check_unchanged_passes_and_raises_data_changed(tmp_path):
    """
    Test that a file with its fingerprint passes, and that a file that
    changed raises `data_changed` naming the argument.
    """
    path = tmp_path / "data.csv"
    # As bytes: the text mode of Windows writes other line ends, and so
    # another fingerprint.
    path.write_bytes(b"date,y\n2020-01-01,1\n")
    digest = file_sha256(str(path))

    check_unchanged(str(path), digest, "data_path")
    path.write_text("date,y\n2020-01-01,2\n")
    with pytest.raises(ServerError) as excinfo:
        check_unchanged(str(path), digest, "exog_path")

    assert digest == "fccc6e599b960d79f12a072e45c55acdb1286a846b09655152cdf861f82fc712"
    assert excinfo.value.code == "data_changed"
    assert excinfo.value.field == "exog_path"
    assert excinfo.value.details == {"path": str(path)}


def test_check_unchanged_message_when_changed_since_profiled(tmp_path):
    """
    Test the message of a file that changed since it was profiled, checked
    before a call reads it again.
    """
    path = tmp_path / "data.csv"
    path.write_text("date,y\n2020-01-01,1\n")
    digest = file_sha256(str(path))
    path.write_text("date,y\n2020-01-01,2\n")

    with pytest.raises(ServerError) as excinfo:
        check_unchanged(str(path), digest, "data_path", profiled=True)

    assert str(excinfo.value) == (
        f"The file {str(path)!r} changed since it was profiled, so its profile and "
        f"the objects built from it no longer describe it. Nothing was run."
    )
    assert excinfo.value.hint == "Call `profile` again on the file as it is now."


def test_check_unchanged_profiled_file_larger_than_the_limit_is_not_hashed(
    tmp_path, monkeypatch
):
    """
    Test that a profiled file now larger than `max_bytes` (it was within the
    limit when profiled, so it changed) is `data_changed` without being
    hashed, and that a file within the limit is hashed as before.
    """
    from skforecast_ai.mcp import _inputs

    path = tmp_path / "data.csv"
    path.write_text("date,y\n2020-01-01,1\n")
    digest = file_sha256(str(path))
    hashed = []
    original = _inputs.file_sha256
    monkeypatch.setattr(
        _inputs, "file_sha256", lambda p: hashed.append(p) or original(p)
    )

    check_unchanged(str(path), digest, "data_path", profiled=True, max_bytes=1024)
    path.write_text("date,y\n" + "2020-01-01,1\n" * 100)
    with pytest.raises(ServerError) as excinfo:
        check_unchanged(str(path), digest, "data_path", profiled=True, max_bytes=1024)

    assert hashed == [str(path)]
    assert excinfo.value.code == "data_changed"
