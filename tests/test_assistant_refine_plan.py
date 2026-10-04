# Unit test refine_plan ForecastingAssistant

import re
import warnings

import numpy as np
import pandas as pd
import pytest
from skforecast.exceptions import MissingValuesWarning

from skforecast_ai import ForecastingAssistant
from skforecast_ai.exceptions import (
    InvalidInputError,
    PlanEditsDiscardedWarning,
    UnrecommendedForecasterWarning,
)
from skforecast_ai.schemas import ForecastPlan

from tests.fixtures_assistant import df_hourly, df_single, df_with_missing


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_refine_plan_ValueError_when_invalid_override_key():
    """
    Test that refine_plan() raises ValueError when an unsupported
    override key is passed.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "Invalid override keys: ['not_a_valid_key']. "
        "Allowed keys: ['calendar_features', 'differentiation', 'dropna_from_series', 'estimator', 'estimator_kwargs', 'forecaster', 'interval', 'lags', 'metric', 'steps', 'target_transformer', 'use_exog', 'window_features']."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.refine_plan(profile, plan, not_a_valid_key="something")


def test_refine_plan_ValueError_when_lags_exceed_data_budget():
    """
    Test that explicit lags spanning more than the allowed fraction of the
    available observations raise ValueError before building the plan.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    # 100 observations -> budget is int(100 * 0.33) = 33.
    with pytest.raises(ValueError, match=re.escape("exceeding the maximum")):
        assistant.refine_plan(profile, plan, lags=50)


def test_refine_plan_ValueError_when_lags_duplicated():
    """
    Test that an explicit lags override with duplicated values raises
    ValueError before the plan is rebuilt.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape("`lags` must not contain duplicates, got [2, 2].")
    with pytest.raises(ValueError, match=err_msg):
        assistant.refine_plan(profile, plan, lags=[2, 2])


def test_refine_plan_output_when_lags_within_budget():
    """
    Test that an explicit lag override within the data budget is applied.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan, lags=[1, 2, 7])

    assert refined.forecaster_kwargs["lags"] == [1, 2, 7]


def test_refine_plan_ValueError_when_forecaster_not_in_candidates():
    """
    Test that refine_plan() raises ValueError when the overridden
    forecaster is not in the profile's candidate list.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "Forecaster 'ForecasterRnn' is not compatible with this profile."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.refine_plan(profile, plan, forecaster="ForecasterRnn")


# =============================================================================
# Tests: basic output
# =============================================================================
def test_refine_plan_output_when_no_overrides():
    """
    Test that refine_plan() with no overrides returns a plan equivalent
    to the original (same key parameters).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan)

    assert refined.steps == plan.steps
    assert refined.forecaster == plan.forecaster
    assert refined.estimator == plan.estimator
    assert refined.interval == plan.interval
    assert refined.task_type == plan.task_type


def test_refine_plan_output_when_steps_overridden():
    """
    Test that refine_plan() returns a new plan with the overridden steps
    while preserving the original plan's forecaster and estimator.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan, steps=24)

    assert isinstance(refined, ForecastPlan)
    assert refined.steps == 24
    assert refined.forecaster == plan.forecaster
    assert refined.estimator == plan.estimator


# =============================================================================
# Tests: feature-rich (individual overrides)
# =============================================================================
def test_refine_plan_output_when_forecaster_overridden():
    """
    Test that refine_plan() applies a forecaster override and re-derives
    the plan accordingly.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan, forecaster="ForecasterDirect")

    assert refined.forecaster == "ForecasterDirect"
    assert refined.steps == plan.steps
    assert refined.task_type == "single_series"


def test_refine_plan_output_when_estimator_overridden():
    """
    Test that refine_plan() applies an estimator override.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan, estimator="RandomForestRegressor")

    assert refined.estimator == "RandomForestRegressor"
    assert refined.forecaster == plan.forecaster
    assert refined.steps == plan.steps


def test_refine_plan_output_when_estimator_kwargs_overridden():
    """
    Test that refine_plan() applies estimator_kwargs override.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    custom_kwargs = {"alpha": 2.0, "fit_intercept": False}
    refined = assistant.refine_plan(profile, plan, estimator_kwargs=custom_kwargs)

    assert refined.estimator_kwargs == custom_kwargs


