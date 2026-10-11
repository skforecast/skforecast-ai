# Unit test detect_csv_dialect

import re

import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.csv_dialect import (
    DIALECT_HINT,
    EXOG_DIALECT_HINT,
    detect_csv_dialect,
)


@pytest.mark.parametrize(
    "sample, expected",
    [
        ("date,y\n2020-01-01,1.5\n2020-01-02,2.5\n", (",", ".")),
        ("date;y\n2020-01-01;1.5\n2020-01-02;2.5\n", (";", ".")),
        ("date;y\n2020-01-01;1,5\n2020-01-02;2,5\n", (";", ",")),
        ("date\ty\n2020-01-01\t1.5\n2020-01-02\t2.5\n", ("\t", ".")),
        ("date\ty\n2020-01-01\t1,5\n2020-01-02\t2,5\n", ("\t", ",")),
        ("date;y\n2020-01-01;1,5e3\n2020-01-02;-2,5\n", (";", ",")),
        ("date;y\n2020-01-01;1\n2020-01-02;2\n", (";", ".")),
        ("date,y\r\n2020-01-01,1.5\r\n", (",", ".")),
        ("", (",", ".")),
    ],
    ids=[
        "comma dot",
        "semicolon dot",
        "semicolon comma",
        "tab dot",
        "tab comma",
        "semicolon comma with exponent and sign",
        "semicolon integers",
        "comma with carriage returns",
        "empty sample",
    ],
)
def test_detect_csv_dialect_output(sample, expected):
    """
    Test that the separator is the one that splits the header and every
    record in the same number of fields, and the decimal mark is ',' only
    for numbers written as '1,5'.
    """
    assert detect_csv_dialect(sample, "data.csv") == expected


@pytest.mark.parametrize(
    "sample, expected",
    [
        # The quoted field holds a comma and a semicolon.
        ('date;note\n2020-01-01;"a,b"\n2020-01-02;"c,d"\n', (";", ".")),
        ('date,note\n2020-01-01,"a;b"\n2020-01-02,"c;d"\n', (",", ".")),
        ('date\tnote\n2020-01-01\t"a;b,c"\n', ("\t", ".")),
        # Quoted numbers with a decimal comma are read as numbers.
        ('date;y\n2020-01-01;"1,5"\n2020-01-02;"2,5"\n', (";", ",")),
        # A comma only inside the quotes of a field is not a decimal mark.
        ('date;y;note\n2020-01-01;1.5;"a,b"\n', (";", ".")),
    ],
    ids=[
        "semicolon with quoted comma",
        "comma with quoted semicolon",
        "tab with quoted semicolon and comma",
        "quoted decimal comma",
        "quoted text with a comma next to dot numbers",
    ],
)
def test_detect_csv_dialect_output_when_quoted_fields_hold_other_separators(
    sample, expected
):
    """
    Test that the quotes are read as pandas reads them: a separator inside a
    quoted field does not split it.
    """
    assert detect_csv_dialect(sample, "data.csv") == expected


@pytest.mark.parametrize(
    "sample, expected",
    [
        # Header one field short, as to_csv(index_label=False) writes it.
        ("y,z\n2020-01-01,1,2\n2020-01-02,3,4\n", (",", ".")),
        ("y;z\n2020-01-01;1;2\n2020-01-02;3;4\n", (";", ".")),
        ("y;z\n2020-01-01;1,5;2,5\n", (";", ",")),
        # Rows of different lengths: the only separator in the header.
        ("a;b;c\n1;2\n3;4;5\n", (";", ".")),
        ("a,b,c\n1,2\n3,4,5\n", (",", ".")),
        # A single column holds no separator in the header.
        ("y\n1\n2\n3\n", (",", ".")),
        ("y\n1,5\n2,5\n", (",", ".")),
        ("y\n1;5\n2;5\n", (",", ".")),
    ],
    ids=[
        "header one field short comma",
        "header one field short semicolon",
        "header one field short semicolon and decimal comma",
        "irregular rows semicolon",
        "irregular rows comma",
        "single column integers",
        "single column with commas",
        "single column with semicolons",
    ],
)
def test_detect_csv_dialect_output_when_rows_are_irregular(sample, expected):
    """
    Test that a header one field short, rows of different lengths and a
    single column are read as before: the only separator of the header, and
    ',' when the header holds none.
    """
    assert detect_csv_dialect(sample, "data.csv") == expected


