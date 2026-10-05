# Unit test resolve_cv_config recommendation/backtesting

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation.backtesting import resolve_cv_config

from tests.tests_recommendation.fixtures_recommendation import (
    profile_multi_long,
    profile_single_daily_100,
)


def test_resolve_cv_config_output_when_integer_initial_train_size():
    """
    Test that resolve_cv_config returns the TimeSeriesFold parameters
    with the fold and training counts, and an explanation that states the
    fold count and, without refit, that the forecaster is trained once
    (no window type, which only matters when refitting).
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
        "n_fits": 1,
    }
    assert cv_config == expected
    assert explanation == (
        "Using 60% of data (60 observations) for initial training, trained "
        "once (no refit), 10-step horizon, 4 folds."
    )


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


def test_resolve_cv_config_output_when_forecaster_is_not_trained():
    """
    Test that the explanation for a forecaster that is not trained (a
    foundation model) states where the first fold forecasts from, instead
    of a training window and refits that do not apply to it.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=60, refit=False)

    cv_config, explanation = resolve_cv_config(
        cv, profile_single_daily_100, trains=False
    )

    assert cv_config["n_folds"] == 4
    assert cv_config["n_fits"] == 0
    assert explanation == (
        "First fold forecasts from 60% of data (60 observations), no training "
        "(each fold forecasts from the observations before it), 10-step "
        "horizon, 4 folds."
    )

    cv_date = TimeSeriesFold(steps=10, initial_train_size="2023-03-01")
    _, explanation_date = resolve_cv_config(
        cv_date, profile_single_daily_100, trains=False
    )

    assert explanation_date.startswith(
        "First fold forecasts from the data up to 2023-03-01, no training"
    )


@pytest.mark.parametrize(
    "profile, expected_windows",
    [(profile_single_daily_100, 8), (profile_multi_long, 84)],
    ids=["single series", "3 series"],
)
def test_resolve_cv_config_output_inference_windows_when_forecaster_is_foundation(
    profile, expected_windows
):
    """
    Test that for ForecasterFoundation the strategy carries its inference
    windows (series times folds), which the explanation states, and that no
    other forecaster, nor a strategy shared by several, carries them.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=20, refit=False)

    cv_config, explanation = resolve_cv_config(
        cv, profile, trains=False, forecaster="ForecasterFoundation"
    )
    cv_config_recursive, _ = resolve_cv_config(
        cv, profile, forecaster="ForecasterRecursive"
    )
    cv_config_shared, _ = resolve_cv_config(cv, profile)

    assert cv_config["inference_windows"] == expected_windows
    assert cv_config["n_fits"] == 0
    assert explanation.endswith(
        f"The model forecasts each series in each fold where it has data (up "
        f"to {expected_windows} inference windows)."
    )
    assert "inference_windows" not in cv_config_recursive
    assert "inference_windows" not in cv_config_shared


@pytest.mark.parametrize(
    "refit, forecaster, expected_n_fits, expected_explanation",
    [
        (
            True,
            None,
            4,
            "Using 60% of data (60 observations) for initial training, "
            "fixed window, refit every fold (4 trainings), 10-step horizon, "
            "4 folds.",
        ),
        (
            2,
            None,
            2,
            "Using 60% of data (60 observations) for initial training, "
            "fixed window, refit every 2 folds (2 trainings), 10-step "
            "horizon, 4 folds.",
        ),
        (
            True,
            "ForecasterDirect",
            4,
            "Using 60% of data (60 observations) for initial training, "
            "fixed window, refit every fold (4 trainings), 10-step horizon, "
            "4 folds. ForecasterDirect fits one estimator per step, so each "
            "training fits 10 estimators (40 fits in all).",
        ),
        (
            False,
            "ForecasterDirect",
            1,
            "Using 60% of data (60 observations) for initial training, "
            "trained once (no refit), 10-step horizon, 4 folds. "
            "ForecasterDirect fits one estimator per step, so each training "
            "fits 10 estimators (10 fits in all).",
        ),
        (
            True,
            "ForecasterRecursive",
            4,
            "Using 60% of data (60 observations) for initial training, "
            "fixed window, refit every fold (4 trainings), 10-step horizon, "
            "4 folds.",
        ),
    ],
    ids=[
        "refit every fold",
        "refit every 2 folds",
        "direct forecaster refit every fold",
        "direct forecaster trained once",
        "recursive forecaster",
    ],
)
def test_resolve_cv_config_states_training_cost(
    refit, forecaster, expected_n_fits, expected_explanation
):
    """
    Test that resolve_cv_config counts the folds that train the forecaster
    and states them when it is refitted, together with the window type,
    and that for a direct forecaster, which fits one estimator per step,
    the explanation also states the total number of estimator fits.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=60, refit=refit)

    cv_config, explanation = resolve_cv_config(
        cv, profile_single_daily_100, forecaster=forecaster
    )

    assert cv_config["n_fits"] == expected_n_fits
    assert explanation == expected_explanation


def test_resolve_cv_config_output_when_stats_does_not_refit():
    """
    Test that for ForecasterStats a `refit=False` splitter is described as
    skforecast runs it: refit in every fold on a fixed window, with one
    training per fold and the sentence saying why. The splitter passed in
    is not modified.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=60, refit=False)

    cv_config, explanation = resolve_cv_config(
        cv, profile_single_daily_100, forecaster="ForecasterStats"
    )

    expected = {
        "steps": 10,
        "initial_train_size": 60,
        "refit": True,
        "fixed_train_size": True,
        "gap": 0,
        "fold_stride": 10,
        "skip_folds": None,
        "allow_incomplete_fold": True,
        "differentiation": None,
        "n_folds": 4,
        "n_fits": 4,
    }
    assert cv_config == expected
    assert explanation == (
        "Using 60% of data (60 observations) for initial training, fixed "
        "window, refit every fold (4 trainings), 10-step horizon, 4 folds. "
        "ForecasterStats is refitted in every fold whatever `refit` says: "
        "skforecast requires it for ARIMA models."
    )
    assert cv.refit is False
