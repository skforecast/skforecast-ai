# Unit test build_plan_explanation
"""Tests for the build_plan_explanation recommendation function."""

import pytest

from skforecast_ai.recommendation import build_plan_explanation


@pytest.mark.parametrize(
    "task_type, expected",
    [
        ("foundation", "the foundation model forecasts directly from the raw context window"),
        ("statistical", "the statistical model estimates its own autoregressive and seasonal structure"),
        ("baseline", "the baseline repeats past values and learns nothing from the data"),
    ],
    ids=lambda dt: f"task_type, expected: {dt}",
)
def test_build_plan_explanation_states_why_no_lags(task_type, expected):
    """
    Test that build_plan_explanation states why foundation, statistical and
    baseline plans carry no lag or window features.
    """
    explanation = build_plan_explanation(
        forecaster         = "ForecasterFoundation",
        estimator          = "autogluon/chronos-2-small",
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


@pytest.mark.parametrize(
    "dropna_from_series, expected",
    [
        (True, "NaN rows will be dropped before fitting."),
        (False, "NaN rows kept (NaN-tolerant estimator)."),
    ],
    ids=["dropna", "keep NaN"],
)
def test_build_plan_explanation_states_nan_handling(dropna_from_series, expected):
    """
    Test that build_plan_explanation states how NaN rows are handled for
    both values of `dropna_from_series`.
    """
    explanation = build_plan_explanation(
        forecaster         = "ForecasterRecursive",
        estimator          = "LGBMRegressor",
        lags               = [1, 2, 3],
        window_features    = None,
        interval_method    = None,
        dropna_from_series = dropna_from_series,
        use_exog           = False,
    )

    assert expected in explanation


@pytest.mark.parametrize(
    "calendar_features",
    [{"features": ["day_of_week", "weekend"], "encoding": None}, None],
    ids=["some calendar features remain", "every calendar feature skipped"],
)
def test_build_plan_explanation_states_skipped_calendar_features(calendar_features):
    """
    Test that build_plan_explanation names the calendar features skipped
    because their columns already exist among the exogenous variables,
    whether or not other calendar features remain.
    """
    explanation = build_plan_explanation(
        forecaster                = "ForecasterRecursive",
        estimator                 = "LGBMRegressor",
        lags                      = [1, 2, 3],
        window_features           = None,
        interval_method           = None,
        dropna_from_series        = None,
        use_exog                  = True,
        calendar_features         = calendar_features,
        task_type                 = "single_series",
        skipped_calendar_features = ["hour", "month"],
    )

    assert (
        "Calendar features ['hour', 'month'] skipped: the exogenous variables "
        "already have columns with the names they would create, and those "
        "columns are used instead."
    ) in explanation


@pytest.mark.parametrize(
    "skipped_calendar_features",
    [None, []],
    ids=lambda skipped: f"skipped_calendar_features: {skipped}",
)
def test_build_plan_explanation_no_skipped_calendar_note_when_nothing_skipped(
    skipped_calendar_features,
):
    """
    Test that build_plan_explanation adds no skipped calendar features
    sentence when no calendar feature was left out.
    """
    explanation = build_plan_explanation(
        forecaster                = "ForecasterRecursive",
        estimator                 = "LGBMRegressor",
        lags                      = [1, 2, 3],
        window_features           = None,
        interval_method           = None,
        dropna_from_series        = None,
        use_exog                  = True,
        calendar_features         = {"features": ["month"], "encoding": None},
        task_type                 = "single_series",
        skipped_calendar_features = skipped_calendar_features,
    )

    assert "skipped" not in explanation
