# Unit test _cv_in_time_zone

import pandas as pd
import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai._utils import _cv_in_time_zone
from skforecast_ai.schemas import DataProfile

from tests.fixtures_datasets import df_h2o, df_h2o_madrid, df_hourly_madrid_spring

# Profile of the monthly h2o (from 1991-07-01).
profile_h2o = DataProfile(
    n_series       = 1,
    series_lengths = {"x": 204},
    target         = "x",
    index_type     = "datetime",
    frequency      = "MS",
)


@pytest.mark.parametrize(
    "initial_train_size",
    ["2003-04-01", pd.Timestamp("2003-04-01")],
    ids=["text", "Timestamp"],
)
def test_cv_in_time_zone_output_when_dates_have_a_time_zone(initial_train_size):
    """
    Test that a date without time zone, on data whose dates have one, is
    read in that time zone and turned into the observations from the first
    date to it (1991-07-01 to 2003-04-01, monthly: 142), on a copy: the
    strategy passed keeps its date.
    """
    cv = TimeSeriesFold(
        steps              = 12,
        initial_train_size = initial_train_size,
        verbose            = False,
    )

    result = _cv_in_time_zone(cv, df_h2o_madrid, profile_h2o)

    assert result.initial_train_size == 142
    assert cv.initial_train_size == initial_train_size


def test_cv_in_time_zone_output_when_date_in_hour_skipped_by_daylight_saving():
    """
    Test that a date in the hour that the spring change skips
    ('2023-03-26 02:00' in Madrid), which the naive dates of the profile
    hold, is placed on the local times of the data instead of failing to
    localize: the observations up to 01:00 of that day (6 days and 2 hours,
    146).
    """
    profile = DataProfile(
        n_series       = 1,
        series_lengths = {"y": 210},
        target         = "y",
        index_type     = "datetime",
        frequency      = "h",
    )
    cv = TimeSeriesFold(
        steps              = 24,
        initial_train_size = "2023-03-26 02:00:00",
        verbose            = False,
    )

    result = _cv_in_time_zone(cv, df_hourly_madrid_spring, profile)

    assert result.initial_train_size == 146


@pytest.mark.parametrize(
    "data, initial_train_size, profile",
    [
        (df_h2o, "2003-04-01", profile_h2o),
        (df_h2o_madrid, 142, profile_h2o),
        (df_h2o_madrid, "2003-04-01 00:00:00+02:00", profile_h2o),
        (None, "2003-04-01", profile_h2o),
        (
            df_h2o_madrid, "2003-04-01",
            profile_h2o.model_copy(update={"frequency": None}),
        ),
        (df_h2o_madrid, "not a date", profile_h2o),
        (df_h2o_madrid, "1990-01-01", profile_h2o),
        (df_h2o_madrid, "2010-01-01", profile_h2o),
    ],
    ids=["dates_without_time_zone", "integer", "date_with_own_time_zone",
         "no_data", "no_frequency", "not_a_date", "before_the_data",
         "after_the_data"],
)
def test_cv_in_time_zone_output_when_strategy_unchanged(
    data, initial_train_size, profile
):
    """
    Test that the strategy is returned as it is for dates without time
    zone, an integer `initial_train_size`, a date that has its own time
    zone, no data (the script rendered from the profile, whose time zone is
    unknown), a profile without frequency, or a date that does not parse
    or is outside the dates of the data (skforecast reports them).
    """
    cv = TimeSeriesFold(
        steps              = 12,
        initial_train_size = initial_train_size,
        verbose            = False,
    )

    assert _cv_in_time_zone(cv, data, profile) is cv
