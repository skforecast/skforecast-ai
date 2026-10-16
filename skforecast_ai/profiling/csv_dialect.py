################################################################################
#                               CSV dialect                                    #
#                                                                              #
# Separator, decimal mark and thousands separator of a CSV file, told from     #
# its first lines                                                              #
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

# Thousands separators a CSV file may be written with besides none, the
# default of `pandas.read_csv`: '.', which goes with ',' as decimal mark (the
# spreadsheets of most of Europe write '1.705,11').
CSV_THOUSANDS = (".",)

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

# A number with '.' between its thousands, and decimals after a ',' or none,
# and nothing else in the field: '1.705', '1.234.567', '1.705,11'. With one
# '.' and no ',' it also reads as a number with three decimals ('12.345').
DOT_THOUSANDS = re.compile(r"[+-]?[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?")

# A whole number without separators, as '870', of at most three digits: a
# file that separates thousands writes larger ones with a '.'.
SHORT_WHOLE_NUMBER = re.compile(r"[+-]?\d{1,3}")
WHOLE_NUMBER = re.compile(r"[+-]?\d+")

# A field that `pandas.read_csv` reads as a number with '.' as thousands
# separator, which drops every '.' of it wherever it is: '15.01.2020' is read
# as 15012020 and '0.5' as 5.
DOTTED_NUMBER = re.compile(r"[+-]?[\d.]*\d[\d.]*(?:,\d*)?(?:[eE][+-]?\d+)?")

DIALECT_HINT = (
    "Profile the file saying how it is written, with `sep` (',', ';' or a "
    "tabulator) and `decimal` ('.' or ',') in `profile()`, `--sep` and "
    "`--decimal` in the `profile` command, or `sep` and `decimal` in the "
    "`profile` tool of the MCP server, and use that profile."
)

THOUSANDS_HINT = (
    "Profile the file saying what its '.' is: `thousands` '.' when it "
    "separates the thousands, or `decimal` '.' when it is the decimal mark, "
    "in `profile()`, `--thousands` or `--decimal` in the `profile` command, "
    "or `thousands` or `decimal` in the `profile` tool of the MCP server, "
    "and use that profile."
)

# Hint of a file that holds '.' both between thousands and elsewhere. When
# its '.' is the decimal mark (a column of whole numbers and '1.375' next to
# '0.75'), `decimal` reads it; otherwise only a copy without the other
# points does, as pandas drops every '.' of a number. The file belongs to
# whoever gave it, so that copy is written only with their consent.
DOTTED_VALUES_HINT = (
    "When '.' is the decimal mark of the file, profile it with `decimal` "
    "'.' (`--decimal` in the `profile` command, `decimal` in the `profile` "
    "tool of the MCP server). Otherwise write a copy of the file with '.' "
    "only between the thousands of its numbers (dates such as '2020-01-15') "
    "and pass that copy; if the file is not yours, ask its owner before "
    "writing it."
)

EXOG_DIALECT_HINT = (
    "Write the file with ',' as separator and '.' as decimal mark, as "
    "`DataFrame.to_csv()` writes it, without ';' or tabulators in the column "
    "names."
)


