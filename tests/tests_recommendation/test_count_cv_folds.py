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
