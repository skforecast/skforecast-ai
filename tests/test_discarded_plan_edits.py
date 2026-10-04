# Unit test discarded_plan_edits

from skforecast_ai._utils import discarded_plan_edits
from skforecast_ai.schemas import ForecastPlan, PreprocessingStep

PLAN = ForecastPlan(
    task_type         = "single_series",
    forecaster        = "ForecasterRecursive",
    forecaster_kwargs = {"lags": [1, 2], "dropna_from_series": False},
    estimator         = "Ridge",
    steps             = 5,
    frequency         = "D",
    explanation       = "Plan.",
)


def test_discarded_plan_edits_empty_when_plans_equal_but_for_ignored_fields():
    """
    Test that the split boundary, the explanation, the warnings and the
    marks are not compared.
    """
    edited = PLAN.model_copy(update={
        "end_train": "2023-01-01",
        "explanation": "Other.",
        "warnings": ["Other."],
        "llm_refined_fields": ["lags"],
        "overridden_fields": ["lags"],
    })

    assert discarded_plan_edits(edited, PLAN, set()) == []


def test_discarded_plan_edits_names_fields_and_forecaster_kwargs():
    """
    Test that fields and keys of `forecaster_kwargs` that differ are named
    in a fixed order, including the preprocessing steps: a key the rebuilt
    plan drops counts, a key only the rebuilt plan has does not.
    """
    step = PreprocessingStep(
        action="note", reason="Edited.", code_snippet="", blocking=False
    )
    edited = PLAN.model_copy(update={
        "metric": "mean_squared_error",
        "preprocessing_steps": [step],
        "forecaster_kwargs": {"lags": [1, 2], "differentiation": 1},
    })

    assert discarded_plan_edits(edited, PLAN, set()) == [
        "metric",
        "preprocessing_steps",
        "forecaster_kwargs['differentiation']",
    ]


def test_discarded_plan_edits_skips_fields_overridden_in_the_call():
    """
    Test that a field the call overrides is not reported, also when the
    override sets several fields (`interval` sets `interval_method`).
    """
    edited = PLAN.model_copy(update={
        "estimator": "LGBMRegressor",
        "interval_method": "conformal",
        "forecaster_kwargs": {"lags": [1, 3], "dropna_from_series": False},
    })

    assert discarded_plan_edits(edited, PLAN, {"estimator", "interval", "lags"}) == []
    assert discarded_plan_edits(edited, PLAN, set()) == [
        "estimator", "interval_method", "forecaster_kwargs['lags']"
    ]


def test_discarded_plan_edits_skips_the_metric_when_overridden():
    """
    Test that the metric and the metrics computed are not reported when
    the call overrides `metric`.
    """
    edited = PLAN.model_copy(update={
        "metric": "mean_squared_error",
        "metrics_to_compute": ["mean_squared_error"],
    })

    assert discarded_plan_edits(edited, PLAN, {"metric"}) == []
    assert discarded_plan_edits(edited, PLAN, set()) == [
        "metric", "metrics_to_compute"
    ]
