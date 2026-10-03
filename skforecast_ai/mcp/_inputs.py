################################################################################
#                              MCP server inputs                               #
#                                                                              #
# Paths, fingerprints and text the server accepts from an agent                #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from .._future_exog import _shown
from ..exceptions import InvalidInputError
from ..rendering._helpers import _COMMENT_ESCAPED_CATEGORIES
from ..schemas.profiles import ForecastingProfile
from ._errors import ServerError

# Any `scheme://` prefix: pandas would download it. URLs are not accepted
# (section 10.7 of the design); the agent downloads the file and passes its
# path instead.
_URL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")

# A number written as text: the core reads a string `test_size` or
# `initial_train_size` as a date, so '2012' would be a date for the core and
# an observation count for the agent.
_NUMBER_PATTERN = re.compile(r"\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*")

# Unicode categories of the characters that break a line or control the
# terminal: the ones `_comment_text` escapes in the scripts.
_CONTROL_CATEGORIES = _COMMENT_ESCAPED_CATEGORIES


@dataclass(frozen=True)
class AllowedDir:
    """
    Directory the data and exogenous files must be in.

    Attributes
    ----------
    path : str
        Absolute, normalized path as configured.
    real : str
        The same path with every symbolic link resolved.
    """

    path: str
    real: str

    @classmethod
    def from_path(cls, path: str | Path) -> AllowedDir:
        """
        Resolve the directory given to `--allow-dir`.

        Parameters
        ----------
        path : str, Path
            Directory to allow. It must exist.

        Returns
        -------
        allowed : AllowedDir
            The directory, absolute and with its links resolved.
        """

        absolute = os.path.normpath(os.path.abspath(os.fspath(path)))
        if not os.path.isdir(absolute):
            raise InvalidInputError(
                f"The allowed directory {absolute!r} does not exist or is not a "
                f"directory.",
                field = "allow_dir",
            )
        return cls(path=absolute, real=os.path.realpath(absolute))

    def contains(self, path: str, real: bool = False) -> bool:
        """
        Whether a normalized absolute path is this directory or inside it.

        Parameters
        ----------
        path : str
            Normalized absolute path.
        real : bool, default False
            Whether `path` has its links resolved, so it is compared with
            the resolved directory only.

        Returns
        -------
        inside : bool
            Whether `path` is inside the directory.
        """

        roots = (self.real,) if real else (self.path, self.real)
        return any(_is_within(path, root) for root in roots)


def _is_within(path: str, root: str) -> bool:
    """
    Whether `path` is `root` or below it, both normalized and absolute.
    """

    # normcase: Windows (and macOS by default) ignore the case of paths.
    path, root = os.path.normcase(path), os.path.normcase(root)
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        # Paths on different drives (Windows).
        return False


def has_control_characters(text: str) -> bool:
    """
    Whether a text holds a line break or another control character.

    Parameters
    ----------
    text : str
        Text to check.

    Returns
    -------
    found : bool
        Whether any character is in the Unicode categories Cc, Zl or Zp.
    """

    return any(unicodedata.category(char) in _CONTROL_CATEGORIES for char in text)


def resolve_csv_path(raw: str, allowed: AllowedDir, field: str) -> str:
    """
    Check a path given by the agent and return the file to read.

    The path must be absolute, end in `.csv` and be inside the allowed
    directory. Whether it is inside is checked on the path as written,
    before looking at the file system, so a path outside the directory is
    rejected without saying whether it exists, and again once its symbolic
    links are resolved, so a link cannot lead outside. URLs are rejected.

    Parameters
    ----------
    raw : str
        Path as the agent gave it.
    allowed : AllowedDir
        Directory the file must be in.
    field : str
        Argument of the tool that holds the path, named by the errors.

    Returns
    -------
    path : str
        Absolute path of the file, with its links resolved.
    """

    if _URL_PATTERN.match(raw):
        raise ServerError(
            "URLs are not accepted: download the file into the allowed "
            "directory and pass its absolute path.",
            code    = "url_not_allowed",
            field   = field,
            details = {"path": raw},
        )
    if not raw or "\x00" in raw or has_control_characters(raw):
        raise ServerError(
            "The path is empty or holds a control character.",
            code  = "invalid_path",
            field = field,
        )
    if not os.path.isabs(raw):
        raise ServerError(
            f"The path {raw!r} is not absolute: pass the absolute path of the "
            f"file (relative paths and '~' are not expanded).",
            code    = "invalid_path",
            field   = field,
            details = {"path": raw},
        )
    normalized = os.path.normpath(raw)
    if Path(normalized).suffix.lower() != ".csv":
        raise ServerError(
            f"The path {raw!r} is not a CSV file: it must end in '.csv'.",
            code    = "invalid_path",
            field   = field,
            details = {"path": raw},
        )
    if not allowed.contains(normalized):
        raise ServerError(
            f"The path {raw!r} is outside the directory the server may read.",
            code    = "path_not_allowed",
            field   = field,
            hint    = f"Use a file inside {allowed.path!r}.",
            details = {"path": raw, "allowed_dir": allowed.path},
        )
    real = os.path.realpath(normalized)
    if not allowed.contains(real, real=True) or Path(real).suffix.lower() != ".csv":
        raise ServerError(
            f"The path {raw!r} is a link to a file outside the directory the "
            f"server may read, or to a file that is not a CSV.",
            code    = "path_not_allowed",
            field   = field,
            hint    = f"Use a file inside {allowed.path!r}.",
            details = {"path": raw, "allowed_dir": allowed.path},
        )
    if not os.path.isfile(real):
        raise ServerError(
            f"CSV file not found: {raw!r}.",
            code    = "data_not_found",
            field   = field,
            details = {"path": raw},
        )

    return real