def test_refine_plan_output_when_interval_added():
    """
    Test that refine_plan() adds prediction intervals to a plan that
    previously had none.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    assert plan.interval is None

    refined = assistant.refine_plan(profile, plan, interval=[0.1, 0.9])

    assert refined.interval == [0.1, 0.9]
    assert refined.interval_method == "bootstrapping"


def test_refine_plan_output_when_interval_removed():
    """
    Test that refine_plan() removes prediction intervals when
    interval=None is explicitly passed.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, interval=[0.1, 0.9])

    assert plan.interval == [0.1, 0.9]

    refined = assistant.refine_plan(profile, plan, interval=None)

    assert refined.interval is None
    assert refined.interval_method is None


# =============================================================================
# Tests: edge cases (multiple overrides, preserved state)
# =============================================================================
def test_refine_plan_output_when_multiple_overrides():
    """
    Test that refine_plan() applies multiple overrides simultaneously.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(
        profile, plan,
        steps=30,
        estimator="XGBRegressor",
        interval=[0.2, 0.8],
    )

    assert refined.steps == 30
    assert refined.estimator == "XGBRegressor"
    assert refined.interval == [0.2, 0.8]
    assert refined.interval_method == "bootstrapping"


def test_refine_plan_preserves_custom_forecaster_when_other_fields_refined():
    """
    Test that when the original plan was created with a custom forecaster,
    refine_plan() preserves it even when other fields are overridden.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterDirect"
    )

    refined = assistant.refine_plan(profile, plan, steps=24, interval=[0.05, 0.95])

    assert refined.forecaster == "ForecasterDirect"
    assert refined.steps == 24
    assert refined.interval == [0.05, 0.95]


def test_refine_plan_output_resets_end_train():
    """
    Test that refine_plan() does not carry the `end_train` split boundary
    over to the refined plan. The boundary was derived from the original
    horizon and test size, so keeping it would make a refined plan run in
    evaluation mode (and fail when the new horizon exceeds the test set)
    instead of forecasting the future.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10).model_copy(
        update={"end_train": "2023-03-01"}
    )

    refined = assistant.refine_plan(profile, plan, steps=5)

    assert refined.end_train is None
    assert refined.steps == 5


def test_refine_plan_output_preserves_llm_refined_fields_when_not_overridden():
    """
    Test that an LLM mark on the original plan survives a deterministic
    refinement of an unrelated field, since the marked value itself is
    carried over from `plan.forecaster_kwargs`, and that the mark is
    dropped once the field is overridden explicitly.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10).model_copy(
        update={"llm_refined_fields": ["lags"]}
    )

    refined_unrelated = assistant.refine_plan(
        profile, plan, estimator_kwargs={"alpha": 0.5}
    )
    refined_lags = assistant.refine_plan(profile, plan, lags=[1, 2])

    assert refined_unrelated.llm_refined_fields == ["lags"]
    assert refined_unrelated.forecaster_kwargs["lags"] == plan.forecaster_kwargs["lags"]
    assert refined_lags.llm_refined_fields == []


def test_refine_plan_output_drops_llm_mark_when_value_is_not_carried_over():
    """
    Test that an LLM mark is dropped when the refinement switches to a
    forecaster family that has no lags, and stays dropped when a later
    refinement switches back and re-derives the lags deterministically.
    Otherwise PACF-derived lags would be displayed as LLM-suggested.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10).model_copy(
        update={"llm_refined_fields": ["lags"]}
    )

    statistical = assistant.refine_plan(profile, plan, forecaster="ForecasterStats")
    recursive = assistant.refine_plan(
        profile, statistical, forecaster="ForecasterRecursive"
    )

    assert statistical.llm_refined_fields == []
    assert recursive.llm_refined_fields == []


def test_refine_plan_output_when_switching_to_and_from_baseline():
    """
    Test that refine_plan() can switch a plan to the baseline, which drops
    the estimator and the features, and back to an ML forecaster, which
    re-derives them deterministically.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    baseline = assistant.refine_plan(
        profile, plan, forecaster="ForecasterEquivalentDate"
    )
    recursive = assistant.refine_plan(
        profile, baseline, forecaster="ForecasterRecursive"
    )

    assert baseline.task_type == "baseline"
    assert baseline.forecaster_kwargs == {"offset": 7, "n_offsets": 1}
    assert baseline.estimator is None
    assert recursive.task_type == "single_series"
    assert recursive.forecaster_kwargs["lags"] == plan.forecaster_kwargs["lags"]


