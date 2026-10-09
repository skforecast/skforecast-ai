# Unit test count_cv_folds recommendation/backtesting

import re

import pandas as pd
import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation.backtesting import count_cv_folds

from tests.tests_recommendation.fixtures_recommendation import (
    profile_single_daily_100,
)


@pytest.mark.parametrize(
    "start_date, frequency",
    [(None, None), ("2023-01-01", None), (None, "D")],
    ids=lambda value: f"{value}",
)
@pytest.mark.parametrize(
    "initial_train_size",
    ["2023-03-01", pd.Timestamp("2023-03-01")],
    ids=["str", "Timestamp"],
)
def test_count_cv_folds_ValueError_when_date_without_datetime_index(
    start_date, frequency, initial_train_size
):
    """
    Test that a date-based initial_train_size raises ValueError when the
    dataset has no start date or no known frequency, instead of counting
    folds on a guessed index.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=initial_train_size)

    err_msg = re.escape(
        f"`initial_train_size` is a date ({initial_train_size!r}) but the "
        f"dataset has no datetime index with a known frequency, so the split "
        f"date cannot be located. Pass an integer number of observations "
        f"instead."
    )
    with pytest.raises(ValueError, match=err_msg):
        count_cv_folds(
            cv             = cv,
            n_observations = 100,
            start_date     = start_date,
            frequency      = frequency,
        )


def test_count_cv_folds_ValueError_when_date_unparseable():
    """
    Test that an initial_train_size string that is not a date raises a
    ValueError naming the parameter instead of a raw pandas parsing error.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size="next spring")

    err_msg = re.escape(
        "`initial_train_size` date 'next spring' could not be parsed. Use an "
        "ISO date such as '2023-03-01'."
    )
    with pytest.raises(ValueError, match=err_msg):
        count_cv_folds(
            cv             = cv,
            n_observations = 100,
            start_date     = profile_single_daily_100.start_date,
            frequency      = profile_single_daily_100.frequency,
        )


def test_count_cv_folds_output_when_integer_initial_train_size():
    """
    Test that an integer initial_train_size is counted against a plain
    RangeIndex: 100 observations, 60 for training and 10 steps give 4
    folds.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=60)

    n_folds = count_cv_folds(cv=cv, n_observations=100)

    assert n_folds == 4


@pytest.mark.parametrize(
    "initial_train_size",
    ["2023-03-01", pd.Timestamp("2023-03-01")],
    ids=["str", "Timestamp"],
)
def test_count_cv_folds_output_when_date_initial_train_size(initial_train_size):
    """
    Test that a date string and the equivalent Timestamp are located on
    the reconstructed DatetimeIndex and give the same fold count (60
    training days of 100, 10 steps: 4 folds).
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=initial_train_size)

    n_folds = count_cv_folds(
                  cv             = cv,
                  n_observations = 100,
                  start_date     = profile_single_daily_100.start_date,
                  frequency      = profile_single_daily_100.frequency,
              )

    assert n_folds == 4


@pytest.mark.parametrize(
    "start_date, frequency, n_observations, initial_train_size, expected",
    [
        ("1991-07-01", "MS", 204, "2003-04-01", 6),
        ("1991-07-01", "MS", 204, "2003-04-01 00:00:00+02:00", 6),
        ("1991-07-01", "MS", 204, "2003-03-31 22:00:00+00:00", 6),
        ("2023-03-20", "h", 210, "2023-03-27 00:00:00", 4),
        ("2023-03-20", "h", 210, "2023-03-27 00:00:00+02:00", 4),
        ("2023-03-20", "h", 210, "2023-03-26 22:00:00+00:00", 4),
        (
            "2023-03-20", "h", 210,
            pd.Timestamp("2023-03-27", tz="Europe/Madrid"), 4,
        ),
        ("2023-03-20", "h", 210, "2023-03-25 00:00:00", 8),
        ("2023-03-20", "h", 210, "2023-03-25 00:00:00+01:00", 8),
    ],
    ids=[
        "monthly: no zone", "monthly: local offset", "monthly: UTC",
        "hourly after the change: no zone",
        "hourly after the change: local offset",
        "hourly after the change: UTC",
        "hourly after the change: Timestamp",
        "hourly before the change: no zone",
        "hourly before the change: local offset",
    ],
)
def test_count_cv_folds_output_when_date_has_a_time_zone(
    start_date, frequency, n_observations, initial_train_size, expected
):
    """
    Test that a date with a time zone, on data whose dates have one
    (Europe/Madrid, hourly across the spring daylight saving change and
    monthly), is placed at its instant and gives the folds of the same date
    without time zone, on a strategy that keeps its date.
    """
    cv = TimeSeriesFold(steps=12, initial_train_size=initial_train_size)

    n_folds = count_cv_folds(
                  cv             = cv,
                  n_observations = n_observations,
                  start_date     = start_date,
                  frequency      = frequency,
                  time_zone      = "Europe/Madrid",
              )

    assert n_folds == expected
    assert cv.initial_train_size == initial_train_size


def test_count_cv_folds_ValueError_when_date_with_time_zone_outside_the_data():
    """
    Test that a date with a time zone after the last date of data whose
    dates have one is reported as outside the data, not as a date with a
    time zone on an index without one.
    """
    cv = TimeSeriesFold(steps=12, initial_train_size="2030-04-01 00:00:00+02:00")

    err_msg = re.escape(
        "If `initial_train_size` is a date, it must be within the index range, "
        "between the first and the last date (both included)."
    )
    with pytest.raises(ValueError, match=err_msg):
        count_cv_folds(
            cv             = cv,
            n_observations = 204,
            start_date     = "1991-07-01",
            frequency      = "MS",
            time_zone      = "Europe/Madrid",
        )


def test_count_cv_folds_ValueError_when_date_with_time_zone_and_dates_without():
    """
    Test that a date with a time zone, on data whose dates have none, is
    rejected with the error of skforecast.
    """
    cv = TimeSeriesFold(steps=12, initial_train_size="2003-04-01 00:00:00+02:00")

    err_msg = re.escape(
        "`initial_train_size` has a time zone (UTC+02:00), but the index has "
        "none. Use a date without time zone."
    )
    with pytest.raises(ValueError, match=err_msg):
        count_cv_folds(
            cv             = cv,
            n_observations = 204,
            start_date     = "1991-07-01",
            frequency      = "MS",
        )