class CsvDialectError(InvalidInputError):
    """
    Raised when the separator, the decimal mark or the thousands separator
    of a CSV file cannot be told. An `InvalidInputError` with code
    `'data_unreadable'` for the caller; its own class so a workflow that
    holds a profile of the file can read it as the profile says instead.
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


def ambiguous_thousands_error(
    source: str,
    field: str,
    example: str,
) -> InvalidInputError:
    """
    Return the error of a CSV file whose only numbers with a `'.'` also
    read as thousands, quoting one.
    """
    return CsvDialectError(
        f"The thousands separator of the CSV file '{source}' cannot be told: "
        f"its numbers with a '.' (such as {example[:20]!r}) read both as "
        f"thousands and as numbers with three decimals.",
        code  = "data_unreadable",
        field = field,
        hint  = THOUSANDS_HINT if field == "data" else EXOG_DIALECT_HINT,
    )


def dotted_values_error(
    source: str,
    field: str,
    other: str,
    with_thousands: str | None = None,
) -> InvalidInputError:
    """
    Return the error of a CSV file read with `'.'` as thousands separator
    that holds values with a `'.'` that does not separate thousands, which
    pandas would read as numbers without it. Quotes one of them and, when
    the separator was detected, a number written with it.
    """
    values = (
        f"values with a '.' that does not separate thousands (such as "
        f"{other[:20]!r}), which pandas would read as numbers without it."
    )
    if with_thousands is None:
        message = (
            f"The CSV file '{source}' cannot be read with '.' as thousands "
            f"separator: it holds {values}"
        )
    else:
        message = (
            f"The CSV file '{source}' cannot be read: it holds numbers with "
            f"'.' between the thousands (such as {with_thousands[:20]!r}) and "
            f"{values}"
        )
    return CsvDialectError(
        message,
        code  = "data_unreadable",
        field = field,
        hint  = DOTTED_VALUES_HINT if field == "data" else EXOG_DIALECT_HINT,
    )


def check_csv_dialect(
    sep: str | None,
    decimal: str | None,
    thousands: str | None = None,
) -> None:
    """
    Check the separator, the decimal mark and the thousands separator given
    by the caller.

    Parameters
    ----------
    sep : str, None
        Separator of the fields: `','`, `';'` or a tabulator. None when it
        is not given.
    decimal : str, None
        Decimal mark: `'.'` or `','`. None when it is not given.
    thousands : str, default None
        Thousands separator: `'.'`, which needs `','` as decimal mark. None
        when it is not given.

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
    if thousands is not None and thousands not in CSV_THOUSANDS:
        raise InvalidInputError(
            f"`thousands` must be '.', got {thousands!r}.",
            field = "thousands",
        )
    if thousands is not None and sep == DEFAULT_CSV_SEP:
        raise InvalidInputError(
            "`thousands` cannot be '.' when `sep` is ',': '.' separates the "
            "thousands where ',' is the decimal mark, which cannot also "
            "separate the fields.",
            field = "thousands",
        )
    if thousands is not None and decimal == thousands:
        raise InvalidInputError(
            f"`thousands` cannot be {thousands!r} when `decimal` is "
            f"{decimal!r}: the same character would separate the thousands "
            f"and the decimals.",
            field = "thousands",
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


def sample_holds_file(path: str | Path) -> bool:
    """
    Tell whether the sample of `read_sample` holds the whole file: one whose
    content, decompressed when its extension says it is compressed, is at
    most `SAMPLE_BYTES` bytes long.

    Parameters
    ----------
    path : str, Path
        Path of the file.

    Returns
    -------
    holds : bool
        True when every line of the file is in the sample; False also when
        the file cannot be opened or decompressed here.
    """

    path = Path(str(path))
    opener = _OPENERS.get(path.suffix.lower())
    try:
        if opener is None:
            return path.stat().st_size <= SAMPLE_BYTES
        with opener(path, "rb") as handle:
            return len(handle.read(SAMPLE_BYTES + 1)) <= SAMPLE_BYTES
    except (OSError, *DECOMPRESSION_ERRORS):
        return False


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


def _without_column(rows: list[list[str]], name: str) -> list[list[str]]:
    """
    Return the records of a sample without the fields of the column named
    `name` in its header.
    """
    skip = {position for position, field in enumerate(rows[0]) if field == name}
    if not skip:
        return rows
    return [
        [field for position, field in enumerate(row) if position not in skip]
        for row in rows
    ]


def _dotted_value(values: list[str]) -> str | None:
    """
    Return the first value with a `'.'` that `pandas.read_csv` would read as
    a number without it when `'.'` separates the thousands ('15.01.2020',
    '0.5'), or None when there is none.
    """
    for value in values:
        if (
            "." in value
            and DOTTED_NUMBER.fullmatch(value)
            and not DOT_THOUSANDS.fullmatch(value)
        ):
            return value
    return None


def _mixed_column(rows: list[list[str]]) -> str | None:
    """
    Return a number that reads as thousands ('1.020') from a column that
    also holds whole numbers of at most three digits ('870') and no larger
    one, as a file that separates thousands writes them, or None.
    """
    for column in range(max(len(row) for row in rows)):
        cells = [row[column].strip() for row in rows[1:] if column < len(row)]
        found = next((cell for cell in cells if DOT_THOUSANDS.fullmatch(cell)), None)
        if found is None:
            continue
        wholes = [cell for cell in cells if WHOLE_NUMBER.fullmatch(cell)]
        if wholes and all(SHORT_WHOLE_NUMBER.fullmatch(cell) for cell in wholes):
            return found
    return None


def _number_marks(
    rows: list[list[str]],
    source: str,
    field: str,
    sep: str,
    decimal: str | None,
    thousands: str | None,
) -> tuple[str, str | None]:
    """
    Tell the decimal mark and the thousands separator from the records of a
    sample read with a separator other than `','`, keeping those given by
    the caller (see `detect_csv_dialect`).
    """
    values = [value.strip() for row in rows[1:] for value in row]
    if thousands is not None:
        other = _dotted_value(values)
        if other is not None:
            raise dotted_values_error(source, field, other)
        return ",", thousands

    # First number of each kind: with '.' between thousands ('1.705',
    # '1.234.567', '1.705,11'), of those, one that cannot read with '.' as
    # decimal mark ('1.234.567', '1.705,11'), with ',' ('2,5', '1,234'),
    # with '.' as decimal mark ('0.5', '1.705') and with '.' as decimal mark
    # only ('0.5').
    first = {}
    only_thousands = True
    for value in values:
        with_point = DECIMAL_NUMBERS["."].fullmatch(value)
        if DOT_THOUSANDS.fullmatch(value):
            first.setdefault("grouped", value)
            if not with_point:
                first.setdefault("sure", value)
        elif DECIMAL_NUMBERS[","].fullmatch(value):
            first.setdefault("comma", value)
            if not THOUSANDS.fullmatch(value):
                only_thousands = False
        elif with_point:
            first.setdefault("decimals", value)
        if with_point:
            first.setdefault("point", value)
    grouped, comma = first.get("grouped"), first.get("comma")

    if decimal == ",":
        # Given: '1.705' only reads as a number with '.' between thousands.
        if grouped is None:
            return decimal, None
        other = _dotted_value(values)
        if other is not None:
            raise dotted_values_error(source, field, other, grouped)
        return decimal, "."

    if comma is not None and "decimals" in first:
        raise decimal_in_both_error(source, field, comma, first["point"])
    if grouped is not None:
        # With ';' a ',' is the decimal mark; with a tabulator, only when a
        # number with a ',' does not also read as thousands.
        comma_decimal = comma is not None and (sep == ";" or not only_thousands)
        evidence = (
            first.get("sure")
            or _mixed_column(rows)
            or (grouped if comma_decimal else None)
        )
        if evidence is not None:
            other = _dotted_value(values)
            if other is not None:
                raise dotted_values_error(source, field, other, evidence)
            return ",", "."
    if comma is not None and "point" in first:
        raise decimal_in_both_error(source, field, comma, first["point"])
    if comma is not None and only_thousands and sep == "\t":
        raise only_thousands_error(source, field, comma)
    if comma is not None:
        return ",", None
    if grouped is not None and "decimals" not in first:
        # No number with '.' as decimal mark only ('0.5') settles it.
        raise ambiguous_thousands_error(source, field, grouped)

    return DEFAULT_CSV_DECIMAL, None


def detect_csv_dialect(
    sample: str,
    source: str,
    field: str = "data",
    sep: str | None = None,
    decimal: str | None = None,
    thousands: str | None = None,
    series_id_column: str | None = None,
) -> tuple[str, str, str | None]:
    """
    Tell the separator, the decimal mark and the thousands separator of a
    CSV file from its start.

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

    With a separator other than `','`, `'.'` separates the thousands (and
    `','` is the decimal mark) when a number cannot read otherwise
    (`'1.234.567'`, `'1.705,11'`), when a column holds whole numbers of at
    most three digits next to numbers that read as thousands (`'870'` and
    `'1.020'`), and when a number reads as thousands in a file whose decimal
    mark is `','`. A decimal mark `','` given by the caller reads every
    number such as `'1.705'` as thousands.

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
        Decimal mark given by the caller, which is then not detected. With
        `'.'`, the file has no thousands separator.
    thousands : str, default None
        Thousands separator given by the caller, which is then not
        detected. With `'.'`, the decimal mark is `','`.
    series_id_column : str, default None
        Column of the series ids of long-format data. It is read as text,
        so its values (`'1.020'`, `'0.5'`) neither tell the decimal mark
        and the thousands separator nor stop them.

    Returns
    -------
    sep : str
        Separator of the fields.
    decimal : str
        Decimal mark.
    thousands : str, None
        Thousands separator: `'.'`, or None when the numbers have none.

    Notes
    -----
    A file that reads with more than one separator, that holds numbers
    written with both decimal marks, or that is separated by tabulators and
    whose only numbers with a `','` also read as thousands, raises `InvalidInputError` with code
    `'data_unreadable'` and a hint that says how to give them: the dialect
    is never guessed. So does a file whose only numbers with a `'.'` read
    both as thousands and as numbers with three decimals (`'1.705'`), unless
    another number has decimals after a `'.'` (`'0.5'`), and a file with
    `'.'` as thousands separator that holds other values with a `'.'`
    (`'15.01.2020'`, `'0.5'`), which pandas would read as numbers without
    it.
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

    if sep == DEFAULT_CSV_SEP or (decimal == "." and thousands is None):
        # A comma file keeps '.' as decimal mark and has no thousands
        # separator; one given is reported by `check_csv_dialect`.
        decimal = DEFAULT_CSV_DECIMAL if decimal is None else decimal
    else:
        rows = records.get(sep) or _records(sample, sep) or []
        if series_id_column is not None and rows:
            rows = _without_column(rows, series_id_column)
        decimal, thousands = _number_marks(
                                 rows      = rows,
                                 source    = source,
                                 field     = field,
                                 sep       = sep,
                                 decimal   = decimal,
                                 thousands = thousands,
                             )

    return sep, decimal, thousands