def test_refine_plan_output_does_not_carry_estimator_across_families():
    """
    Test that switching an ML plan to ForecasterStats re-derives the
    statistical estimator instead of carrying the ML regressor over, and
    that switching back re-derives the ML estimator of the profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    statistical = assistant.refine_plan(profile, plan, forecaster="ForecasterStats")
    recursive = assistant.refine_plan(
        profile, statistical, forecaster="ForecasterRecursive"
    )

    assert plan.estimator == "Ridge"
    assert statistical.estimator == "Arima"
    assert statistical.forecaster_kwargs == {}
    assert recursive.estimator == "Ridge"
    assert recursive.forecaster_kwargs["lags"] == plan.forecaster_kwargs["lags"]


def test_refine_plan_output_keeps_estimator_within_ml_forecasters():
    """
    Test that switching between ML forecasters keeps the estimator, its
    kwargs and the lags of the plan.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile,
        steps=10,
        estimator="Ridge",
        estimator_kwargs={"alpha": 2.0},
        lags=[1, 2, 7],
    )

    direct = assistant.refine_plan(profile, plan, forecaster="ForecasterDirect")

    assert direct.estimator == "Ridge"
    assert direct.estimator_kwargs == {"alpha": 2.0}
    assert direct.forecaster_kwargs["lags"] == [1, 2, 7]


@pytest.mark.parametrize(
    "forecaster, estimator, estimator_kwargs, new_estimator, new_kwargs",
    [
        (
            "ForecasterRecursive",
            "Ridge",
            {"alpha": 2.0},
            "LGBMRegressor",
            {"n_estimators": 50},
        ),
        (
            "ForecasterFoundation",
            "autogluon/chronos-2-small",
            {"cross_learning": True},
            "google/timesfm-3.0-pytorch",
            {"context_length": 1024},
        ),
    ],
    ids=lambda dt: (
        f"forecaster, estimator, estimator_kwargs, new_estimator, new_kwargs: {dt}"
    ),
)
def test_refine_plan_output_drops_estimator_kwargs_when_estimator_changes(
    forecaster, estimator, estimator_kwargs, new_estimator, new_kwargs
):
    """
    Test that changing the estimator drops the kwargs written for the
    previous one (a Chronos-2 `cross_learning` would make TimesFM fail),
    while refining another field keeps them and new kwargs passed with the
    new estimator are applied.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile,
        steps            = 10,
        forecaster       = forecaster,
        estimator        = estimator,
        estimator_kwargs = estimator_kwargs,
    )

    same_estimator = assistant.refine_plan(profile, plan, steps=5)
    new = assistant.refine_plan(profile, plan, estimator=new_estimator)
    new_with_kwargs = assistant.refine_plan(
        profile, plan, estimator=new_estimator, estimator_kwargs=new_kwargs
    )

    assert same_estimator.estimator_kwargs == estimator_kwargs
    assert new.estimator == new_estimator
    assert new.estimator_kwargs == {}
    assert new_with_kwargs.estimator_kwargs == new_kwargs


def test_refine_plan_ValueError_when_statistical_with_explicit_lags():
    """
    Test that an explicit lags override is not silently dropped when the
    plan is switched to ForecasterStats: plan() rejects it.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "'ForecasterStats' models the past values itself: it takes no lag or "
        "window features, so ['lags'] cannot be applied. Omit them."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.refine_plan(profile, plan, forecaster="ForecasterStats", lags=7)


