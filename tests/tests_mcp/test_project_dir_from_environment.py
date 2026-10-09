# Unit test project_dir_from_environment

import os
import re
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.mcp._inputs import project_dir_from_environment


def test_project_dir_from_environment_output(tmp_path, monkeypatch):
    """
    Test that the directory of `CLAUDE_PROJECT_DIR` is returned as given,
    also when it is below the home directory.
    """
    project = tmp_path / "home" / "project"
    project.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))

    assert project_dir_from_environment() == str(project)


@pytest.mark.parametrize("value", [None, ""], ids=lambda v: f"value: {v!r}")
def test_project_dir_from_environment_InvalidInputError_when_not_set(
    monkeypatch, value
):
    """
    Test that a missing or empty `CLAUDE_PROJECT_DIR` raises
    `InvalidInputError` naming `allow_project_dir` and `--allow-dir` as the
    alternative.
    """
    if value is None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    else:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", value)

    err_msg = re.escape(
        "`--allow-project-dir` needs the environment variable "
        "`CLAUDE_PROJECT_DIR`, which Claude Code sets to the project of "
        "the session, and it is not set. Give the directory with "
        "`--allow-dir` instead."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as excinfo:
        project_dir_from_environment()

    assert excinfo.value.field == "allow_project_dir"


@pytest.mark.parametrize(
    "place", ["home", "home through a link", "parent of home", "root"]
)
def test_project_dir_from_environment_InvalidInputError_when_home_or_root(
    tmp_path, monkeypatch, place
):
    """
    Test that the home directory, also through a symbolic link, a directory
    that contains it and the root of the file system raise
    `InvalidInputError`: a session opened there is not a project.
    """
    home = tmp_path / "users" / "home"
    home.mkdir(parents=True)
    os.symlink(home, tmp_path / "alias")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    given = {
        "home"               : str(home),
        "home through a link": str(tmp_path / "alias"),
        "parent of home"     : str(tmp_path / "users"),
        "root"               : os.path.abspath(os.sep),
    }[place]
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", given)

    err_msg = re.escape(
        f"`--allow-project-dir` does not accept {given!r}: the home "
        f"directory, a directory that contains it or the root of a file "
        f"system, where the server would read every CSV file of the "
        f"user. Start the agent in the directory of the project, or "
        f"give a directory with `--allow-dir`."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as excinfo:
        project_dir_from_environment()

    assert excinfo.value.field == "allow_project_dir"
