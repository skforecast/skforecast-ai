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
