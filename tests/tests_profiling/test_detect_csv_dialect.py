# Unit test detect_csv_dialect

import re

import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.csv_dialect import (
    DIALECT_HINT,
    DOTTED_VALUES_HINT,
    EXOG_DIALECT_HINT,
    THOUSANDS_HINT,
    detect_csv_dialect,
)


@pytest.mark.parametrize(
    "sample, expected",
    [
        ("date,y\n2020-01-01,1.5\n2020-01-02,2.5\n", (",", ".", None)),
        ("date;y\n2020-01-01;1.5\n2020-01-02;2.5\n", (";", ".", None)),
        ("date;y\n2020-01-01;1,5\n2020-01-02;2,5\n", (";", ",", None)),
        ("date\ty\n2020-01-01\t1.5\n2020-01-02\t2.5\n", ("\t", ".", None)),
        ("date\ty\n2020-01-01\t1,5\n2020-01-02\t2,5\n", ("\t", ",", None)),
        ("date;y\n2020-01-01;1,5e3\n2020-01-02;-2,5\n", (";", ",", None)),
        ("date;y\n2020-01-01;1\n2020-01-02;2\n", (";", ".", None)),
        ("date,y\r\n2020-01-01,1.5\r\n", (",", ".", None)),
        ("", (",", ".", None)),
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
        ('date;note\n2020-01-01;"a,b"\n2020-01-02;"c,d"\n', (";", ".", None)),
        ('date,note\n2020-01-01,"a;b"\n2020-01-02,"c;d"\n', (",", ".", None)),
        ('date\tnote\n2020-01-01\t"a;b,c"\n', ("\t", ".", None)),
        # Quoted numbers with a decimal comma are read as numbers.
        ('date;y\n2020-01-01;"1,5"\n2020-01-02;"2,5"\n', (";", ",", None)),
        # A comma only inside the quotes of a field is not a decimal mark.
        ('date;y;note\n2020-01-01;1.5;"a,b"\n', (";", ".", None)),
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
        ("y,z\n2020-01-01,1,2\n2020-01-02,3,4\n", (",", ".", None)),
        ("y;z\n2020-01-01;1;2\n2020-01-02;3;4\n", (";", ".", None)),
        ("y;z\n2020-01-01;1,5;2,5\n", (";", ",", None)),
        # Rows of different lengths: the only separator in the header.
        ("a;b;c\n1;2\n3;4;5\n", (";", ".", None)),
        ("a,b,c\n1,2\n3,4,5\n", (",", ".", None)),
        # A single column holds no separator in the header.
        ("y\n1\n2\n3\n", (",", ".", None)),
        ("y\n1,5\n2,5\n", (",", ".", None)),
        ("y\n1;5\n2;5\n", (",", ".", None)),
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
        (";", None, (";", ",", None)),
        (";", ".", (";", ".", None)),
        (";", ",", (";", ",", None)),
        (",", None, (",", ".", None)),
        (",", ".", (",", ".", None)),
        ("\t", ",", ("\t", ",", None)),
        (None, ",", (";", ",", None)),
        (None, ".", (";", ".", None)),
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

    assert detect_csv_dialect(sample, "data.csv", sep=";") == (";", ",", None)
    assert detect_csv_dialect(sample, "data.csv", sep=",") == (",", ".", None)


def test_detect_csv_dialect_decimal_is_never_comma_when_sep_is_comma():
    """
    Test that a comma file keeps '.' as decimal mark even when its numbers
    are quoted with a comma.
    """
    sample = 'date,y\n2020-01-01,"1,5"\n2020-01-02,"2,5"\n'

    assert detect_csv_dialect(sample, "data.csv") == (",", ".", None)
    assert detect_csv_dialect(sample, "data.csv", sep=",") == (",", ".", None)


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

    assert detect_csv_dialect(sample, "my.csv", decimal=",") == (";", ",", None)
    assert detect_csv_dialect(sample, "my.csv", decimal=".") == (";", ".", None)


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

    assert detect_csv_dialect(sample, "my.csv") == (";", ",", None)


@pytest.mark.parametrize("value", ["0,958", "1,0", "12,5", "1,2345"])
def test_detect_csv_dialect_decimal_comma_when_one_value_is_not_thousands(value):
    """
    Test that one value that does not read as thousands ('0,958', '1,0',
    '12,5') settles the decimal mark as ',' next to values that do.
    """
    sample = f"date;y\n2020-01-01;1,841\n2020-01-02;{value}\n"

    assert detect_csv_dialect(sample, "my.csv") == (";", ",", None)


def test_detect_csv_dialect_decimal_given_skips_the_thousands_ambiguity():
    """
    Test that a decimal mark given by the caller is kept for a file whose
    numbers with a ',' read as thousands.
    """
    sample = "date;y\n2020-01-01;1,841\n2020-01-02;2,235\n"

    assert detect_csv_dialect(sample, "my.csv", decimal=",") == (";", ",", None)
    assert detect_csv_dialect(sample, "my.csv", sep=",") == (",", ".", None)


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


@pytest.mark.parametrize(
    "sample, expected",
    [
        (
            "date;y\n2015-01-01;870\n2015-02-01;1.020\n2015-03-01;2.015\n",
            (";", ",", "."),
        ),
        (
            "date\ty\n2015-01-01\t870\n2015-02-01\t1.020\n2015-03-01\t2.015\n",
            ("\t", ",", "."),
        ),
        ("date;y\n2015-01-01;-870\n2015-02-01;-1.020\n", (";", ",", ".")),
        (
            "date;y;z\n2015-01-01;870;5\n2015-02-01;1.020;12\n",
            (";", ",", "."),
        ),
        ("date;y\n2015-01-01;1.705,11\n2015-02-01;870,5\n", (";", ",", ".")),
        ("date;y\n2015-01-01;1.705,11\n2015-02-01;1.870,25\n", (";", ",", ".")),
        ("date\ty\n2015-01-01\t1.705,11\n", ("\t", ",", ".")),
        ("date;y\n2015-01-01;1.234.567\n2015-02-01;2.345.678\n", (";", ",", ".")),
        ("date;y;z\n2015-01-01;1.705;2,5\n2015-02-01;1.870;3,5\n", (";", ",", ".")),
        ("date;y;z\n2015-01-01;1.705;1,841\n", (";", ",", ".")),
    ],
    ids=[
        "semicolon whole numbers with and without separator",
        "tab whole numbers with and without separator",
        "negative numbers",
        "a column of thousands next to one of whole numbers",
        "thousands with decimal comma next to decimal comma",
        "every value with thousands and decimal comma",
        "tab thousands with decimal comma",
        "several groups of thousands",
        "thousands next to decimal comma in another column",
        "thousands next to three decimals after a comma with semicolon",
    ],
)
def test_detect_csv_dialect_output_when_point_separates_thousands(sample, expected):
    """
    Test that '.' is the thousands separator, with ',' as decimal mark, when
    the file says so: a column with whole numbers of at most three digits
    next to numbers such as '1.020', a number that cannot read with '.' as
    decimal mark ('1.705,11', '1.234.567'), or ',' as decimal mark in the
    same file.
    """
    assert detect_csv_dialect(sample, "data.csv") == expected


@pytest.mark.parametrize(
    "sample",
    [
        "date;y;x\n2015-01-01;12.345;0.5\n2015-02-01;13.456;1.5\n",
        "date;y\n2015-01-01;12.345\n2015-02-01;13.45\n",
        "date;y\n2015-01-01;1.020\n2015-02-01;0.125\n",
        "date\ty\n2015-01-01\t1.020\n2015-02-01\t1020.5\n",
    ],
    ids=[
        "next to another column with decimals",
        "next to a value with two decimals",
        "next to a value below one",
        "tab next to a value of four digits before the point",
    ],
)
def test_detect_csv_dialect_three_decimals_when_another_number_has_point_decimals(
    sample,
):
    """
    Test that a number with three decimals ('12.345') next to a number that
    only reads with '.' as decimal mark ('0.5', '13.45') is not taken for
    thousands: the decimal mark is '.' and the file has no thousands
    separator.
    """
    assert detect_csv_dialect(sample, "data.csv")[1:] == (".", None)


@pytest.mark.parametrize(
    "sample, example",
    [
        ("date;y\n2015-01-01;1.870\n2015-02-01;1.020\n", "1.870"),
        ("date\ty\n2015-01-01\t1.870\n2015-02-01\t1.020\n", "1.870"),
        ("date;y\n2015-01-01;1500\n2015-02-01;1.020\n", "1.020"),
        ("date;y;n\n2015-01-01;1.870;5\n2015-02-01;1.020;7\n", "1.870"),
    ],
    ids=[
        "every value with thousands",
        "tab every value with thousands",
        "next to a whole number of four digits",
        "whole numbers only in another column",
    ],
)
@pytest.mark.parametrize(
    "field, hint",
    [("data", THOUSANDS_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_detect_csv_dialect_InvalidInputError_when_thousands_are_ambiguous(
    sample, example, field, hint
):
    """
    Test that a file whose only numbers with a '.' read both as thousands
    and as numbers with three decimals raises an InvalidInputError with the
    code 'data_unreadable', an example, the argument that named the file and
    its hint. Whole numbers in another column, or larger than three digits,
    do not settle it.
    """
    err_msg = re.escape(
        f"The thousands separator of the CSV file 'my.csv' cannot be told: its "
        f"numbers with a '.' (such as '{example}') read both as thousands and "
        f"as numbers with three decimals."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        detect_csv_dialect(sample, "my.csv", field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


@pytest.mark.parametrize(
    "decimal, thousands, expected",
    [
        (",", None, (";", ",", ".")),
        (None, ".", (";", ",", ".")),
        (",", ".", (";", ",", ".")),
        (".", None, (";", ".", None)),
    ],
    ids=["decimal comma", "thousands", "both", "decimal point"],
)
def test_detect_csv_dialect_output_when_decimal_or_thousands_given(
    decimal, thousands, expected
):
    """
    Test that a file whose thousands are ambiguous is read once the caller
    says what its '.' is: a decimal mark ',' or a thousands separator '.'
    read '1.870' as thousands, and a decimal mark '.' as three decimals.
    """
    sample = "date;y\n2015-01-01;1.870\n2015-02-01;1.020\n"

    result = detect_csv_dialect(
                 sample, "my.csv", decimal=decimal, thousands=thousands
             )

    assert result == expected


def test_detect_csv_dialect_output_when_decimal_comma_given_without_thousands():
    """
    Test that a decimal mark ',' given by the caller keeps the file without
    thousands separator when no number reads as thousands.
    """
    sample = "date;y\n2015-01-01;1,5\n2015-02-01;2,5\n"

    assert detect_csv_dialect(sample, "my.csv", decimal=",") == (";", ",", None)


def test_detect_csv_dialect_thousands_never_when_sep_is_comma():
    """
    Test that a comma file keeps '.' as decimal mark, without thousands
    separator, even when its numbers read as thousands.
    """
    sample = "date,y\n2015-01-01,870\n2015-02-01,1.020\n2015-03-01,1.870\n"

    assert detect_csv_dialect(sample, "data.csv") == (",", ".", None)


@pytest.mark.parametrize(
    "sample, with_thousands, other",
    [
        (
            "date;y;end\n2020-01-15;1.705,11;15.01.2020\n"
            "2020-01-16;870,5;16.01.2020\n",
            "1.705,11",
            "15.01.2020",
        ),
        (
            "date;y;x\n2015-01-01;870;0.5\n2015-02-01;1.020;1.5\n",
            "1.020",
            "0.5",
        ),
        (
            "date;y;v\n2015-01-01;1.234.567;1.2.3\n",
            "1.234.567",
            "1.2.3",
        ),
    ],
    ids=[
        "dates with points in another column",
        "decimals with point",
        "version numbers",
    ],
)
@pytest.mark.parametrize(
    "field, hint",
    [("data", DOTTED_VALUES_HINT), ("exog", EXOG_DIALECT_HINT)],
)
def test_detect_csv_dialect_InvalidInputError_when_thousands_and_other_points(
    sample, with_thousands, other, field, hint
):
    """
    Test that a file whose '.' separates thousands and that holds other
    values made of digits and points ('15.01.2020' in a column that is not
    the one of the dates, '0.5'), which pandas reads as numbers without
    them, raises an InvalidInputError with the code 'data_unreadable', an
    example of each, the argument that named the file and its hint.
    """
    err_msg = re.escape(
        f"The CSV file 'my.csv' cannot be read: it holds numbers with '.' "
        f"between the thousands (such as '{with_thousands}') and values with a "
        f"'.' that does not separate thousands (such as '{other}'), which "
        f"pandas would read as numbers without it."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        detect_csv_dialect(sample, "my.csv", field=field)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


@pytest.mark.parametrize(
    "decimal",
    [None, ","],
    ids=lambda dt: f"decimal: {dt}",
)
def test_detect_csv_dialect_InvalidInputError_when_thousands_given_and_other_points(
    decimal,
):
    """
    Test that a thousands separator '.' given by the caller is checked
    against the values made of digits and points: '0.5' would be read as 5.
    """
    sample = "date;y;x\n2015-01-01;1.705;0.5\n"

    err_msg = re.escape(
        "The CSV file 'my.csv' cannot be read with '.' as thousands "
        "separator: it holds values with a '.' that does not separate "
        "thousands (such as '0.5'), which pandas would read as numbers "
        "without it."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        detect_csv_dialect(sample, "my.csv", decimal=decimal, thousands=".")

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.hint == DOTTED_VALUES_HINT


def test_detect_csv_dialect_InvalidInputError_when_decimal_given_and_other_points():
    """
    Test that a decimal mark ',' given by the caller reads '1.705' as
    thousands only when no other value made of digits and points would be
    read without them.
    """
    sample = "date;y;x\n15.01.2020;1.705;0.5\n16.01.2020;1.870;1.5\n"

    err_msg = re.escape(
        "(such as '1.705') and values with a '.' that does not separate "
        "thousands (such as '0.5')"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        detect_csv_dialect(sample, "my.csv", decimal=",")


def test_detect_csv_dialect_decimal_in_both_when_tab_thousands_and_point_thousands():
    """
    Test that a file separated by tabulators with numbers such as '1,841'
    and '1.705', each of which reads as thousands, keeps raising the error
    of the decimal mark instead of choosing one.
    """
    sample = "date\ty\tz\n2015-01-01\t1.705\t1,841\n"

    err_msg = re.escape(
        "The decimal mark of the CSV file 'my.csv' cannot be told: it holds "
        "numbers written with ',' (such as '1,841') and with '.' (such as "
        "'1.705')."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$"):
        detect_csv_dialect(sample, "my.csv")


# Samples of long-format data whose ids ('1.2.3', '1.001', '1,5') look like
# numbers, and what they give without and with `series_id_column`: the ids
# are read as text, so they must not tell the dialect nor stop it.
@pytest.mark.parametrize(
    "sample, expected",
    [
        # ids '1.2.3' are not thousands, and y mixes '870' and '1.020'.
        (
            "store;date;y\n1.2.3;2015-01-01;870\n1.2.3;2015-02-01;1.020\n"
            "1.2.3;2015-03-01;2.015\n",
            (";", ",", "."),
        ),
        # ids '0.5' are not thousands.
        (
            "store;date;y\n0.5;2015-01-01;870\n0.5;2015-02-01;1.020\n",
            (";", ",", "."),
        ),
        # ids '1.001' would make the whole y values ambiguous thousands.
        (
            "store;date;y\n1.001;2015-01-01;870\n1.002;2015-02-01;945\n",
            (";", ".", None),
        ),
        (
            "store;date;y\n1.870;2015-01-01;12\n1.870;2015-02-01;13\n",
            (";", ".", None),
        ),
        # ids '1,5' would give a decimal comma next to the decimal point of y.
        (
            "store;date;y\n1,5;2015-01-01;1.5\n1,5;2015-02-01;2.5\n",
            (";", ".", None),
        ),
        (
            "store;date;y\n1,5;2015-01-01;12\n1,5;2015-02-01;13\n",
            (";", ".", None),
        ),
        (
            "date;store;y\n2015-01-01;1,5;2.5\n2015-02-01;1,5;3.5\n",
            (";", ".", None),
        ),
        # ids '1.001' would make y with decimal comma numbers with thousands.
        (
            "store;date;y\n1.001;2015-01-01;1,5\n1.002;2015-02-01;2,5\n",
            (";", ",", None),
        ),
        # Quoted ids with a comma.
        (
            'store;date;y\n"1,5";2015-01-01;2.5\n"1,5";2015-02-01;3.5\n',
            (";", ".", None),
        ),
        # A tab separated file.
        (
            "store\tdate\ty\n1,841\t2015-01-01\t1.5\n1,841\t2015-02-01\t2.5\n",
            ("\t", ".", None),
        ),
    ],
    ids=[
        "dotted ids and thousands in y",
        "ids below one and thousands in y",
        "ids with three decimals and whole y",
        "ids with three digits after the point and whole y",
        "ids with decimal comma and y with decimal point",
        "ids with decimal comma and whole y",
        "ids in the second column",
        "ids with thousands and y with decimal comma",
        "quoted ids with a comma",
        "tab and ids with thousands",
    ],
)
def test_detect_csv_dialect_output_when_series_id_column_given(sample, expected):
    """
    Test that the values of the column of series ids, which are read as text,
    neither tell the decimal mark and the thousands separator nor stop them:
    only the other columns decide the dialect.
    """
    result = detect_csv_dialect(sample, "data.csv", series_id_column="store")

    assert result == expected


@pytest.mark.parametrize(
    "sample, expected",
    [
        (
            "store;date;y\n1.001;2015-01-01;1,5\n1.002;2015-02-01;2,5\n",
            (";", ",", "."),
        ),
        (
            "store;date;y\n1,5;2015-01-01;12\n1,5;2015-02-01;13\n",
            (";", ",", None),
        ),
    ],
    ids=["ids taken for thousands", "ids taken for a decimal comma"],
)
def test_detect_csv_dialect_series_ids_decide_the_dialect_without_series_id_column(
    sample, expected
):
    """
    Test that, without `series_id_column`, the same samples give another
    dialect: the ids are read as numbers (thousands in '1.001', a decimal
    comma in '1,5').
    """
    assert detect_csv_dialect(sample, "data.csv") == expected


@pytest.mark.parametrize(
    "sample, message, expected",
    [
        (
            "store;date;y\n1.2.3;2015-01-01;870\n1.2.3;2015-02-01;1.020\n"
            "1.2.3;2015-03-01;2.015\n",
            "The CSV file 'data.csv' cannot be read: it holds numbers with '.' "
            "between the thousands (such as '1.020') and values with a '.' "
            "that does not separate thousands (such as '1.2.3'), which pandas "
            "would read as numbers without it.",
            (";", ",", "."),
        ),
        (
            "store;date;y\n1.001;2015-01-01;870\n1.002;2015-02-01;945\n",
            "The thousands separator of the CSV file 'data.csv' cannot be "
            "told: its numbers with a '.' (such as '1.001') read both as "
            "thousands and as numbers with three decimals.",
            (";", ".", None),
        ),
        (
            "store;date;y\n1,5;2015-01-01;1.5\n1,5;2015-02-01;2.5\n",
            "The decimal mark of the CSV file 'data.csv' cannot be told: it "
            "holds numbers written with ',' (such as '1,5') and with '.' "
            "(such as '1.5').",
            (";", ".", None),
        ),
    ],
    ids=["dotted values", "ambiguous thousands", "decimal in both"],
)
def test_detect_csv_dialect_InvalidInputError_when_series_ids_stop_the_dialect(
    sample, message, expected
):
    """
    Test that, without `series_id_column`, ids such as '1.2.3', '1.001' or
    '1,5' make the dialect impossible to tell, which the same samples are
    with the column given.
    """
    with pytest.raises(InvalidInputError, match=re.escape(message) + "$"):
        detect_csv_dialect(sample, "data.csv")

    result = detect_csv_dialect(sample, "data.csv", series_id_column="store")

    assert result == expected


@pytest.mark.parametrize(
    "series_id_column",
    ["other", "date", "STORE"],
    ids=lambda dt: f"series_id_column: {dt}",
)
def test_detect_csv_dialect_InvalidInputError_when_series_id_column_is_not_the_ids(
    series_id_column,
):
    """
    Test that the column is matched by its name in the header: another
    column, a name that is not in the header or a case that differs leaves
    the ids of the sample to stop the dialect, as without the argument.
    """
    sample = "store;date;y\n1,5;2015-01-01;2.5\n1,5;2015-02-01;3.5\n"

    err_msg = re.escape(
        "The decimal mark of the CSV file 'data.csv' cannot be told: it holds "
        "numbers written with ',' (such as '1,5') and with '.' (such as "
        "'2.5')."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$"):
        detect_csv_dialect(sample, "data.csv", series_id_column=series_id_column)


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"thousands": "."}, (";", ",", ".")),
        ({"decimal": ","}, (";", ",", ".")),
    ],
    ids=["thousands given", "decimal comma given"],
)
def test_detect_csv_dialect_output_when_series_id_column_and_dialect_given(
    kwargs, expected
):
    """
    Test that an id below one ('0.5') does not stop a thousands separator or a
    decimal mark ',' given by the caller, which read '1.705' as thousands
    when the ids are left out and raise when they are not.
    """
    sample = "store;date;y\n0.5;2015-01-01;1.705\n0.5;2015-02-01;1.870\n"

    err_msg = re.escape("(such as '0.5')")
    with pytest.raises(InvalidInputError, match=err_msg):
        detect_csv_dialect(sample, "data.csv", **kwargs)

    result = detect_csv_dialect(
                 sample, "data.csv", series_id_column="store", **kwargs
             )

    assert result == expected


@pytest.mark.parametrize(
    "sample, expected",
    [
        (
            "datum;umsatz\n15.01.2020;1.234,56\n16.01.2020;2.345,67\n",
            (";", ",", "."),
        ),
        (
            "datum\tumsatz\n15.01.2020\t1.234,56\n16.01.2020\t2.345,67\n",
            ("\t", ",", "."),
        ),
        (
            "datum;umsatz\n2020.01.15;1.234,56\n2020.01.16;2.345,67\n",
            (";", ",", "."),
        ),
        (
            "datum;umsatz\n15.01.2020 10:00;1.234,56\n16.01.2020 11:30;2.345,67\n",
            (";", ",", "."),
        ),
        (
            "name;datum;umsatz\na;15.01.2020;1.234,56\nb;16.01.2020;2.345,67\n",
            (";", ",", "."),
        ),
        (
            "datum;umsatz\n15.01.2020;870\n16.01.2020;1.020\n",
            (";", ",", "."),
        ),
        (
            "datum;umsatz\n15.01.2020;870,5\n16.01.2020;945,25\n",
            (";", ",", None),
        ),
        (
            "datum,umsatz\n15.01.2020,1.5\n16.01.2020,2.5\n",
            (",", ".", None),
        ),
    ],
    ids=[
        "german spreadsheet",
        "tabulator",
        "year first with points",
        "with time",
        "after a column of text",
        "whole numbers",
        "decimal comma without thousands",
        "comma file",
    ],
)
def test_detect_csv_dialect_output_when_dates_with_points_in_the_date_column(
    sample, expected
):
    """
    Test that the dates written with points ('15.01.2020') of the column of
    the dates of the sample are not numbers, so they neither tell the decimal
    mark and the thousands separator nor stop them: a German spreadsheet is
    read with ';', ',' and '.' instead of raising 'data_unreadable'.
    """
    assert detect_csv_dialect(sample, "my.csv") == expected


def test_detect_csv_dialect_output_when_date_column_given():
    """
    Test that the `date_column` given is left out of the numbers when its
    dates are not written in a way that finds them in the sample (two digits
    for the year, '15.01.20'), as the caller said where they are.
    """
    sample = "datum;umsatz\n15.01.20;1.234,56\n16.01.20;2.345,67\n"

    result = detect_csv_dialect(sample, "my.csv", date_column="datum")

    assert result == (";", ",", ".")


@pytest.mark.parametrize(
    "sample, date_column, other",
    [
        ("datum;umsatz\n15.01.20;1.234,56\n16.01.20;2.345,67\n", None, "15.01.20"),
        (
            "datum;end;umsatz\n15.01.2020;16.01.2020;1.234,56\n",
            "end",
            "15.01.2020",
        ),
    ],
    ids=["dates not found in the sample", "other column than the one given"],
)
def test_detect_csv_dialect_InvalidInputError_when_dates_with_points_not_in_date_column(
    sample, date_column, other
):
    """
    Test that dates with points that are not in the column of the dates (the
    sample finds none, or the caller names another column) still raise an
    InvalidInputError with the code 'data_unreadable', an example of each
    kind of value and the hint of the values: only the column of the dates
    is read as text.
    """
    err_msg = re.escape(
        f"The CSV file 'my.csv' cannot be read: it holds numbers with '.' "
        f"between the thousands (such as '1.234,56') and values with a '.' "
        f"that does not separate thousands (such as '{other}'), which pandas "
        f"would read as numbers without it."
    )
    with pytest.raises(InvalidInputError, match=err_msg + "$") as exc_info:
        detect_csv_dialect(sample, "my.csv", date_column=date_column)

    assert exc_info.value.code == "data_unreadable"
    assert exc_info.value.hint == DOTTED_VALUES_HINT


@pytest.mark.parametrize(
    "sample, expected",
    [
        (
            "store;datum;umsatz\n1.020;15.01.2020;1,5\n2.030;16.01.2020;2,5\n",
            (";", ",", None),
        ),
        (
            "store;datum;umsatz\n1.020;15.01.2020;1.234,5\n2.030;16.01.2020;2,5\n",
            (";", ",", "."),
        ),
    ],
    ids=["ids with points", "ids with points and thousands"],
)
def test_detect_csv_dialect_output_when_series_ids_and_dates_with_points(
    sample, expected
):
    """
    Test that the column of the series ids ('1.020') and the column of the
    dates ('15.01.2020') are both left out of the numbers, so only the
    amounts tell how the file is written.
    """
    result = detect_csv_dialect(sample, "my.csv", series_id_column="store")

    assert result == expected
