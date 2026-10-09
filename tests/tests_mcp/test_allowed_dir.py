# Unit test AllowedDir

import os
import re
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.mcp._inputs import AllowedDir, resolve_csv_path


def test_AllowedDir_from_path_output_when_allowed_dir_is_a_link(tmp_path):
    """
    Test that an allowed directory given through a symbolic link accepts the
    paths written through the link and through the real directory.
    """
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "data.csv").write_text("date,y\n2020-01-01,1\n")
    os.symlink(allowed, tmp_path / "alias")
    allowed_dir = AllowedDir.from_path(tmp_path / "alias")

    through_link = resolve_csv_path(
        str(tmp_path / "alias" / "data.csv"), allowed_dir, "data_path"
    )
    through_real = resolve_csv_path(str(allowed / "data.csv"), allowed_dir, "data_path")

    assert through_link == through_real == os.path.realpath(allowed / "data.csv")


def test_AllowedDir_contains_output(tmp_path):
    """
    Test that the directory itself and the paths below it are inside, and
    that a sibling whose name starts like it is not.
    """
    allowed = AllowedDir(path=str(tmp_path / "data"), real=str(tmp_path / "data"))

    assert allowed.contains(str(tmp_path / "data"))
    assert allowed.contains(str(tmp_path / "data" / "a" / "b.csv"))
    assert not allowed.contains(str(tmp_path / "data2" / "b.csv"))
    assert not allowed.contains(str(tmp_path))


def test_AllowedDir_from_path_InvalidInputError_when_not_a_directory(tmp_path):
    """
    Test that an allowed directory that does not exist raises
    `InvalidInputError` naming `allow_dir`.
    """
    missing = tmp_path / "missing"
    err_msg = re.escape(
        f"The allowed directory {str(missing)!r} does not exist or is not a directory."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as excinfo:
        AllowedDir.from_path(missing)

    assert excinfo.value.field == "allow_dir"


@pytest.mark.parametrize("path", ["", ".", "data", "../data", "~/data"])
def test_AllowedDir_from_path_InvalidInputError_when_not_absolute(
    tmp_path, monkeypatch, path
):
    """
    Test that an empty or relative allowed directory raises instead of
    resolving against the working directory: a client that expands an unset
    variable to nothing would make the server read the CSV files of wherever
    it was started.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    err_msg = re.escape(
        f"The allowed directory must be an absolute path, got {path!r}."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as excinfo:
        AllowedDir.from_path(path)

    assert excinfo.value.field == "allow_dir"
