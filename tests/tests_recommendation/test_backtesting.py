# Unit test _compute_min_train_size recommendation/backtesting
"""Tests for the _compute_min_train_size backtesting helper."""

from skforecast_ai.recommendation.backtesting import _compute_min_train_size
from skforecast_ai.schemas import ForecastPlan


def _make_plan(task_type: str, steps: int, forecaster_kwargs: dict) -> ForecastPlan:
    """
    Build a minimal ForecastPlan for window-size computation, without
    validation, so the helper is also tested on hand-built plans.
    """
    return ForecastPlan.model_construct(
        task_type         = task_type,
        forecaster        = "ForecasterRecursive",
        forecaster_kwargs = forecaster_kwargs,
        steps             = steps,
        explanation       = "test plan",
    )


def test_compute_min_train_size_output_when_lags_only():
    """
    Test that with only integer lags the minimum train size is
    max_lag + steps.
    """
    plan = _make_plan("single_series", steps=10, forecaster_kwargs={"lags": 24})

    assert _compute_min_train_size(plan) == 34


def test_compute_min_train_size_output_when_lags_list():
    """
    Test that a list of lags uses its maximum value as the effective
    window.
    """
    plan = _make_plan("single_series", steps=10, forecaster_kwargs={"lags": [1, 2, 24]})

    assert _compute_min_train_size(plan) == 34


def test_compute_min_train_size_output_when_window_features_int_dominate_lags():
    """
    Test that an integer window_size larger than max_lag drives the
    effective window, so min train size is max_window + steps.
    """
    plan = _make_plan(
        "single_series",
        steps=10,
        forecaster_kwargs={
            "lags": 7,
            "window_features": [{"stats": ["mean"], "window_size": 30}],
        },
    )

    assert _compute_min_train_size(plan) == 40


def test_compute_min_train_size_output_when_window_features_list_sizes():
    """
    Test that a list of window_size uses its maximum value when
    computing the effective window.
    """
    plan = _make_plan(
        "single_series",
        steps=10,
        forecaster_kwargs={
            "lags": 5,
            "window_features": [{"stats": ["mean"], "window_size": [3, 14]}],
        },
    )

    assert _compute_min_train_size(plan) == 24


def test_compute_min_train_size_output_when_lags_empty_list():
    """
    Test that a hand-built plan holding an empty lags list is treated as
    having no lags (2 * steps) instead of raising from `max()`.
    """
    plan = _make_plan(
        "single_series",
        steps=10,
        forecaster_kwargs={"lags": [], "window_features": None},
    )

    assert _compute_min_train_size(plan) == 20


def test_compute_min_train_size_output_when_no_lags_or_window_features():
    """
    Test that with no lags and no window features the effective window
    is zero, so the fallback minimum train size is 2 * steps.
    """
    plan = _make_plan("single_series", steps=10, forecaster_kwargs={})

    assert _compute_min_train_size(plan) == 20


def test_compute_min_train_size_output_when_statistical_task():
    """
    Test that statistical tasks skip the window computation and return
    2 * steps regardless of forecaster kwargs.
    """
    plan = _make_plan("statistical", steps=12, forecaster_kwargs={"lags": 99})

    assert _compute_min_train_size(plan) == 24


def test_compute_min_train_size_output_when_baseline_task():
    """
    Test that baseline tasks need more observations than the baseline window
    (`offset * n_offsets`) plus one horizon.
    """
    plan = _make_plan(
        "baseline", steps=5, forecaster_kwargs={"offset": 12, "n_offsets": 2}
    )

    assert _compute_min_train_size(plan) == 29


def test_compute_min_train_size_output_when_baseline_window_smaller_than_steps():
    """
    Test that a short baseline window still requires at least 2 * steps
    observations, as the other forecasters without features do.
    """
    plan = _make_plan(
        "baseline", steps=10, forecaster_kwargs={"offset": 1, "n_offsets": 1}
    )

    assert _compute_min_train_size(plan) == 20


def test_compute_min_train_size_output_when_differentiation():
    """
    Test that the differentiation order adds to the window: max_lag +
    differentiation + steps.
    """
    plan = _make_plan(
        "single_series", steps=10,
        forecaster_kwargs={"lags": 24, "differentiation": 2},
    )

    assert _compute_min_train_size(plan) == 36
