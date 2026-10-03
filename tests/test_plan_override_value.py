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
