# Unit test cv_fields_without_effect skforecast_ai.recommendation.backtesting

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation.backtesting import cv_fields_without_effect
from skforecast_ai.schemas import ForecastPlan


def _make_plan(task_type: str, forecaster: str) -> ForecastPlan:
    """Build a minimal ForecastPlan, without validation."""
    return ForecastPlan.model_construct(
        task_type         = task_type,
        forecaster        = forecaster,
        forecaster_kwargs = {},
        steps             = 10,
        explanation       = "test plan",
    )


plan_recursive = _make_plan("single_series", "ForecasterRecursive")
plan_stats = _make_plan("statistical", "ForecasterStats")
plan_foundation = _make_plan("foundation", "ForecasterFoundation")


@pytest.mark.parametrize(
    "refit, overridden, expected",
    [
        (False, ["fixed_train_size"], ["fixed_train_size"]),
        (0, ["fixed_train_size"], ["fixed_train_size"]),
        (False, ["refit", "fixed_train_size"], ["fixed_train_size"]),
        (False, ["refit", "gap"], []),
        (True, ["refit", "fixed_train_size"], []),
        (2, ["refit", "fixed_train_size"], []),
        (False, [], []),
    ],
    ids=[
        "refit_false",
        "refit_zero",
        "refit_false_keeps_refit",
        "refit_false_without_fixed_train_size",
        "refit_true",
        "refit_integer",
        "nothing_passed",
    ],
)
def test_cv_fields_without_effect_output_when_forecaster_is_trained(
    refit, overridden, expected
):
    """
    Test that for a trained forecaster only `fixed_train_size` is without
    effect, and only when `refit` is falsy (the model is trained once).
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=60, refit=refit)

    result = cv_fields_without_effect(overridden, cv, plan_recursive)

    assert result == expected


@pytest.mark.parametrize(
    "overridden",
    [["fixed_train_size"], ["refit", "fixed_train_size"], ["refit"], []],
    ids=["fixed_train_size", "both_passed", "refit_only", "nothing_passed"],
)
def test_cv_fields_without_effect_output_when_plan_is_none(overridden):
    """
    Test that a comparison (plan None) reports nothing as without effect:
    the effect depends on each candidate (a fixed window that does nothing
    for a forecaster trained once is the one ForecasterStats refits on).
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=60, refit=False)

    result = cv_fields_without_effect(overridden, cv, None)

    assert result == []


@pytest.mark.parametrize(
    "refit, fixed_train_size, overridden, expected",
    [
        (False, False, ["refit", "fixed_train_size"], ["refit", "fixed_train_size"]),
        (False, True, ["refit", "fixed_train_size"], ["refit", "fixed_train_size"]),
        (False, False, ["fixed_train_size", "refit"], ["fixed_train_size", "refit"]),
        (False, False, ["gap", "refit"], ["refit"]),
        (2, True, ["refit", "fixed_train_size"], ["refit"]),
        (3, False, ["refit", "fixed_train_size"], []),
        (3, False, ["refit"], []),
        (True, False, ["refit", "fixed_train_size"], []),
        (1, True, ["refit", "fixed_train_size"], ["refit"]),
        (False, False, [], []),
    ],
    ids=[
        "refit_false_expanding",
        "refit_false_fixed",
        "keeps_the_order_of_overridden",
        "ignores_names_not_passed",
        "refit_integer_fixed_window",
        "refit_integer_expanding_window",
        "refit_integer_alone",
        "refit_true_expanding_window",
        "refit_one_fixed_window",
        "nothing_passed",
    ],
)
def test_cv_fields_without_effect_output_when_forecaster_is_stats(
    refit, fixed_train_size, overridden, expected
):
    """
    Test that for ForecasterStats, which skforecast refits in every fold on
    a fixed window unless `refit` is truthy, a name is without effect when
    the strategy that runs is the same without it: `fixed_train_size` when
    `refit` is falsy, and `refit` when the window that runs is the fixed one
    anyway. A truthy `refit` with an expanding window does change what runs
    (the default runs a fixed one), in the order the names were passed.
    """
    cv = TimeSeriesFold(
        steps=10, initial_train_size=60, refit=refit,
        fixed_train_size=fixed_train_size,
    )

    result = cv_fields_without_effect(overridden, cv, plan_stats)

    assert result == expected


@pytest.mark.parametrize(
    "overridden, expected",
    [
        (["refit", "fixed_train_size"], ["refit", "fixed_train_size"]),
        (["fixed_train_size", "refit"], ["fixed_train_size", "refit"]),
        (["refit", "gap"], ["refit"]),
        (["initial_train_size", "gap"], []),
        ([], []),
    ],
    ids=["both", "both_other_order", "refit_and_gap", "others", "nothing_passed"],
)
def test_cv_fields_without_effect_output_when_plan_is_foundation(
    overridden, expected
):
    """
    Test that for a foundation plan (the model is not trained) `refit` and
    `fixed_train_size` are without effect whatever their value.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=60, refit=True)

    result = cv_fields_without_effect(overridden, cv, plan_foundation)

    assert result == expected
