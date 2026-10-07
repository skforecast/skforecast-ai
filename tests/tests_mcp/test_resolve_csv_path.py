# Unit test resolve_csv_path

import os
import re
import pytest

from skforecast_ai.mcp._errors import ServerError
from skforecast_ai.mcp._inputs import AllowedDir, resolve_csv_path


def _layout(tmp_path):
    """
    Build an allowed directory with a CSV file, a directory outside it with
    another CSV file, and return them.
    """
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (allowed / "data.csv").write_text("date,y\n2020-01-01,1\n")
    (outside / "secret.csv").write_text("date,y\n2020-01-01,1\n")

    return allowed, outside


def test_resolve_csv_path_output_when_file_inside_allowed_dir(tmp_path):
    """
    Test that an absolute path of a CSV file inside the allowed directory is
    returned with its links resolved, also when written with '..' that stays
    inside, and with an upper-case extension.
    """
    allowed, _ = _layout(tmp_path)
    (allowed / "UPPER.CSV").write_text("date,y\n2020-01-01,1\n")
    allowed_dir = AllowedDir.from_path(allowed)

    path = resolve_csv_path(str(allowed / "data.csv"), allowed_dir, "data_path")
    dotted = resolve_csv_path(
        str(allowed / "sub" / ".." / "data.csv"), allowed_dir, "data_path"
    )
    upper = resolve_csv_path(str(allowed / "UPPER.CSV"), allowed_dir, "data_path")

    assert path == os.path.realpath(allowed / "data.csv")
    assert dotted == path
    assert upper == os.path.realpath(allowed / "UPPER.CSV")


@pytest.mark.parametrize(
    "raw, code",
    [
        ("https://example.org/data.csv", "url_not_allowed"),
        ("file:///etc/data.csv", "url_not_allowed"),
        ("s3://bucket/data.csv", "url_not_allowed"),
        ("data.csv", "invalid_path"),
        ("~/data.csv", "invalid_path"),
        ("", "invalid_path"),
        ("/tmp/da\x00ta.csv", "invalid_path"),
        ("/tmp/da\nta.csv", "invalid_path"),
        ("/tmp/data.txt", "invalid_path"),
        ("/tmp/data.csv.gz", "invalid_path"),
    ],
    ids=lambda dt: f"raw: {dt!r}",
)
def test_resolve_csv_path_ServerError_when_path_is_not_an_absolute_csv(
    tmp_path, raw, code
):
    """
    Test that URLs, relative paths, paths with a control character and paths
    that do not end in '.csv' are rejected with their code, naming the field.
    """
    allowed, _ = _layout(tmp_path)

    with pytest.raises(ServerError) as excinfo:
        resolve_csv_path(raw, AllowedDir.from_path(allowed), "data_path")

    assert excinfo.value.code == code
    assert excinfo.value.field == "data_path"


@pytest.mark.parametrize(
    "relative",
    ["../outside/secret.csv", "../outside/missing.csv", "../../etc/passwd.csv"],
    ids=lambda dt: f"relative: {dt}",
)
def test_resolve_csv_path_ServerError_when_path_outside_allowed_dir(tmp_path, relative):
    """
    Test that a path outside the allowed directory is rejected with
    `path_not_allowed` whether the file exists or not, so the error does not
    tell an agent which files exist outside.
    """
    allowed, _ = _layout(tmp_path)
    raw = str(allowed) + os.sep + relative

    with pytest.raises(
        ServerError,
        match=re.escape(
            f"The path {raw!r} is outside the directory the server may read."
        ),
    ) as excinfo:
        resolve_csv_path(raw, AllowedDir.from_path(allowed), "exog_path")

    assert excinfo.value.code == "path_not_allowed"
    assert excinfo.value.field == "exog_path"
    assert excinfo.value.hint == (
        f"Do not copy or move the file yourself. Tell the user that the "
        f"server only reads inside {str(allowed)!r}: they can copy the file "
        f"there, or restart the server with `--allow-dir` set to the "
        f"directory of the file."
    )
    assert excinfo.value.details == {"path": raw, "allowed_dir": str(allowed)}


@pytest.mark.parametrize(
    "raw", ["data.csv", "sub/data.csv", "~/data.csv"], ids=lambda dt: f"raw: {dt}"
)
def test_resolve_csv_path_relative_path_names_the_allowed_dir(tmp_path, raw):
    """
    Test that the error of a relative path names the directory the server
    reads, in its hint and its details, so the agent can build the absolute
    path without searching the file system.
    """
    allowed, _ = _layout(tmp_path)

    with pytest.raises(ServerError) as excinfo:
        resolve_csv_path(raw, AllowedDir.from_path(allowed), "data_path")

    assert excinfo.value.code == "invalid_path"
    assert excinfo.value.hint == (
        f"The server reads CSV files inside {str(allowed)!r}."
    )
    assert excinfo.value.details == {"path": raw, "allowed_dir": str(allowed)}


def test_resolve_csv_path_ServerError_when_symlink_points_outside(tmp_path):
    """
    Test that a link inside the allowed directory to a file outside it, or
    to a file that is not a CSV, is rejected with `path_not_allowed`.
    """
    allowed, outside = _layout(tmp_path)
    (allowed / "secret.txt").write_text("date,y\n2020-01-01,1\n")
    os.symlink(outside / "secret.csv", allowed / "link.csv")
    os.symlink(allowed / "secret.txt", allowed / "text.csv")
    allowed_dir = AllowedDir.from_path(allowed)

    for name in ("link.csv", "text.csv"):
        with pytest.raises(ServerError) as excinfo:
            resolve_csv_path(str(allowed / name), allowed_dir, "data_path")
        assert excinfo.value.code == "path_not_allowed"


def test_resolve_csv_path_ServerError_when_file_not_found(tmp_path):
    """
    Test that a missing file, or a directory, inside the allowed directory
    is `data_not_found`.
    """
    allowed, _ = _layout(tmp_path)
    (allowed / "folder.csv").mkdir()
    allowed_dir = AllowedDir.from_path(allowed)

    for name in ("missing.csv", "folder.csv"):
        with pytest.raises(ServerError) as excinfo:
            resolve_csv_path(str(allowed / name), allowed_dir, "data_path")
        assert excinfo.value.code == "data_not_found"