def check_file_size(path: str, max_bytes: int, field: str) -> None:
    """
    Reject a file larger than the limit of the server, before reading it.

    Parameters
    ----------
    path : str
        Path of the file, resolved by `resolve_csv_path`.
    max_bytes : int
        Largest size accepted, in bytes; 0 accepts any size.
    field : str
        Argument of the tool that holds the path.

    Returns
    -------
    None
    """

    if max_bytes == 0:
        return
    size = os.path.getsize(path)
    if size > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise ServerError(
            f"The file is {size / (1024 * 1024):.1f} MB, more than the "
            f"{limit_mb} MB the server reads. Nothing was read.",
            code    = "file_too_large",
            field   = field,
            hint    = (
                "Pass a smaller file (for example the recent history only), "
                "or ask the user to restart the server with a larger "
                "`--max-file-mb` (0 for no limit)."
            ),
            details = {"size_bytes": size, "max_file_mb": limit_mb},
        )


def file_sha256(path: str) -> str:
    """
    Fingerprint of a file, to notice that it changed between two reads.

    Parameters
    ----------
    path : str
        Path of the file.

    Returns
    -------
    digest : str
        Hexadecimal SHA-256 of its bytes.
    """

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)

    return digest.hexdigest()


def check_unchanged(
    path: str,
    expected: str,
    field: str,
    profiled: bool = False,
    max_bytes: int = 0,
) -> None:
    """
    Raise `data_changed` when a file no longer has the expected fingerprint.

    Parameters
    ----------
    path : str
        Path of the file.
    expected : str
        SHA-256 the file had.
    field : str
        Argument of the tool the file came from.
    profiled : bool, default False
        Whether `expected` is the fingerprint the file had when it was
        profiled (checked before a call reads it again), rather than at the
        start of the call.
    max_bytes : int, default 0
        Largest file the server reads. A profiled file larger than it now
        changed since it was profiled (it was read then), so it is reported
        without hashing it. 0 hashes any size.

    Returns
    -------
    None
    """

    grown = profiled and max_bytes > 0 and os.path.getsize(path) > max_bytes
    if not grown and file_sha256(path) == expected:
        return
    if profiled:
        message = (
            f"The file {path!r} changed since it was profiled, so its profile "
            f"and the objects built from it no longer describe it. Nothing was "
            f"run."
        )
    else:
        message = (
            f"The file {path!r} changed while the server was using it, so the "
            f"result would not describe one version of the data. Nothing was "
            f"registered."
        )

    # The data is profiled; the future exogenous values are only read.
    if field == "data_path":
        hint = "Call `profile` again on the file as it is now."
    else:
        hint = "Call the tool again once the file no longer changes."

    raise ServerError(
        message,
        code    = "data_changed",
        field   = field,
        hint    = hint,
        details = {"path": path},
    )


def check_not_numeric_text(value: object, field: str) -> None:
    """
    Reject a number written as text, which the core would read as a date.

    Parameters
    ----------
    value : object
        Value of the argument.
    field : str
        Name of the argument.

    Returns
    -------
    None
    """

    if isinstance(value, str) and _NUMBER_PATTERN.fullmatch(value):
        raise ServerError(
            f"`{field}` is the text {value!r}: pass a number (without quotes) "
            f"for a count of observations, or an ISO 8601 date such as "
            f"'2012-01-01' for a date.",
            code  = "invalid_argument",
            field = field,
        )


def check_text_argument(value: str | list[str] | None, field: str) -> None:
    """
    Reject a column name given by the agent that holds a control character.

    Parameters
    ----------
    value : str, list of str, None
        Value of the argument.
    field : str
        Name of the argument.

    Returns
    -------
    None
    """

    values = [value] if isinstance(value, str) else list(value or [])
    bad = [text for text in values if has_control_characters(text)]
    if bad:
        raise ServerError(
            f"`{field}` holds a line break or another control character: "
            f"{_shown(bad)}.",
            code  = "invalid_argument",
            field = field,
        )


def check_profile_names(profile: ForecastingProfile) -> None:
    """
    Reject data whose column names or series ids hold a control character.

    Those names reach the agent in the summary of every object built from
    the data, so a line break in them could be read as a new section of the
    text. The core accepts them (a spreadsheet header written with
    Alt+Enter is a valid column name), so the check is made here, on the
    names the profile records.

    Parameters
    ----------
    profile : ForecastingProfile
        Profile of the data.

    Returns
    -------
    None
    """

    data_profile = profile.data_profile
    targets = data_profile.target
    names = [targets] if isinstance(targets, str) else list(targets)
    names += list(data_profile.series_lengths)
    names += list(data_profile.exog_columns)
    names += [data_profile.date_column, data_profile.series_id_column]
    bad = list(dict.fromkeys(
        str(name) for name in names
        if name is not None and has_control_characters(str(name))
    ))
    if bad:
        raise ServerError(
            f"The data has column names or series ids with a line break or "
            f"another control character: {_shown(bad)}. The server does not "
            f"accept them, since they reach the agent as text.",
            code  = "invalid_argument",
            field = "data_path",
            hint  = "Rename those columns (or series) in the CSV file.",
        )