def test_refine_plan_ValueError_when_baseline_with_explicit_lags():
    """
    Test that an explicit lags override is not silently dropped when the
    plan is switched to the baseline: plan() rejects it.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    with pytest.raises(ValueError, match=re.escape("so ['lags'] cannot be applied")):
        assistant.refine_plan(
            profile, plan, forecaster="ForecasterEquivalentDate", lags=7
        )


# =============================================================================
# Tests: error code and field
# =============================================================================
def test_refine_plan_InvalidInputError_field_when_invalid_override_key():
    """
    Test that unknown override keys raise InvalidInputError with the first
    unknown key, in alphabetical order, as field.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    err_msg = re.escape(
        "Invalid override keys: ['lagz', 'stepz']. Allowed keys: "
        "['calendar_features', 'differentiation', 'dropna_from_series', "
        "'estimator', 'estimator_kwargs', 'forecaster', 'interval', 'lags', "
        "'metric', 'steps', 'target_transformer', 'use_exog', "
        "'window_features']."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.refine_plan(profile, plan, stepz=3, lagz=2)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "lagz"


def test_refine_plan_warnings_are_those_of_the_rebuilt_plan():
    """
    Test that the refined plan keeps in `warnings` the warnings emitted by
    the `plan()` call that rebuilds it: refining an unrecommended
    forecaster warns again and keeps that warning, while overriding it
    with a recommended forecaster leaves the list empty.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_hourly, target="sales", date_column="date")
    with pytest.warns(UnrecommendedForecasterWarning):
        plan = assistant.plan(profile, steps=10, forecaster="ForecasterStats")

    with pytest.warns(UnrecommendedForecasterWarning) as record:
        refined = assistant.refine_plan(profile, plan, steps=12)

    assert refined.warnings == plan.warnings
    assert refined.warnings == [str(w.message) for w in record]

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        recommended = assistant.refine_plan(
            profile, plan, forecaster="ForecasterRecursive"
        )

    assert recommended.warnings == []


# =============================================================================
# Tests: overridden_fields and discarded edits
# =============================================================================
def test_refine_plan_output_overridden_fields_kept_while_value_is_kept():
    """
    Test that the decisions of the user are kept in `overridden_fields`
    while the refined plan holds their values, that a key passed in the
    call is added (unless it is None, which asks for the rule), and that a
    decision whose value is not carried over (lags with ForecasterStats)
    is dropped.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, lags=[1, 2, 7], estimator="Ridge")

    steps = assistant.refine_plan(profile, plan, steps=12)
    kwargs = assistant.refine_plan(profile, plan, estimator_kwargs={"alpha": 0.5})
    reset = assistant.refine_plan(profile, plan, lags=None)
    stats = assistant.refine_plan(profile, plan, forecaster="ForecasterStats")

    assert plan.overridden_fields == ["estimator", "lags"]
    assert steps.overridden_fields == ["estimator", "lags"]
    assert kwargs.overridden_fields == ["estimator", "estimator_kwargs", "lags"]
    assert reset.overridden_fields == ["estimator"]
    assert stats.overridden_fields == ["forecaster"]


def test_refine_plan_output_does_not_mark_carried_values_as_overridden():
    """
    Test that the values `refine_plan()` passes to `plan()` from a
    deterministic plan (forecaster, estimator, lags) are not recorded as
    decisions of the user.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    refined = assistant.refine_plan(profile, plan, steps=12)

    assert plan.overridden_fields == []
    assert refined.overridden_fields == []


def test_refine_plan_PlanEditsDiscardedWarning_when_plan_edited_by_hand():
    """
    Test that values of the plan edited by hand, which `plan()` does not
    rebuild, are named in a `PlanEditsDiscardedWarning` also kept in the
    warnings of the refined plan, and that the refined plan holds the
    values `plan()` builds.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    edited = plan.model_copy(
        update={
            "metric": "mean_squared_error",
            "forecaster_kwargs": {**plan.forecaster_kwargs, "differentiation": 1},
        },
        deep=True,
    )

    expected = (
        "refine_plan() rebuilds the plan with plan(), so these values of the "
        "plan, which differ from what plan() builds for it, were discarded: "
        "['metric', \"forecaster_kwargs['differentiation']\"]. Pass the ones "
        "that `refine_plan()` accepts (['calendar_features', "
        "'differentiation', 'dropna_from_series', 'estimator', "
        "'estimator_kwargs', 'forecaster', 'interval', 'lags', 'metric', "
        "'steps', 'target_transformer', 'use_exog', 'window_features']) as "
        "overrides to keep them."
    )
    with pytest.warns(PlanEditsDiscardedWarning, match=re.escape(expected)):
        refined = assistant.refine_plan(profile, edited, steps=12)

    assert refined.warnings == [expected]
    assert refined.metric == plan.metric
    assert "differentiation" not in refined.forecaster_kwargs


