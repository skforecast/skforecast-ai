# Unit test time_zones

import pandas as pd
import pytest

from skforecast_ai._dates import time_zones


@pytest.mark.parametrize(
    "values, expected",
    [
        (["2012-03-25", "2012-03-26"], ["no time zone"]),
        (["2012-03-25 10:00:00", "2012-03-25 11:00"], ["no time zone"]),
        (
            ["2012-03-25T01:00:00+01:00", "2012-03-25T03:00:00+02:00"],
            ["+01:00", "+02:00"],
        ),
        (
            [
                "2012-03-25T01:00:00Z",
                "2012-03-25T02:00:00+00:00",
                "2012-03-25 03:00:00 UTC",
            ],
            ["+00:00"],
        ),
        (
            [
                "2012-01-01T00:00:00+0100",
                "2012-01-01T01:00:00+01:00",
                "2012-01-01T02:00+01",
            ],
            ["+01:00"],
        ),
        (
            ["2012-01-01 00:00:00.123456+05:30", "2012-01-01 00:00:01.5+05:30"],
            ["+05:30"],
        ),
        (
            ["2012-03-20 00:00:00 CET", "2012-03-28 09:00:00 CEST"],
            ["no time zone"],
        ),
        (
            ["2012-01-01 00:00:00+01:00", "2012-01-01 01:00:00"],
            ["+01:00", "no time zone"],
        ),
        (["2012-03-20 10:00 PM", "2012-03-20 11:00 AM"], ["no time zone"]),
        (["25-03-2012", "26-03-2013"], ["no time zone"]),
        (["01-Jan-2012", "02-Jan-2013"], ["no time zone"]),
        (["2023-01-01 00:00 Sun", "2023-01-02 00:00 Mon"], ["no time zone"]),
        (["2023-01-01 00:00 Jan", "2023-02-01 00:00 Feb"], ["no time zone"]),
        (["01:30 hrs", "00:45 min"], ["no time zone"]),
        (
            ["03/08/2024 12:00:00 AM -0500", "03/12/2024 12:00:00 AM -0400"],
            ["-05:00", "-04:00"],
        ),
        (
            ["Sat Mar 24 20:00:00 +0100 2012", "Sun Mar 25 20:00:00 +0200 2012"],
            ["+01:00", "+02:00"],
        ),
        (
            ["2012-03-24 00:00:00 GMT+01:00", "2012-03-26 00:00:00 GMT+02:00"],
            ["+01:00", "+02:00"],
        ),
        (["20120324T000000+0100", "20120326T000000+0200"], ["+01:00", "+02:00"]),
        (
            [
                "2012-01-01T10:00:00Z",
                "2012-01-01T11:00:00z",
                "2012-01-01T12:00:00-00:00",
            ],
            ["+00:00"],
        ),
        (
            ["2012-01-01 10:00:00 UT", "2012-01-02 10:00:00"],
            ["no time zone"],
        ),
    ],
    ids=[
        "dates", "dates_with_times", "daylight_saving_change", "utc_spellings",
        "offset_spellings", "fractions_of_second", "zone_names",
        "offset_and_none", "am_pm", "year_after_dash", "month_name",
        "weekday_after_time", "month_after_time", "durations",
        "offset_after_am_pm", "offset_before_year", "gmt_prefix",
        "iso_basic_format", "utc_lowercase_and_negative_zero", "ut_word",
    ],
)
def test_time_zones_output_when_text(values, expected):
    """
    Test that the time zone of a text date is read after its time, also
    after AM or PM, a 'GMT' prefix, a time without colons or before a final
    year: offsets in any spelling count once, the names of UTC count as
    '+00:00', other words (zone names such as 'CET', AM, PM, weekdays,
    months, units) are not time zones, and the year after a dash
    ('25-03-2012') is not an offset.
    """
    assert time_zones(pd.Series(values, dtype=object)) == expected


def test_time_zones_output_when_datetime_objects():
    """
    Test that datetime objects are left out, as pandas reads their time
    zones when it parses them.
    """
    values = pd.Series(
        [pd.Timestamp("2012-03-27", tz="UTC"), pd.Timestamp("2012-03-28")],
        dtype=object,
    )

    assert time_zones(values) == []
