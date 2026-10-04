# Unit test constant_calendar_features

import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.profiling import create_data_profile
from skforecast_ai.recommendation.calendar import constant_calendar_features

from tests.fixtures_assistant import df_single
from tests.fixtures_datasets import df_h2o, df_h2o_long, df_hourly_madrid_spring

ALL_FEATURES = [
    "year", "month", "week", "day_of_week", "day_of_month", "day_of_year",
    "weekend", "hour", "minute", "second", "quarter",
]

profile_daily = create_data_profile(df_single, target="sales", date_column="date")
profile_monthly = create_data_profile(df_h2o, target="x")
profile_long_monthly = create_data_profile(
    df_h2o_long, target="x", date_column="date", series_id_column="series"
)
profile_hourly_madrid = create_data_profile(df_hourly_madrid_spring, target="y")
profile_weekly = create_data_profile(
    pd.DataFrame(
        {"y": np.arange(60, dtype=float)},
        index=pd.date_range("2023-01-01", periods=60, freq="W-SUN"),
    ),
    target="y",
)
# Daily data at midnight UTC read in Madrid: the local hour is 1 in winter
# and 2 in summer, and the profile writes the first date with its offset.
profile_daily_utc_in_madrid = create_data_profile(
    pd.DataFrame(
        {"y": np.arange(400, dtype=float)},
        index=pd.date_range(
            "2020-01-01", periods=400, freq="D", tz="UTC"
        ).tz_convert("Europe/Madrid"),
    ),
    target="y",
)
profile_two_hourly = create_data_profile(
    pd.DataFrame(
        {"y": np.arange(60, dtype=float)},
        index=pd.date_range("2023-01-01", periods=60, freq="2h"),
    ),
    target="y",
)


@pytest.mark.parametrize(
    "data_profile, expected",
    [
        (profile_daily, ["hour", "minute", "second"]),
        (profile_monthly, ["day_of_month", "hour", "minute", "second"]),
        (profile_long_monthly, ["day_of_month", "hour", "minute", "second"]),
        (profile_weekly, ["day_of_week", "weekend", "hour", "minute", "second"]),
        (profile_hourly_madrid, ["minute", "second"]),
        (profile_two_hourly, ["minute", "second"]),
        (profile_daily_utc_in_madrid, ["minute", "second"]),
    ],
    ids=[
        "daily", "monthly", "long_monthly", "weekly", "hourly_madrid",
        "two_hourly", "daily_utc_in_madrid",
    ],
)
def test_constant_calendar_features_output(data_profile, expected):
    """
    Test that the features finer than the frequency whose column is
    constant on the grid of the data are listed in the order given: on
    daily data the hour, minute and second; on monthly data also the day of
    the month (always 1 with 'MS'), in single and long format; on weekly
    data the day of the week and the weekend; on hourly data (also across a
    change of time) the minute and the second. Every 2 hours the hour still
    changes, so it is not listed, and so does the local hour of daily data
    at midnight UTC read in Madrid (1 in winter, 2 in summer).
    """
    assert constant_calendar_features(ALL_FEATURES, data_profile) == expected


def test_constant_calendar_features_output_keeps_coarser_constant_features():
    """
    Test that a feature coarser than the frequency that is constant only
    because the data are short is not listed: the year of 100 days from
    2023-01-01 to 2023-04-10 (the quarter and the month change).
    """
    assert profile_daily.span_index_length == 100
    features = ["year", "quarter", "month"]

    assert constant_calendar_features(features, profile_daily) == []


@pytest.mark.parametrize(
    "features, update",
    [
        ([], {}),
        (["hour"], {"frequency": None}),
        (["hour"], {"span_index_length": 1}),
        (["hour"], {"time_zone": "Not/A_Zone"}),
    ],
    ids=["no_features", "no_frequency", "single_date", "unknown_zone"],
)
def test_constant_calendar_features_output_empty_when_no_grid(features, update):
    """
    Test that nothing is listed without features, without a frequency, with
    fewer than two dates, or with a time zone pandas rejects, where the grid
    of the data cannot be built.
    """
    data_profile = profile_daily.model_copy(update=update)

    assert constant_calendar_features(features, data_profile) == []


@pytest.mark.parametrize(
    "start",
    ["2023-01-02", "2023-01-06"],
    ids=["first date a Monday", "first date a Friday"],
)
def test_constant_calendar_features_output_weekend_on_business_days(start):
    """
    Test that `'weekend'` is listed for business-day data, which step by a
    day and never reach a weekend, whatever the first date.
    """
    data_profile = create_data_profile(
        pd.DataFrame(
            {"y": np.arange(60, dtype=float)},
            index=pd.date_range(start, periods=60, freq="B"),
        ),
        target="y",
    )

    result = constant_calendar_features(ALL_FEATURES, data_profile)

    assert result == ["weekend", "hour", "minute", "second"]


def test_constant_calendar_features_emits_no_warning():
    """
    Test that the check emits no warning of its own: numpy 2.5 deprecates
    the unit that pandas reads a text such as '1h' with.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = constant_calendar_features(["hour", "month"], profile_daily)

    assert result == ["hour"]
