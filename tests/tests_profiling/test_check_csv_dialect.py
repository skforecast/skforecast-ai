# Unit test check_csv_dialect

import re

import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.csv_dialect import check_csv_dialect


@pytest.mark.parametrize(
    "sep, decimal",
    [
        (None, None),
        (",", None),
        (";", None),
        ("\t", None),
        (None, "."),
        (None, ","),
        (",", "."),
        (";", ","),
        ("\t", ","),
        (";", "."),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_check_csv_dialect_output_when_valid(sep, decimal):
    """
    Test that every combination of a valid separator and decimal mark, or
    none, passes and returns None.
    """
    assert check_csv_dialect(sep, decimal) is None


@pytest.mark.parametrize(
    "sep, decimal, thousands",
    [
        (None, None, None),
        (";", ",", None),
        (";", ",", "."),
        ("\t", ",", "."),
        (";", None, "."),
        ("\t", None, "."),
        (None, ",", "."),
        (None, None, "."),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_check_csv_dialect_output_when_thousands_valid(sep, decimal, thousands):
    """
    Test that '.' as thousands separator passes with a separator other than
    ',' and with ',' as decimal mark, or when these are not given, and
    returns None.
    """
    assert check_csv_dialect(sep, decimal, thousands) is None


@pytest.mark.parametrize(
    "sep, decimal, message, field",
    [
        (
            "|",
            None,
            "`sep` must be ',', ';' or a tabulator ('\\t'), got '|'.",
            "sep",
        ),
        (
            "tab",
            ".",
            "`sep` must be ',', ';' or a tabulator ('\\t'), got 'tab'.",
            "sep",
        ),
        (
            ";",
            ";",
            "`decimal` must be '.' or ',', got ';'.",
            "decimal",
        ),
        (
            None,
            "x",
            "`decimal` must be '.' or ',', got 'x'.",
            "decimal",
        ),
        (
            ",",
            ",",
            "`decimal` cannot be ',' when `sep` is ',': the same character "
            "would separate the fields and the decimals.",
            "decimal",
        ),
    ],
    ids=["sep pipe", "sep tab word", "decimal semicolon", "decimal x", "same mark"],
)
def test_check_csv_dialect_InvalidInputError_when_not_valid(
    sep, decimal, message, field
):
    """
    Test that a separator or a decimal mark that is not accepted, and a
    decimal mark equal to the separator, raise an InvalidInputError (a
    ValueError) with the code 'invalid_argument' and the argument at fault.
    """
    with pytest.raises(InvalidInputError, match=re.escape(message)) as exc_info:
        check_csv_dialect(sep, decimal)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == field
    assert isinstance(exc_info.value, ValueError)


@pytest.mark.parametrize(
    "sep, decimal, thousands, message",
    [
        (
            ";",
            ",",
            ",",
            "`thousands` must be '.', got ','.",
        ),
        (
            None,
            None,
            " ",
            "`thousands` must be '.', got ' '.",
        ),
        (
            ",",
            None,
            ".",
            "`thousands` cannot be '.' when `sep` is ',': '.' separates the "
            "thousands where ',' is the decimal mark, which cannot also "
            "separate the fields.",
        ),
        (
            ",",
            ".",
            ".",
            "`thousands` cannot be '.' when `sep` is ',': '.' separates the "
            "thousands where ',' is the decimal mark, which cannot also "
            "separate the fields.",
        ),
        (
            ";",
            ".",
            ".",
            "`thousands` cannot be '.' when `decimal` is '.': the same "
            "character would separate the thousands and the decimals.",
        ),
        (
            None,
            ".",
            ".",
            "`thousands` cannot be '.' when `decimal` is '.': the same "
            "character would separate the thousands and the decimals.",
        ),
    ],
    ids=[
        "thousands comma",
        "thousands space",
        "sep comma",
        "sep comma and decimal point (sep message wins)",
        "decimal point with semicolon",
        "decimal point",
    ],
)
def test_check_csv_dialect_InvalidInputError_when_thousands_not_valid(
    sep, decimal, thousands, message
):
    """
    Test that a thousands separator other than '.', one given with ',' as
    separator, and one given with '.' as decimal mark raise an
    InvalidInputError (a ValueError) with the code 'invalid_argument' and the
    field 'thousands'. With ',' as separator and '.' as decimal mark, the
    message of the separator comes first.
    """
    err_msg = re.escape(message)
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        check_csv_dialect(sep, decimal, thousands)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "thousands"
    assert isinstance(exc_info.value, ValueError)
