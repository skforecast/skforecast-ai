# Unit test count_cv_fits recommendation/backtesting

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation.backtesting import count_cv_fits


@pytest.mark.parametrize(
    "refit, expected",
    [(False, 1), (True, 10), (3, 4), (0, 1)],
    ids=lambda value: f"{value}",
)
def test_count_cv_fits_output_when_refit_varies(refit, expected):
    """
    Test that count_cv_fits counts the folds that train the forecaster:
    only the first without refit (or refit 0), every fold with True, and
    every n folds with an integer (folds 0, 3, 6 and 9 of 10).
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=50, refit=refit)

    assert count_cv_fits(cv=cv, n_observations=100) == expected


def test_count_cv_fits_output_when_initial_train_size_is_a_date():
    """
    Test that a date-based initial_train_size is split on a DatetimeIndex
    built from the start date and frequency, like count_cv_folds.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size="2023-03-01", refit=True)

    result = count_cv_fits(
        cv             = cv,
        n_observations = 100,
        start_date     = "2023-01-01",
        frequency      = "D",
    )

    assert result == 4
