# Unit test resolve_cv_config recommendation/backtesting

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation.backtesting import resolve_cv_config

from tests.tests_recommendation.fixtures_recommendation import (
    profile_single_daily_100,
)


def test_resolve_cv_config_output_when_integer_initial_train_size():
    """
    Test that resolve_cv_config returns the TimeSeriesFold parameters
    with the fold count, and an explanation that states that count.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=60, refit=False)

    cv_config, explanation = resolve_cv_config(cv, profile_single_daily_100)

    expected = {
        "steps": 10,
        "initial_train_size": 60,
        "refit": False,
        "fixed_train_size": True,
        "gap": 0,
        "fold_stride": 10,
        "skip_folds": None,
        "allow_incomplete_fold": True,
        "differentiation": None,
        "n_folds": 4,
    }
    assert cv_config == expected
    assert "4 folds" in explanation
    assert "fixed window, no refit" in explanation


def test_resolve_cv_config_output_when_date_initial_train_size():
    """
    Test that a date-based initial_train_size is counted against a
    DatetimeIndex built from the profile start date and frequency.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size="2023-03-01")

    cv_config, explanation = resolve_cv_config(cv, profile_single_daily_100)

    assert cv_config["initial_train_size"] == "2023-03-01"
    assert cv_config["n_folds"] == 4
    assert "Initial training up to 2023-03-01" in explanation
