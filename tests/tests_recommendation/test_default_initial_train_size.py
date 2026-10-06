# Unit test default_initial_train_size skforecast_ai.recommendation.backtesting

import pytest

from skforecast_ai.recommendation.backtesting import (
    default_initial_train_size,
    derive_cv_defaults,
)
from skforecast_ai.schemas import DataProfile, ForecastingProfile, ForecastPlan


def _make_profile(n_observations: int, dated: bool = True) -> ForecastingProfile:
    """
    Build a profile of a daily series that starts on 2020-01-01 (or of a
    series without dates), without validation of the modeling decisions.
    """
    if dated:
        data_profile = DataProfile(
            n_series       = 1,
            series_lengths = {"y": n_observations},
            target         = "y",
            index_type     = "datetime",
            frequency      = "D",
            start_date     = "2020-01-01",
        )
    else:
        data_profile = DataProfile(
            n_series       = 1,
            series_lengths = {"y": n_observations},
            target         = "y",
            index_type     = "range",
        )

    return ForecastingProfile.model_construct(data_profile=data_profile)


def _make_plan(
    task_type: str,
    steps: int,
    forecaster_kwargs: dict,
    forecaster: str = "ForecasterRecursive",
) -> ForecastPlan:
    """Build a minimal ForecastPlan, without validation."""
    return ForecastPlan.model_construct(
        task_type         = task_type,
        forecaster        = forecaster,
        forecaster_kwargs = forecaster_kwargs,
        steps             = steps,
        explanation       = "test plan",
    )


@pytest.mark.parametrize(
    "profile, plan, expected",
    [
        (
            _make_profile(100),
            _make_plan("single_series", 10, {"lags": 5}),
            {
                "value": "2020-03-10",
                "position": 70,
                "rule": "share",
                "n_observations": 100,
                "share": 70,
                "minimum": 15,
                "needed": 6,
                "window_size": 5,
                "steps": 10,
            },
        ),
        (
            _make_profile(100),
            _make_plan("single_series", 10, {"lags": 65}),
            {
                "value": "2020-03-15",
                "position": 75,
                "rule": "minimum",
                "n_observations": 100,
                "share": 70,
                "minimum": 75,
                "needed": 66,
                "window_size": 65,
                "steps": 10,
            },
        ),
        (
            _make_profile(100),
            _make_plan("single_series", 20, {"lags": 5}),
            {
                "value": "2020-02-29",
                "position": 60,
                "rule": "two_folds",
                "n_observations": 100,
                "share": 70,
                "minimum": 25,
                "needed": 6,
                "window_size": 5,
                "steps": 20,
            },
        ),
        (
            _make_profile(100),
            _make_plan("single_series", 20, {"lags": 70}),
            {
                "value": "2020-02-29",
                "position": 60,
                "rule": "two_folds",
                "n_observations": 100,
                "share": 70,
                "minimum": 90,
                "needed": 71,
                "window_size": 70,
                "steps": 20,
            },
        ),
    ],
    ids=["share", "minimum", "two_folds_from_share", "two_folds_from_minimum"],
)
def test_default_initial_train_size_output_when_rule_applies(
    profile, plan, expected
):
    """
    Test that default_initial_train_size returns the date, the position and
    the numbers of the rules, and names the last rule applied: the share of
    the observations, the minimum the forecaster needs, or the room for two
    folds (reached from the share or from the minimum).
    """
    default = default_initial_train_size(profile, plan)

    assert default == expected
    assert (
        derive_cv_defaults(profile, plan)["initial_train_size"] == default["value"]
    )


def test_default_initial_train_size_output_when_minimum_equals_share():
    """
    Test that a tie between the share and the minimum keeps the rule
    'share': the minimum only wins when it is larger.
    """
    # lags 60 plus 10 steps is a minimum of 70, the share of 100.
    profile = _make_profile(100)
    plan = _make_plan("single_series", 10, {"lags": 60})

    default = default_initial_train_size(profile, plan)

    assert default == {
        "value": "2020-03-10",
        "position": 70,
        "rule": "share",
        "n_observations": 100,
        "share": 70,
        "minimum": 70,
        "needed": 61,
        "window_size": 60,
        "steps": 10,
    }


def test_default_initial_train_size_output_when_minimum_leaves_no_room_for_folds():
    """
    Test that the minimum rule stands when the series is too short for two
    folds (`n - 2 * steps <= 0`), where the two-folds cap does not apply:
    the position exceeds the number of observations.
    """
    profile = _make_profile(60)
    plan = _make_plan("statistical", 40, {}, forecaster="ForecasterStats")

    default = default_initial_train_size(profile, plan)

    assert default == {
        "value": "2020-03-20",
        "position": 80,
        "rule": "minimum",
        "n_observations": 60,
        "share": 42,
        "minimum": 80,
        "needed": None,
        "window_size": None,
        "steps": 40,
    }
    assert derive_cv_defaults(profile, plan)["initial_train_size"] == "2020-03-20"


@pytest.mark.parametrize(
    "plan, expected",
    [
        (
            _make_plan("single_series", 10, {"lags": 5}),
            {
                "value": 70,
                "position": 70,
                "rule": "share",
                "n_observations": 100,
                "share": 70,
                "minimum": 15,
                "needed": 6,
                "window_size": 5,
                "steps": 10,
            },
        ),
        (
            _make_plan("single_series", 10, {"lags": 65}),
            {
                "value": 75,
                "position": 75,
                "rule": "minimum",
                "n_observations": 100,
                "share": 70,
                "minimum": 75,
                "needed": 66,
                "window_size": 65,
                "steps": 10,
            },
        ),
        (
            _make_plan("single_series", 20, {"lags": 5}),
            {
                "value": 60,
                "position": 60,
                "rule": "two_folds",
                "n_observations": 100,
                "share": 70,
                "minimum": 25,
                "needed": 6,
                "window_size": 5,
                "steps": 20,
            },
        ),
    ],
    ids=["share", "minimum", "two_folds"],
)
def test_default_initial_train_size_output_when_data_has_no_dates(plan, expected):
    """
    Test that without dates the value is the number of observations (an
    integer equal to the position), whatever the rule.
    """
    profile = _make_profile(100, dated=False)

    default = default_initial_train_size(profile, plan)

    assert default == expected
    assert (
        derive_cv_defaults(profile, plan)["initial_train_size"] == default["value"]
    )


@pytest.mark.parametrize(
    "forecaster, expected",
    [("ForecasterRecursive", 6), ("ForecasterDirect", 15)],
    ids=["recursive: window plus one", "direct: window plus the steps"],
)
def test_default_initial_train_size_output_needed_by_forecaster(forecaster, expected):
    """
    Test that `needed` is the fewest observations skforecast runs the
    forecaster with: more than its window of 5, plus the 10 steps for a
    direct forecaster, which trains one estimator per step.
    """
    result = default_initial_train_size(
        _make_profile(100),
        _make_plan("single_series", 10, {"lags": 5}, forecaster=forecaster),
    )

    assert result["needed"] == expected
    assert result["minimum"] == 15
