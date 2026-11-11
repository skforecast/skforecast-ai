# Unit test sample_date_column

import pytest

from skforecast_ai.profiling.csv_dialect import sample_date_column


@pytest.mark.parametrize(
    "sample, sep, expected",
    [
        ("datum;umsatz\n15.01.2020;1.234,56\n16.01.2020;2.345,67\n", ";", "datum"),
        ("date,y\n2020-01-15,1\n2020-01-16,2\n", ",", "date"),
        ("date,y\n2020.01.15,1\n2020.01.16,2\n", ",", "date"),
        ("date\ty\n15/01/2020\t1\n16/01/2020\t2\n", "\t", "date"),
        ("date;y\n01-02-2020;1\n03-04-2020;2\n", ";", "date"),
        ("date;y\n15.01.2020 10:00;1\n16.01.2020 11:30:15;2\n", ";", "date"),
        ("date,y\n2020-01-15T10:30:00.123,1\n2020-01-16 11:00,2\n", ",", "date"),
        ("n;date;y\na;15.01.2020;1\nb;16.01.2020;2\n", ";", "date"),
        ('date;y\n"15.01.2020";1\n"16.01.2020";2\n', ";", "date"),
        ("date;y\n 15.01.2020 ;1\n16.01.2020;2\n", ";", "date"),
        ("date;y\n15.01.2020;1\n;2\n17.01.2020;3\n", ";", "date"),
        ("date;y\n15.01.2020;1\n16.01.2020\n", ";", "date"),
        ("date1;date2;y\n15.01.2020;16.01.2020;1\n", ";", "date1"),
    ],
    ids=[
        "dotted dates",
        "iso dates",
        "year first with points",
        "slashes with tab",
        "dashes",
        "with time",
        "with time and fraction",
        "second column",
        "quoted",
        "spaces around",
        "empty field skipped",
        "short row",
        "first of two columns of dates",
    ],
)
def test_sample_date_column_output_when_fields_are_dates_written_with_numbers(
    sample, sep, expected
):
    """
    Test that the column of the dates is the first one whose fields in the
    sample are all dates written with numbers, with '.', '/' or '-' between
    their fields, the year first or last and optionally a time, ignoring
    quotes, spaces and the empty fields.
    """
    assert sample_date_column(sample, sep) == expected


@pytest.mark.parametrize(
    "sample, sep",
    [
        ("d;y\nabc;1\nabd;2\n", ";"),
        ("d;y\n15.01.2020;1\n16 Jan 2020;2\n", ";"),
        ("d;y\n15.01.20;1\n16.01.20;2\n", ";"),
        ("d;y\n1.234;1\n2.345;2\n", ";"),
        ("d;y\n2020;1\n2021;2\n", ";"),
        ("d;y\n;1\n;2\n", ";"),
        ("d;y\n15.01.2020;1\n", ","),
        ("d;y\n", ";"),
        ("", ";"),
    ],
    ids=[
        "text",
        "one field that is not a date",
        "two digits year",
        "numbers with points",
        "years",
        "empty fields",
        "separator that does not split",
        "header only",
        "empty sample",
    ],
)
def test_sample_date_column_output_is_None_when_no_column_holds_dates(sample, sep):
    """
    Test that None is returned when no column has all its fields in the
    sample as dates written with numbers, or the sample has no records.
    """
    assert sample_date_column(sample, sep) is None


def test_sample_date_column_output_when_series_id_column_given():
    """
    Test that the column of the series ids is never the dates, even when its
    values are written as dates: the next column that holds them is.
    """
    sample = "id;date;y\n15.01.2020;15.01.2020;1\n16.01.2020;16.01.2020;2\n"

    assert sample_date_column(sample, ";") == "id"
    assert sample_date_column(sample, ";", series_id_column="id") == "date"
    assert sample_date_column(sample, ";", series_id_column="other") == "id"


@pytest.mark.parametrize(
    "date_column, expected",
    [("y", "y"), ("date", "date"), ("missing", None)],
    ids=["column that holds numbers", "column of dates", "column not in header"],
)
def test_sample_date_column_output_when_date_column_given(date_column, expected):
    """
    Test that the `date_column` given is the answer when the header holds it,
    whatever its values, and None when it does not: the caller said where
    the dates are, so the sample is not searched.
    """
    sample = "date;y\n15.01.2020;1.5\n16.01.2020;2.5\n"

    assert sample_date_column(sample, ";", date_column=date_column) == expected
