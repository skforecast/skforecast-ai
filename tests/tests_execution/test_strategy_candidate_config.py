# Unit test strategy_candidate_config

import pytest

from skforecast_ai.execution.comparison import strategy_candidate_config

from tests.fixtures_compare import (
    plan_sales,
    plan_sales_all_overrides,
    plan_sales_direct,
    plan_sales_edited,
    plan_sales_refined,
    plan_sales_stats,
    plan_sales_window_features,
)

_WINDOW_FEATURES = [
    {"stats": ["mean", "std"], "window_size": 3},
    {"stats": ["mean"], "window_size": 7},
    {"stats": ["mean"], "window_size": 21},
]


@pytest.mark.parametrize(
    "plan, expected",
    [
        (
            plan_sales,
            {
                "forecaster": "ForecasterRecursive",
                "estimator": "Ridge",
                "lags": [1, 2, 3, 4, 5, 7],
                "window_features": _WINDOW_FEATURES,
            },
        ),
        (
            plan_sales_direct,
            {
                "forecaster": "ForecasterDirect",
                "estimator": "Ridge",
                "lags": [1, 2, 3, 4, 5, 7],
                "window_features": _WINDOW_FEATURES,
            },
        ),
        (
            plan_sales_refined,
            {
                "forecaster": "ForecasterRecursive",
                "estimator": "RandomForestRegressor",
                "lags": [1, 2, 3],
                "window_features": _WINDOW_FEATURES,
            },
        ),
        (
            plan_sales_window_features,
            {
                "forecaster": "ForecasterRecursive",
                "estimator": "Ridge",
                "lags": [1, 2, 3, 4, 5, 7],
                "window_features": [{"stats": ["mean"], "window_size": 3}],
            },
        ),
        (
            plan_sales_stats,
            {"forecaster": "ForecasterStats", "estimator": "Arima"},
        ),
    ],
    ids=["recommended", "direct", "refined", "window features", "stats"],
)
def test_strategy_candidate_config_output(plan, expected):
    """
    Test that the forecaster, the estimator, the lags and the window
    features of the plan are carried over, with no key for a value the plan
    does not hold (ForecasterStats has no lags) and no `interval` or
    `metric`, which are the comparison's.
    """
    assert strategy_candidate_config(plan) == expected


def test_strategy_candidate_config_carries_over_the_decisions_of_the_user():
    """
    Test that `estimator_kwargs`, `use_exog`, `differentiation`,
    `calendar_features` and `target_transformer` are carried over when the
    user chose them (`overridden_fields`), in the form `plan()` takes them.
    """
    assert plan_sales_all_overrides.overridden_fields == [
        "estimator",
        "estimator_kwargs",
        "lags",
        "use_exog",
        "differentiation",
        "calendar_features",
        "target_transformer",
    ]
    assert strategy_candidate_config(plan_sales_all_overrides) == {
        "forecaster": "ForecasterRecursive",
        "estimator": "Ridge",
        "estimator_kwargs": {"alpha": 2.0},
        "lags": [1, 2],
        "window_features": _WINDOW_FEATURES,
        "use_exog": False,
        "differentiation": 1,
        "calendar_features": ["day_of_week"],
        "target_transformer": "StandardScaler",
    }


def test_strategy_candidate_config_leaves_to_the_rules_what_the_user_did_not_choose():
    """
    Test that a `differentiation` the plan holds but the user did not choose
    (not in `overridden_fields`, as when the plan was edited by hand) is not
    carried over, so the rules decide it again.
    """
    assert plan_sales_edited.forecaster_kwargs["differentiation"] == 1
    assert "differentiation" not in plan_sales_edited.overridden_fields
    assert "differentiation" not in strategy_candidate_config(plan_sales_edited)


def test_strategy_candidate_config_does_not_share_estimator_kwargs_with_the_plan():
    """
    Test that the configuration holds a copy of `estimator_kwargs`, so
    changing it does not change the plan.
    """
    config = strategy_candidate_config(plan_sales_all_overrides)

    config["estimator_kwargs"]["alpha"] = 99.0

    assert plan_sales_all_overrides.estimator_kwargs == {"alpha": 2.0}