@pytest.mark.parametrize(
    "sep, decimal, expected",
    [
        (";", None, (";", ",")),
        (";", ".", (";", ".")),
        (";", ",", (";", ",")),
        (",", None, (",", ".")),
        (",", ".", (",", ".")),
        ("\t", ",", ("\t", ",")),
        (None, ",", (";", ",")),
        (None, ".", (";", ".")),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_detect_csv_dialect_output_when_sep_or_decimal_given(sep, decimal, expected):
    """
    Test that a separator or a decimal mark given by the caller is kept, and
    the other one is detected.
    """
    sample = "date;y\n2020-01-01;1,5\n2020-01-02;2,5\n"

    result = detect_csv_dialect(sample, "data.csv", sep=sep, decimal=decimal)

    assert result == expected


def test_detect_csv_dialect_output_when_sep_given_resolves_ambiguity():
    """
    Test that a file whose separator is ambiguous is read once the separator
    is given.
    """
    sample = "a,b;c\n1,2;3\n"

    assert detect_csv_dialect(sample, "data.csv", sep=";") == (";", ",")
    assert detect_csv_dialect(sample, "data.csv", sep=",") == (",", ".")


def test_detect_csv_dialect_decimal_is_never_comma_when_sep_is_comma():
    """
    Test that a comma file keeps '.' as decimal mark even when its numbers
    are quoted with a comma.
    """
    sample = 'date,y\n2020-01-01,"1,5"\n2020-01-02,"2,5"\n'

    assert detect_csv_dialect(sample, "data.csv") == (",", ".")
    assert detect_csv_dialect(sample, "data.csv", sep=",") == (",", ".")


@pytest.mark.parametrize(
    "field, hint",
    [("data", DIALECT_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_detect_csv_dialect_InvalidInputError_when_separator_is_ambiguous(
    field, hint
):
    """
    Test that a header that reads with two separators, each in as many
    fields as every record, raises an InvalidInputError with the code
    'data_unreadable', the argument that named the file and the hint of the
    argument.
    """
    sample = "a,b;c\n1,2;3\n"

    err_msg = re.escape(
        "The separator of the CSV file 'my.csv' cannot be told: its header "
        "reads with ',' (2 columns) and ';' (2 columns)."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        detect_csv_dialect(sample, "my.csv", field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


def test_detect_csv_dialect_InvalidInputError_when_three_separators_are_regular():
    """
    Test that the message lists every separator that reads the file, with
    its number of columns.
    """
    sample = "a,b;c\td\n1,2;3\t4\n"

    err_msg = re.escape(
        "The separator of the CSV file 'my.csv' cannot be told: its header "
        "reads with ',' (2 columns) and ';' (2 columns) and a tabulator "
        "(2 columns)."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$"):
        detect_csv_dialect(sample, "my.csv")


@pytest.mark.parametrize(
    "field, hint",
    [("data", DIALECT_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_detect_csv_dialect_InvalidInputError_when_decimal_is_ambiguous(
    field, hint
):
    """
    Test that numbers written with ',' and with '.' in the same file raise
    an InvalidInputError with the code 'data_unreadable', an example of each
    mark, the argument that named the file and the hint of the argument.
    """
    sample = "date;y;z\n2020-01-01;1,5;2.5\n"

    err_msg = re.escape(
        "The decimal mark of the CSV file 'my.csv' cannot be told: it holds "
        "numbers written with ',' (such as '1,5') and with '.' (such as "
        "'2.5')."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        detect_csv_dialect(sample, "my.csv", field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


def test_detect_csv_dialect_decimal_given_skips_the_ambiguity():
    """
    Test that a decimal mark given by the caller is kept for a file with
    numbers written with both marks.
    """
    sample = "date;y;z\n2020-01-01;1,5;2.5\n"

    assert detect_csv_dialect(sample, "my.csv", decimal=",") == (";", ",")
    assert detect_csv_dialect(sample, "my.csv", decimal=".") == (";", ".")


@pytest.mark.parametrize(
    "field, hint",
    [("data", DIALECT_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_detect_csv_dialect_InvalidInputError_when_numbers_only_read_as_thousands(
    field, hint
):
    """
    Test that a file separated by tabulators whose numbers with a ',' all
    read as thousands ('1,234') and none is written with '.' raises an
    InvalidInputError with the code 'data_unreadable', an example, the
    argument that named the file and its hint.
    """
    sample = "date\ty\n2020-01-01\t1,841\n2020-01-02\t2,235\n"

    err_msg = re.escape(
        "The decimal mark of the CSV file 'my.csv' cannot be told: its "
        "numbers with a ',' (such as '1,841') read both as thousands and as "
        "numbers with three decimals."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        detect_csv_dialect(sample, "my.csv", field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


def test_detect_csv_dialect_decimal_comma_when_semicolon_and_only_thousands():
    """
    Test that in a file separated by ';' numbers with a ',' that all read as
    thousands too ('1,841') are numbers with three decimals: the decimal mark
    is ','.
    """
    sample = "date;y\n2020-01-01;1,841\n2020-01-02;2,235\n"

    assert detect_csv_dialect(sample, "my.csv") == (";", ",")


@pytest.mark.parametrize("value", ["0,958", "1,0", "12,5", "1,2345"])
def test_detect_csv_dialect_decimal_comma_when_one_value_is_not_thousands(value):
    """
    Test that one value that does not read as thousands ('0,958', '1,0',
    '12,5') settles the decimal mark as ',' next to values that do.
    """
    sample = f"date;y\n2020-01-01;1,841\n2020-01-02;{value}\n"

    assert detect_csv_dialect(sample, "my.csv") == (";", ",")


def test_detect_csv_dialect_decimal_given_skips_the_thousands_ambiguity():
    """
    Test that a decimal mark given by the caller is kept for a file whose
    numbers with a ',' read as thousands.
    """
    sample = "date;y\n2020-01-01;1,841\n2020-01-02;2,235\n"

    assert detect_csv_dialect(sample, "my.csv", decimal=",") == (";", ",")
    assert detect_csv_dialect(sample, "my.csv", sep=",") == (",", ".")


def test_detect_csv_dialect_cuts_the_examples_of_the_decimal_error_to_20_characters():
    """
    Test that the numbers quoted by the decimal error are cut to 20
    characters.
    """
    long_comma = "1," + "5" * 30
    long_dot = "2." + "5" * 30
    sample = f"date;y;z\n2020-01-01;{long_comma};{long_dot}\n"

    err_msg = re.escape(
        "it holds numbers written with ',' (such as '1,555555555555555555'"
        ") and with '.' (such as '2.555555555555555555')."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        detect_csv_dialect(sample, "my.csv")
