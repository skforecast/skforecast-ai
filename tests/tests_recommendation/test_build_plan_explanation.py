# Unit test build_plan_explanation
"""Tests for the build_plan_explanation recommendation function."""

import pytest

from skforecast_ai.recommendation import build_plan_explanation


@pytest.mark.parametrize(
    "task_type, expected",
    [
        ("foundation", "the foundation model forecasts directly from the raw context window"),
        ("statistical", "the statistical model estimates its own autoregressive and seasonal structure"),
    ],
    ids=lambda dt: f"task_type, expected: {dt}",
)
def test_build_plan_explanation_states_why_no_lags(task_type, expected):
    """
    Test that build_plan_explanation states why foundation and statistical
    plans carry no lag or window features.
    """
    explanation = build_plan_explanation(
        forecaster         = "ForecasterFoundation",
        estimator          = "Chronos-2",
        lags               = None,
        window_features    = None,
        interval_method    = "native",
        dropna_from_series = None,
        use_exog           = False,
        task_type          = task_type,
    )

    assert "No lag or window features:" in explanation
    assert expected in explanation


@pytest.mark.parametrize(
    "task_type",
    [None, "single_series"],
    ids=lambda task_type: f"task_type: {task_type}",
)
def test_build_plan_explanation_no_missing_lags_note_when_lags_present(task_type):
    """
    Test that build_plan_explanation reports the lags instead of the
    no-features note whenever lags are available.
    """
    explanation = build_plan_explanation(
        forecaster         = "ForecasterRecursive",
        estimator          = "LGBMRegressor",
        lags               = [1, 2, 3],
        window_features    = None,
        interval_method    = "bootstrapping",
        dropna_from_series = False,
        use_exog           = True,
        task_type          = task_type,
    )

    assert "Lags: [1, 2, 3]." in explanation
    assert "No lag or window features:" not in explanation