def test_refine_plan_no_warning_when_edit_is_replaced_by_an_override():
    """
    Test that a value edited by hand and passed again as an override of the
    call is not reported as discarded, and that the end_train split, the
    explanation, the warnings and the marks are not compared.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    edited = plan.model_copy(
        update={
            "forecaster_kwargs": {**plan.forecaster_kwargs, "lags": [1, 3]},
            "end_train": "2023-03-01",
            "explanation": "Edited.",
            "warnings": ["Edited."],
            "llm_refined_fields": ["window_features"],
        },
        deep=True,
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        refined = assistant.refine_plan(profile, edited, lags=[1, 2])

    assert refined.forecaster_kwargs["lags"] == [1, 2]
    assert refined.warnings == []


def test_refine_plan_PlanEditsDiscardedWarning_when_plan_cannot_be_rebuilt():
    """
    Test that, when `plan()` rejects the values of the plan, the comparison
    runs again with the overrides of the call (here `lags`, which replace
    lags too long for the data), and that when it cannot run at all (a
    forecaster that does not fit the data, replaced in the call) the
    warning says that edits may have been lost.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)
    long_lags = plan.model_copy(
        update={
            "metric": "mean_squared_error",
            "forecaster_kwargs": {**plan.forecaster_kwargs, "lags": [60]},
        },
        deep=True,
    )
    multi_series = plan.model_copy(
        update={
            "task_type": "multi_series",
            "forecaster": "ForecasterRecursiveMultiSeries",
        },
    )

    with pytest.warns(PlanEditsDiscardedWarning, match=re.escape("['metric']")):
        assistant.refine_plan(profile, long_lags, lags=[1, 2])

    expected = (
        "refine_plan() rebuilds the plan with plan(), which rejects the values "
        "of the plan for this profile, so values edited by hand in the plan "
        "may have been discarded without being compared."
    )
    with pytest.warns(PlanEditsDiscardedWarning, match=re.escape(expected)):
        refined = assistant.refine_plan(
            profile, multi_series, forecaster="ForecasterRecursive"
        )

    assert refined.warnings == [expected]


def test_refine_plan_output_metric_kept_only_when_chosen():
    """
    Test that a metric chosen by the user is kept by a refinement of
    another field and reset with `metric=None`, while a selected metric is
    selected again (MASE for several series would replace it).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    chosen = assistant.plan(profile, steps=10, metric=["mean_squared_error"])
    default = assistant.plan(profile, steps=10)

    kept = assistant.refine_plan(profile, chosen, steps=12)
    reset = assistant.refine_plan(profile, chosen, metric=None)
    changed = assistant.refine_plan(profile, default, metric="median_absolute_error")

    assert kept.metrics_to_compute == ["mean_squared_error"]
    assert kept.overridden_fields == ["metric"]
    assert reset.metrics_to_compute == default.metrics_to_compute
    assert reset.overridden_fields == []
    assert changed.metric == "median_absolute_error"
    assert changed.overridden_fields == ["metric"]


def test_refine_plan_output_use_exog_kept_only_when_it_applies():
    """
    Test that `use_exog=False` chosen by the user is kept by a refinement
    of another field and by a switch to the baseline, and that
    `use_exog=None` lets the rule decide again.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, use_exog=False)

    kept = assistant.refine_plan(profile, plan, steps=12)
    reset = assistant.refine_plan(profile, plan, use_exog=None)
    stats = assistant.refine_plan(profile, plan, forecaster="ForecasterStats")

    assert kept.use_exog is False
    assert kept.overridden_fields == ["use_exog"]
    assert reset.use_exog is True
    assert reset.overridden_fields == []
    assert stats.use_exog is False
    assert stats.overridden_fields == ["forecaster", "use_exog"]


def test_refine_plan_output_use_exog_true_not_carried_to_the_baseline():
    """
    Test that `use_exog=True` chosen by the user is not carried over to the
    baseline, which cannot use exogenous variables, and comes back when a
    later refinement does not need it (the rule decides again).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, use_exog=True)

    baseline = assistant.refine_plan(
        profile, plan, forecaster="ForecasterEquivalentDate"
    )

    assert baseline.use_exog is False
    assert baseline.overridden_fields == ["forecaster"]


def test_refine_plan_output_differentiation_kept_while_it_applies():
    """
    Test that a differentiation order chosen by the user is kept by a
    refinement of another field, dropped (with its mark) by a switch to
    ForecasterStats and removed with `differentiation=None`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, differentiation=1)

    kept = assistant.refine_plan(profile, plan, forecaster="ForecasterDirect")
    stats = assistant.refine_plan(profile, plan, forecaster="ForecasterStats")
    removed = assistant.refine_plan(profile, plan, differentiation=None)

    assert kept.forecaster_kwargs["differentiation"] == 1
    assert kept.overridden_fields == ["forecaster", "differentiation"]
    assert stats.forecaster_kwargs == {}
    assert stats.overridden_fields == ["forecaster"]
    assert "differentiation" not in removed.forecaster_kwargs
    assert removed.overridden_fields == []


