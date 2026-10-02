# Unit test build_cv_explanation recommendation/backtesting

from skforecast_ai.recommendation.backtesting import build_cv_explanation


def test_build_cv_explanation_output_when_forecaster_is_stats():
    """
    Test that build_cv_explanation appends the sentence saying that
    ForecasterStats is refitted in every fold whatever `refit` says, and
    does not add it for another forecaster.
    """
    cv_params = {
        "initial_train_size": 60,
        "steps": 10,
        "refit": True,
        "fixed_train_size": True,
        "gap": 0,
    }

    explanation = build_cv_explanation(
        cv_params, n_observations=100, n_folds=4, n_fits=4,
        forecaster="ForecasterStats",
    )
    explanation_recursive = build_cv_explanation(
        cv_params, n_observations=100, n_folds=4, n_fits=4,
        forecaster="ForecasterRecursive",
    )

    assert explanation == (
        "Using 60% of data (60 observations) for initial training, fixed "
        "window, refit every fold (4 trainings), 10-step horizon, 4 folds. "
        "ForecasterStats is refitted in every fold whatever `refit` says: "
        "skforecast requires it for ARIMA models."
    )
    assert explanation_recursive == (
        "Using 60% of data (60 observations) for initial training, fixed "
        "window, refit every fold (4 trainings), 10-step horizon, 4 folds."
    )
