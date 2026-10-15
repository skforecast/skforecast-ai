################################################################################
#                               CSV dialect                                    #
#                                                                              #
# Separator and decimal mark of a CSV file, told from its first lines          #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations

import bz2
import csv
import gzip
import io
import lzma
import re
import urllib.request
import zlib
from pathlib import Path

from ..exceptions import InvalidInputError

# Separators and decimal marks a CSV file may be written with. The first of
# each is the one `pandas.read_csv` reads by default.
CSV_SEPARATORS = (",", ";", "\t")
CSV_DECIMALS = (".", ",")
DEFAULT_CSV_SEP = ","
DEFAULT_CSV_DECIMAL = "."

# Bytes read from the start of a file to tell how it is written. Always the
# same bytes of the same file, so the same file gives the same answer.
SAMPLE_BYTES = 256 * 1024

# Compressed files pandas reads from their extension, with what opens them
# here. Other extensions pandas decompresses ('.zip', '.zst', '.tar') are
# read as before, with ',' and '.'.
_OPENERS = {".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open}

# Errors of a compressed file that cannot be decompressed.
DECOMPRESSION_ERRORS = (gzip.BadGzipFile, EOFError, zlib.error, lzma.LZMAError)

_SEPARATOR_NAMES = {",": "','", ";": "';'", "\t": "a tabulator"}

# A number with decimals written with each mark, and nothing else in the
# field.
DECIMAL_NUMBERS = {
    ",": re.compile(r"[+-]?\d+,\d+(?:[eE][+-]?\d+)?"),
    ".": re.compile(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?"),
}

# A number that reads both as thousands separated by ',' and as a number
# with three decimals ('1,234'): alone, it does not tell the decimal mark
# of a file separated by tabulators. With ';' the ',' is the decimal mark:
# a spreadsheet separates with ';' where ',' is the decimal mark.
THOUSANDS = re.compile(r"[+-]?[1-9]\d{0,2}(?:,\d{3})+")

DIALECT_HINT = (
    "Profile the file saying how it is written, with `sep` (',', ';' or a "
    "tabulator) and `decimal` ('.' or ',') in `profile()`, `--sep` and "
    "`--decimal` in the `profile` command, or `sep` and `decimal` in the "
    "`profile` tool of the MCP server, and use that profile."
)

EXOG_DIALECT_HINT = (
    "Write the file with ',' as separator and '.' as decimal mark, as "
    "`DataFrame.to_csv()` writes it, without ';' or tabulators in the column "
    "names."
)


class CsvDialectError(InvalidInputError):
    """
    Raised when the separator or the decimal mark of a CSV file cannot be
    told. An `InvalidInputError` with code `'data_unreadable'` for the
    caller; its own class so a workflow that holds a profile of the file
    can read it as the profile says instead.
    """


def decimal_in_both_error(
    source: str,
    field: str,
    with_comma: str,
    with_point: str,
) -> InvalidInputError:
    """
    Return the error of a CSV file that holds numbers written with both
    decimal marks, quoting one of each.
    """
    return CsvDialectError(
        f"The decimal mark of the CSV file '{source}' cannot be told: it "
        f"holds numbers written with ',' (such as {with_comma[:20]!r}) and "
        f"with '.' (such as {with_point[:20]!r}).",
        code  = "data_unreadable",
        field = field,
        hint  = DIALECT_HINT if field == "data" else EXOG_DIALECT_HINT,
    )


def only_thousands_error(source: str, field: str, example: str) -> InvalidInputError:
    """
    Return the error of a CSV file whose only numbers with a `','` also
    read as thousands, quoting one.
    """
    return CsvDialectError(
        f"The decimal mark of the CSV file '{source}' cannot be told: its "
        f"numbers with a ',' (such as {example[:20]!r}) read both as "
        f"thousands and as numbers with three decimals.",
        code  = "data_unreadable",
        field = field,
        hint  = DIALECT_HINT if field == "data" else EXOG_DIALECT_HINT,
    )


def check_csv_dialect(sep: str | None, decimal: str | None) -> None:
    """
    Check the separator and the decimal mark given by the caller.

    Parameters
    ----------
    sep : str, None
        Separator of the fields: `','`, `';'` or a tabulator. None when it
        is not given.
    decimal : str, None
        Decimal mark: `'.'` or `','`. None when it is not given.

    Returns
    -------
    None
    """

    if sep is not None and sep not in CSV_SEPARATORS:
        raise InvalidInputError(
            f"`sep` must be ',', ';' or a tabulator ('\\t'), got {sep!r}.",
            field = "sep",
        )
    if decimal is not None and decimal not in CSV_DECIMALS:
        raise InvalidInputError(
            f"`decimal` must be '.' or ',', got {decimal!r}.",
            field = "decimal",
        )
    if decimal == "," and sep == ",":
        raise InvalidInputError(
            "`decimal` cannot be ',' when `sep` is ',': the same character "
            "would separate the fields and the decimals.",
            field = "decimal",
        )


def read_sample(path: str | Path) -> str | None:
    """
    Read the start of a CSV file as text, decompressed when its extension
    says it is compressed, to tell how the file is written.

    Parameters
    ----------
    path : str, Path
        Path of the file.

    Returns
    -------
    sample : str, None
        Text of the complete lines within the first `SAMPLE_BYTES` bytes.
        None when the file cannot be opened or decompressed here, which is
        left for `pandas.read_csv` to report.
    """

    opener = _OPENERS.get(Path(str(path)).suffix.lower(), open)
    try:
        with opener(path, "rb") as handle:
            raw = handle.read(SAMPLE_BYTES + 1)
    except (OSError, *DECOMPRESSION_ERRORS):
        return None

    return sample_text(raw)


def read_row_lengths(path: str | Path, sep: str) -> list[int] | None:
    """
    Count the fields of every row of a CSV file after its header, as
    `pandas.read_csv` splits them, decompressed when its extension says it
    is compressed.

    `pandas.read_csv` fills the missing fields of a row shorter than the
    header with missing values, so its result cannot tell an empty last
    field from a missing one; the counts can.

    Parameters
    ----------
    path : str, Path
        Path of the file.
    sep : str
        Separator of the fields.

    Returns
    -------
    lengths : list of int, None
        Number of fields of each row after the header, blank lines left
        out as pandas leaves them out. None when the file cannot be opened,
        decompressed or decoded here.
    """

    opener = _OPENERS.get(Path(str(path)).suffix.lower(), open)
    try:
        with opener(path, "rt", encoding="utf-8", newline="") as handle:
            rows = csv.reader(handle, delimiter=sep)
            next(rows, None)
            return [
                len(row) for row in rows
                if len(row) > 1 or (row and row[0].strip())
            ]
    except (OSError, UnicodeDecodeError, csv.Error, *DECOMPRESSION_ERRORS):
        return None


def read_url_sample(url: str) -> str | None:
    """
    Read the start of a CSV file served at a URL, as `read_sample` reads
    the start of a local file.

    Parameters
    ----------
    url : str
        URL of the file ('http://' or 'https://').

    Returns
    -------
    sample : str, None
        Text of the complete lines within the first `SAMPLE_BYTES` bytes
        (of the content, when it is gzip). None when it cannot be read
        here, which is left for `pandas.read_csv` to report.
    """

    try:
        with urllib.request.urlopen(url) as response:
            raw = response.read(SAMPLE_BYTES + 1)
    except (OSError, ValueError):
        return None
    cut = len(raw) > SAMPLE_BYTES
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = zlib.decompressobj(wbits=31).decompress(raw, SAMPLE_BYTES + 1)
        except zlib.error:
            return None

    return sample_text(raw, cut=cut)


def sample_text(raw: bytes, cut: bool = False) -> str | None:
    """
    Return the text of the complete lines within the first `SAMPLE_BYTES`
    bytes of the content of a CSV file.

    Parameters
    ----------
    raw : bytes
        Content of the file, or its start.
    cut : bool, default False
        Whether `raw` is known to end before the content does, although it
        is not longer than `SAMPLE_BYTES`.

    Returns
    -------
    sample : str, None
        Text of the sample, without the line cut by the limit. None when it
        is not UTF-8, which `pandas.read_csv` reports when it reads the
        file.
    """

    if cut or len(raw) > SAMPLE_BYTES:
        # The last line is cut, and with it a character of several bytes.
        raw = raw[: raw.rfind(b"\n", 0, SAMPLE_BYTES) + 1]
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _records(sample: str, sep: str) -> list[list[str]] | None:
    """
    Split the sample into records and fields with a separator, reading the
    quotes as pandas does. None when the sample cannot be read with it.
    """
    try:
        return [
            record
            for record in csv.reader(io.StringIO(sample, newline=""), delimiter=sep)
            if record
        ]
    except csv.Error:
        return None


def detect_csv_dialect(
    sample: str,
    source: str,
    field: str = "data",
    sep: str | None = None,
    decimal: str | None = None,
) -> tuple[str, str]:
    """
    Tell the separator and the decimal mark of a CSV file from its start.

    The separator is the only one of `','`, `';'` and the tabulator that
    splits the header in more than one field and every record of the sample
    in as many fields as the header. When none does (rows of different
    lengths, which pandas reads or reports), it is the only one found in
    the header, and `','` when the header holds none, as before. The decimal
    mark is `','` only when the separator is not `','` and the sample holds
    numbers written as `'1,5'` and none written as `'1.5'`.
    In a file separated by tabulators, numbers such as `'1,234'`, which also
    read as thousands, do not tell the decimal mark when no other number has
    a `','`; with `';'` they are numbers with three decimals.

    Parameters
    ----------
    sample : str
        Start of the file (see `sample_text`).
    source : str
        Path or URL of the file, named by the error.
    field : str, default 'data'
        Argument that named the file, reported with the error.
    sep : str, default None
        Separator given by the caller, which is then not detected.
    decimal : str, default None
        Decimal mark given by the caller, which is then not detected.

    Returns
    -------
    sep : str
        Separator of the fields.
    decimal : str
        Decimal mark.

    Notes
    -----
    A file that reads with more than one separator, that holds numbers
    written with both decimal marks, or that is separated by tabulators and
    whose only numbers with a `','` also read as thousands, raises `InvalidInputError` with code
    `'data_unreadable'` and a hint that says how to give them: the dialect
    is never guessed.
    """

    hint = DIALECT_HINT if field == "data" else EXOG_DIALECT_HINT
    records = {}
    if sep is None:
        # No other separator in the sample: the file is read as before.
        candidates = [
            candidate for candidate in CSV_SEPARATORS
            if candidate == DEFAULT_CSV_SEP or candidate in sample
        ]
        if len(candidates) > 1:
            parsed = {
                candidate: _records(sample, candidate) for candidate in candidates
            }
            records = {
                candidate: rows for candidate, rows in parsed.items() if rows
            }
            in_header = [
                candidate for candidate, rows in records.items()
                if len(rows[0]) > 1
            ]
            regular = [
                candidate for candidate in in_header
                if len({len(row) for row in records[candidate]}) == 1
            ]
            found = regular or in_header
            if len(found) > 1:
                readings = " and ".join(
                    f"{_SEPARATOR_NAMES[candidate]} "
                    f"({len(records[candidate][0])} columns)"
                    for candidate in found
                )
                raise CsvDialectError(
                    f"The separator of the CSV file '{source}' cannot be told: "
                    f"its header reads with {readings}.",
                    code  = "data_unreadable",
                    field = field,
                    hint  = hint,
                )
            sep = found[0] if found else DEFAULT_CSV_SEP
        else:
            sep = DEFAULT_CSV_SEP

    if decimal is None:
        decimal = DEFAULT_CSV_DECIMAL
        if sep != DEFAULT_CSV_SEP and "," in sample:
            rows = records.get(sep) or _records(sample, sep) or []
            counts = {mark: 0 for mark in CSV_DECIMALS}
            examples = {}
            only_thousands = True
            for row in rows[1:]:
                for value in row:
                    value = value.strip()
                    for mark, pattern in DECIMAL_NUMBERS.items():
                        if pattern.fullmatch(value):
                            counts[mark] += 1
                            examples.setdefault(mark, value)
                            if mark == "," and not THOUSANDS.fullmatch(value):
                                only_thousands = False
            if counts[","] and counts["."]:
                raise decimal_in_both_error(
                    source, field, examples[","], examples["."]
                )
            if counts[","] and only_thousands and sep == "\t":
                raise only_thousands_error(source, field, examples[","])
            if counts[","]:
                decimal = ","

    return sep, decimal
