# Unit test plan_override_value

import pytest

from skforecast_ai._utils import plan_override_value
from skforecast_ai.schemas import ForecastPlan

PLAN = ForecastPlan(
    task_type         = "single_series",
    forecaster        = "ForecasterRecursive",
    forecaster_kwargs = {"lags": 3},
    estimator         = "Ridge",
    steps             = 5,
    explanation       = "Plan.",
)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("forecaster", "ForecasterRecursive"),
        ("estimator", "Ridge"),
        ("estimator_kwargs", None),
        ("lags", 3),
        ("window_features", None),
        ("use_exog", False),
        ("differentiation", None),
    ],
)
def test_plan_override_value_reads_the_value_of_each_decision(name, expected):
    """
    Test that the value of each decision is read in the form `plan()`
    takes it: empty estimator keyword arguments and a missing key are None.
    """
    assert plan_override_value(PLAN, name) == expected


def test_plan_override_value_metric_lists_the_primary_metric_first():
    """
    Test that the metric is read as the list `plan(metric=...)` takes: the
    primary metric first, then the other metrics computed, in their order.
    """
    plan = PLAN.model_copy(update={
        "metric": "mean_squared_error",
        "metrics_to_compute": [
            "mean_absolute_error", "mean_squared_error", "median_absolute_error"
        ],
    })

    assert plan_override_value(plan, "metric") == [
        "mean_squared_error", "mean_absolute_error", "median_absolute_error"
    ]


def test_plan_override_value_of_feature_overrides():
    """
    Test that a machine learning plan without calendar features or scaling
    reads as `[]` and `'none'` (what `plan()` takes for none), and as None
    for a forecaster without them.
    """
    stats = ForecastPlan(
        task_type   = "statistical",
        forecaster  = "ForecasterStats",
        estimator   = "Arima",
        steps       = 5,
        explanation = "Plan.",
    )
    scaled = PLAN.model_copy(update={"forecaster_kwargs": {
        "lags": 3, "transformer_y": "StandardScaler", "dropna_from_series": True,
        "calendar_features": {"features": ["month"], "encoding": None},
    }})

    assert plan_override_value(PLAN, "calendar_features") == []
    assert plan_override_value(PLAN, "target_transformer") == "none"
    assert plan_override_value(stats, "calendar_features") is None
    assert plan_override_value(stats, "target_transformer") is None
    assert plan_override_value(scaled, "calendar_features") == ["month"]
    assert plan_override_value(scaled, "target_transformer") == "StandardScaler"
    assert plan_override_value(scaled, "dropna_from_series") is True