def test_refine_plan_output_feature_overrides_kept_while_they_apply():
    """
    Test that chosen calendar features, scaling and NaN handling are kept
    by a refinement of another field and dropped by a switch to
    ForecasterStats, which takes none of them.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, calendar_features=[], target_transformer="none",
        dropna_from_series=True,
    )

    kept = assistant.refine_plan(profile, plan, steps=12)
    stats = assistant.refine_plan(profile, plan, forecaster="ForecasterStats")

    assert kept.forecaster_kwargs["calendar_features"] is None
    assert "transformer_y" not in kept.forecaster_kwargs
    assert kept.forecaster_kwargs["dropna_from_series"] is True
    assert kept.overridden_fields == [
        "calendar_features", "target_transformer", "dropna_from_series"
    ]
    assert stats.overridden_fields == ["forecaster"]


def test_refine_plan_ValueError_names_a_carried_decision_that_no_longer_applies():
    """
    Test that a decision of the user carried over from the plan that the
    refined plan rejects (`dropna_from_series=False` once the estimator
    does not accept missing values) raises saying it was carried over and
    how to clear it, and that passing None lets the rule decide.
    """
    assistant = ForecastingAssistant()
    with pytest.warns(MissingValuesWarning):
        profile = assistant.profile(
            data=df_with_missing, target="sales", date_column="date"
        )
    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor", dropna_from_series=False
    )

    err_msg = re.escape(
        "`dropna_from_series` was carried over from the plan, where the user "
        "chose it (`plan.overridden_fields`); pass `dropna_from_series=None` "
        "to let the rule decide."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as info:
        assistant.refine_plan(profile, plan, estimator="Ridge")
    refined = assistant.refine_plan(
        profile, plan, estimator="Ridge", dropna_from_series=None
    )

    assert info.value.field == "dropna_from_series"
    assert refined.forecaster_kwargs["dropna_from_series"] is True


def test_refine_plan_output_differentiation_chooses_default_windows_again():
    """
    Test that a differentiation order passed to refine_plan() gives the plan
    that plan() builds with it: the lags and window features the rules chose
    are chosen again with room for the order (on 100 weekly observations the
    default window of 33 takes the whole budget), instead of being carried
    over and rejected. Lags the user chose are kept.
    """
    assistant = ForecastingAssistant()
    data = pd.DataFrame({
        "date": pd.date_range("2020-01-05", periods=100, freq="W"),
        "y": np.arange(100, dtype=float),
    })
    profile = assistant.profile(data=data, target="y", date_column="date")
    default_plan = assistant.plan(profile, steps=4)
    chosen_lags = assistant.plan(profile, steps=4, lags=5)

    refined = assistant.refine_plan(profile, default_plan, differentiation=1)
    refined_lags = assistant.refine_plan(profile, chosen_lags, differentiation=1)

    assert refined == assistant.plan(profile, steps=4, differentiation=1)
    assert refined_lags.forecaster_kwargs["lags"] == 5
    assert refined_lags.overridden_fields == ["lags", "differentiation"]


def test_refine_plan_PlanEditsDiscardedWarning_when_exog_columns_edited_by_hand():
    """
    Test that `exog_columns` of a plan edited by hand, which refine_plan()
    takes again from the profile, is named in the warning of discarded
    edits, and that a plan left as built does not warn.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data         = df_single.assign(extra=1.0),
        target       = "sales",
        date_column  = "date",
        exog_columns = ["promo"],
    )
    plan = assistant.plan(profile, steps=5)
    edited = plan.model_copy(update={"exog_columns": ["promo", "extra"]})

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        kept = assistant.refine_plan(profile, plan, lags=3)
    with pytest.warns(PlanEditsDiscardedWarning, match="exog_columns"):
        refined = assistant.refine_plan(profile, edited, lags=3)

    assert kept.exog_columns == ["promo"]
    assert refined.exog_columns == ["promo"]
