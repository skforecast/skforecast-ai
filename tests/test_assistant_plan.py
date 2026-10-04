# Unit test plan ForecastingAssistant

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import MissingValuesWarning

from skforecast_ai import ForecastingAssistant
from skforecast_ai.exceptions import (
    InvalidInputError,
    InvalidInputTypeError,
    UnrecommendedForecasterWarning,
)
from skforecast_ai.schemas import ForecastPlan

from tests.fixtures_assistant import (
    df_all_calendar_named_exog,
    df_calendar_named_exog,
    df_categorical_exog,
    df_hourly,
    df_irregular,
    df_multi_long,
    df_multi_wide,
    df_no_exog,
    df_range_index,
    df_single,
    df_with_missing,
)


# =============================================================================
# Tests: error / validation
# =============================================================================
def test_plan_ValueError_when_forecaster_not_in_candidates():
    """
    Test that plan() raises ValueError when the specified
    forecaster is not in the profile's candidate list.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        "Forecaster 'ForecasterRnn' is not compatible with this profile."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(profile, steps=10, forecaster="ForecasterRnn")


def test_plan_UnrecommendedForecasterWarning_when_forecaster_not_recommended():
    """
    Test that plan() warns, but still uses the requested forecaster, when
    it is supported yet not among the profile candidates. ForecasterStats
    is excluded from the candidates for hourly data because Auto-ARIMA
    with a seasonal period of 24 is impractically slow.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_hourly, target="sales", date_column="date")

    assert "ForecasterStats" not in profile.forecaster_candidates

    warn_msg = re.escape(
        "Forecaster 'ForecasterStats' is not among the recommended candidates"
    )
    with pytest.warns(UnrecommendedForecasterWarning, match=warn_msg):
        plan = assistant.plan(profile, steps=10, forecaster="ForecasterStats")

    assert plan.forecaster == "ForecasterStats"


@pytest.mark.parametrize(
    "lags, match",
    [
        (0, "must be positive integers"),
        ([], "must not be an empty list"),
        ([0, 1], "must be positive integers"),
        (True, "must be an int or a list of ints"),
        ([1.5], "must contain ints only"),
        ([1, "3"], "must contain ints only"),
        ([2, 2], "must not contain duplicates"),
    ],
    ids=lambda value: f"{value!r}",
)
def test_plan_ValueError_when_lags_invalid(lags, match):
    """
    Test that plan() rejects an explicit lags override that skforecast
    would either reject later or accept silently (an empty list trains
    without lags, duplicates produce repeated features) with a ValueError
    raised before the plan is built.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(ValueError, match=match):
        assistant.plan(profile, steps=10, lags=lags)


@pytest.mark.parametrize(
    "steps",
    [0, True, "12", 12.5],
    ids=lambda steps: f"steps: {steps!r}",
)
def test_plan_ValueError_when_steps_not_positive_integer(steps):
    """
    Test that plan() rejects a horizon that is not an integer greater than
    or equal to 1 before deriving the plan, instead of coercing a bool to a
    one-step plan or failing later.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        f"`steps` must be an integer greater than or equal to 1, got {steps!r}."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(profile, steps=steps)


def test_plan_ValueError_when_window_features_duplicate_pairs():
    """
    Test that plan() rejects explicit window_features that pair the same
    statistic with the same window size in two entries, which
    RollingFeatures would reject when the generated script runs.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        "`window_features` contains duplicate (stat, window_size) pairs: "
        "[('mean', 7)]. Merge the entries or change the window size."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(
            profile,
            steps=10,
            window_features=[
                {"stats": ["mean"], "window_size": 7},
                {"stats": ["mean", "std"], "window_size": 7},
            ],
        )


# =============================================================================
# Tests: basic output
# =============================================================================
def test_plan_output_when_single_series():
    """
    Test that plan() returns a ForecastPlan with correct task_type
    and steps for a single-series profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    assert isinstance(plan, ForecastPlan)
    assert plan.steps == 10
    assert plan.task_type == "single_series"
    assert plan.forecaster == profile.forecaster


def test_plan_output_when_steps_is_integral_float():
    """
    Test that plan() accepts an integral float horizon with a direct
    forecaster and stores it as an int, in the plan and in the forecaster
    arguments.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    plan = assistant.plan(profile, steps=12.0, forecaster="ForecasterDirect")

    assert plan.steps == 12
    assert type(plan.steps) is int
    assert plan.forecaster_kwargs["steps"] == 12
    assert type(plan.forecaster_kwargs["steps"]) is int


def test_plan_output_when_forecaster_override():
    """
    Test that plan() honors an explicit forecaster override.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterDirect"
    )

    assert plan.forecaster == "ForecasterDirect"
    assert plan.task_type == "single_series"


@pytest.mark.parametrize(
    "estimator, expected_calendar, expected_skipped",
    [
        (
            None,
            {"features": ["day_of_week", "month"], "encoding": "cyclical"},
            "['weekend']",
        ),
        (
            "LGBMRegressor",
            {"features": ["day_of_week"], "encoding": None},
            "['weekend', 'month']",
        ),
    ],
    ids=["Ridge, cyclical encoding", "LGBMRegressor, raw encoding"],
)
def test_plan_output_when_calendar_features_collide_with_exog(
    estimator, expected_calendar, expected_skipped
):
    """
    Test that plan() leaves out the calendar features whose columns already
    exist as exogenous columns and says so in the explanation. The columns
    depend on the encoding: with cyclical encoding 'month' creates
    'month_sin' and 'month_cos' and is kept, while 'weekend' is never
    encoded and collides with either estimator.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_calendar_named_exog, target="sales", date_column="date"
    )
    plan = assistant.plan(profile, steps=10, estimator=estimator)

    assert plan.forecaster_kwargs["calendar_features"] == expected_calendar
    assert (
        f"Calendar features {expected_skipped} skipped: the exogenous "
        f"variables already have columns with the names they would create, "
        f"and those columns are used instead."
    ) in plan.explanation


def test_plan_output_when_every_calendar_feature_collides_with_exog():
    """
    Test that plan() sets no calendar features when all of them collide
    with exogenous columns, and the explanation names them as skipped.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_all_calendar_named_exog, target="sales", date_column="date"
    )
    plan = assistant.plan(profile, steps=10, estimator="LGBMRegressor")

    assert plan.forecaster_kwargs["calendar_features"] is None
    assert "Calendar features: [" not in plan.explanation
    assert (
        "Calendar features ['day_of_week', 'weekend', 'month'] skipped:"
    ) in plan.explanation


def test_plan_output_when_multi_series():
    """
    Test that plan() produces a multi_series plan from a
    multi-series profile.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.plan(profile, steps=5)

    assert plan.task_type == "multi_series"
    assert plan.forecaster == "ForecasterRecursiveMultiSeries"


# =============================================================================
# Tests: feature-rich (intervals, kwargs, statistical/foundation)
# =============================================================================
def test_plan_output_when_interval_bootstrapping():
    """
    Test that plan() sets interval_method='bootstrapping' for ML
    forecasters when interval is provided.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10, interval=[0.1, 0.9])

    assert plan.interval == [0.1, 0.9]
    assert plan.interval_method == "bootstrapping"


def test_plan_output_when_interval_native_for_statistical():
    """
    Test that plan() sets interval_method='native' for
    ForecasterStats when interval is provided.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats", interval=[0.1, 0.9]
    )

    assert plan.interval == [0.1, 0.9]
    assert plan.interval_method == "native"
    assert plan.task_type == "statistical"


def test_plan_output_when_statistical_has_no_lags():
    """
    Test that plan() sets lags, window_features, and transformers
    to None for statistical task types.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats"
    )

    assert plan.task_type == "statistical"
    assert "lags" not in plan.forecaster_kwargs or plan.forecaster_kwargs.get("lags") is None


def test_plan_output_when_foundation_forecaster():
    """
    Test that plan() assigns the default foundation model ID as estimator
    and empty forecaster_kwargs for a foundation forecaster override.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterFoundation"
    )

    assert plan.task_type == "foundation"
    assert plan.estimator == "autogluon/chronos-2-small"
    assert plan.estimator_kwargs == {}
    assert plan.forecaster_kwargs == {}
    assert plan.use_exog is True


@pytest.mark.parametrize(
    "data, profile_kwargs",
    [
        (
            df_multi_long,
            {"target": "value", "date_column": "date", "series_id_column": "series_id"},
        ),
        (
            df_multi_wide,
            {"target": ["series_a", "series_b"], "date_column": "date"},
        ),
    ],
    ids=["long", "wide"],
)
def test_plan_output_when_foundation_forecaster_with_multi_series(
    data, profile_kwargs
):
    """
    Test that plan() builds a ForecasterFoundation plan for multi-series data
    in long and wide format, without an UnrecommendedForecasterWarning since
    it is a candidate for several series, with the default model.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=data, **profile_kwargs)
    assert "ForecasterFoundation" in profile.forecaster_candidates

    with warnings.catch_warnings():
        warnings.simplefilter("error", UnrecommendedForecasterWarning)
        plan = assistant.plan(profile, steps=5, forecaster="ForecasterFoundation")

    assert plan.task_type == "foundation"
    assert plan.estimator == "autogluon/chronos-2-small"
    assert plan.forecaster_kwargs == {}
    assert plan.use_exog is False


def test_plan_output_when_foundation_model_id_given():
    """
    Test that plan() keeps an explicit foundation model ID as estimator, and
    that the explanation names the model and its non-commercial license.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile          = profile,
        steps            = 10,
        forecaster       = "ForecasterFoundation",
        estimator        = "google/timesfm-3.0-pytorch",
        estimator_kwargs = {"context_length": 1024},
        interval         = [0.1, 0.9],
    )

    assert plan.estimator == "google/timesfm-3.0-pytorch"
    assert plan.estimator_kwargs == {"context_length": 1024}
    assert plan.use_exog is True
    assert plan.explanation.startswith(
        "Plan: ForecasterFoundation + google/timesfm-3.0-pytorch."
    )
    assert (
        "The weights of 'google/timesfm-3.0-pytorch' are released under "
        "timesfm-non-commercial-license-v1.0, which restricts commercial use "
        "(https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE)."
    ) in plan.explanation


def test_plan_output_when_foundation_model_without_covariates():
    """
    Test that plan() does not use the exogenous variables with a foundation
    model that accepts no covariates, and says so in the explanation.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile    = profile,
        steps      = 10,
        forecaster = "ForecasterFoundation",
        estimator  = "Salesforce/moirai-2.0-R-small",
    )

    assert plan.use_exog is False
    assert "Exogenous variables included." not in plan.explanation
    assert (
        "Exogenous variables ['promo'] are not used: "
        "'Salesforce/moirai-2.0-R-small' does not support covariates."
    ) in plan.explanation


def test_plan_output_when_foundation_model_requires_numeric_covariates():
    """
    Test that plan() keeps the numeric exogenous variables and adds a
    non-blocking step that excludes the categorical ones when the foundation
    model only accepts numeric covariates.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_categorical_exog, target="sales", date_column="date"
    )
    plan = assistant.plan(
        profile    = profile,
        steps      = 10,
        forecaster = "ForecasterFoundation",
        estimator  = "google/timesfm-3.0-pytorch",
    )
    step = next(
        s for s in plan.preprocessing_steps
        if s.action == "handle_categorical_exog"
    )

    assert plan.use_exog is True
    assert step.blocking is False
    assert step.reason == (
        "Categorical exogenous variables detected: ['weekday']. "
        "'google/timesfm-3.0-pytorch' only accepts numeric covariates, so "
        "these columns are excluded. Encode them manually to include them."
    )


def test_plan_output_when_foundation_provider_requires_account():
    """
    Test that the explanation of a TabPFN plan says that its provider
    requires its own account, and that t0, no longer gated, gets no
    sentence about its weights.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile    = profile,
        steps      = 10,
        forecaster = "ForecasterFoundation",
        estimator  = "priorlabs/tabpfn-ts",
    )
    plan_t0 = assistant.plan(
        profile    = profile,
        steps      = 10,
        forecaster = "ForecasterFoundation",
        estimator  = "theforecastingcompany/t0-alpha",
    )

    assert (
        "The provider of 'priorlabs/tabpfn-ts' requires its own account and "
        "accepting its license, outside the Hugging Face Hub, before running "
        "the script."
    ) in plan.explanation
    assert "The weights of" not in plan_t0.explanation
    assert "provider" not in plan_t0.explanation


def test_plan_ValueError_when_foundation_model_not_supported():
    """
    Test that plan() rejects a foundation estimator that no skforecast
    adapter serves, including the former 'Chronos-2' label.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        "'Chronos-2' is not a foundation model supported by skforecast. "
        "Pass its Hugging Face model ID as `estimator`, for example "
        "'autogluon/chronos-2-small'."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(
            profile, steps=10, forecaster="ForecasterFoundation",
            estimator="Chronos-2",
        )


def test_plan_ValueError_when_foundation_model_id_in_estimator_kwargs():
    """
    Test that plan() rejects a model ID passed in `estimator_kwargs`, which
    would let the plan name one model and the script load another.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        "`estimator_kwargs` cannot contain 'model_id' for "
        "'ForecasterFoundation'. Pass the model ID as `estimator` instead, "
        "e.g. estimator='google/timesfm-3.0-pytorch'."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(
            profile, steps=10, forecaster="ForecasterFoundation",
            estimator_kwargs={"model_id": "google/timesfm-3.0-pytorch"},
        )


def test_plan_ValueError_when_foundation_model_cannot_predict_interval():
    """
    Test that plan() rejects an interval whose bounds are not in the
    quantile grid of the foundation model.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        "'google/timesfm-3.0-pytorch' (TimesFM3Adapter) only predicts the "
        "quantile levels [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9], so "
        "`interval` [0.05, 0.95] cannot be computed: [0.05, 0.95] not in "
        "that list."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(
            profile, steps=10, forecaster="ForecasterFoundation",
            estimator="google/timesfm-3.0-pytorch", interval=[0.05, 0.95],
        )


def test_plan_output_when_baseline_forecaster():
    """
    Test that plan() builds a seasonal naive ForecasterEquivalentDate plan
    without an UnrecommendedForecasterWarning: no estimator, no features,
    the offset from the daily frequency, and no exogenous variables.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5, forecaster="ForecasterEquivalentDate")

    assert plan.task_type == "baseline"
    assert plan.forecaster == "ForecasterEquivalentDate"
    assert plan.forecaster_kwargs == {"offset": 7, "n_offsets": 1}
    assert plan.estimator is None
    assert plan.use_exog is False
    assert plan.interval_method is None
    assert plan.explanation == (
        "Plan: ForecasterEquivalentDate. No lag or window features: the "
        "baseline repeats past values and learns nothing from the data. MAE "
        "is interpretable, robust to outliers, and works at any scale. "
        "Baseline: seasonal naive, each step repeats the value observed 7 "
        "steps earlier (one seasonal period). Exogenous variables ['promo'] "
        "are not used: the baseline only repeats past target values."
    )


def test_plan_output_when_baseline_with_interval():
    """
    Test that plan() selects conformal intervals for the baseline.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=5, forecaster="ForecasterEquivalentDate", interval=[0.1, 0.9]
    )

    assert plan.interval == [0.1, 0.9]
    assert plan.interval_method == "conformal"


@pytest.mark.parametrize(
    "kwargs, given",
    [
        ({"estimator": "Ridge"}, "['estimator']"),
        ({"estimator_kwargs": {"alpha": 1.0}}, "['estimator_kwargs']"),
        ({"lags": 7}, "['lags']"),
        (
            {"lags": 7, "window_features": [{"stats": ["mean"], "window_size": 7}]},
            "['lags', 'window_features']",
        ),
    ],
    ids=lambda dt: f"kwargs, given: {dt}",
)
def test_plan_ValueError_when_baseline_with_model_arguments(kwargs, given):
    """
    Test that plan() rejects an estimator, estimator kwargs, lags or window
    features for the baseline instead of silently ignoring them.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        f"'ForecasterEquivalentDate' is a baseline that repeats past values: "
        f"it has no estimator and no lag or window features, so {given} "
        f"cannot be applied. Omit them."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(
            profile, steps=5, forecaster="ForecasterEquivalentDate", **kwargs
        )


@pytest.mark.parametrize(
    "forecaster, kwargs, given",
    [
        ("ForecasterStats", {"lags": 7}, "['lags']"),
        (
            "ForecasterStats",
            {"window_features": [{"stats": ["mean"], "window_size": 7}]},
            "['window_features']",
        ),
        (
            "ForecasterFoundation",
            {"lags": 7, "window_features": [{"stats": ["mean"], "window_size": 7}]},
            "['lags', 'window_features']",
        ),
    ],
    ids=lambda dt: f"forecaster, kwargs, given: {dt}",
)
def test_plan_ValueError_when_forecaster_without_lags_given_features(
    forecaster, kwargs, given
):
    """
    Test that plan() rejects lags or window features for the statistical and
    foundation forecasters, which model the past values themselves, instead
    of silently ignoring them.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        f"'{forecaster}' models the past values itself: it takes no lag or "
        f"window features, so {given} cannot be applied. Omit them."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(profile, steps=5, forecaster=forecaster, **kwargs)


def test_plan_output_when_statistical_with_estimator_kwargs():
    """
    Test that plan() still accepts an estimator and its kwargs for the
    statistical forecaster, which uses them (only lags and window features
    are rejected).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    plan = assistant.plan(
        profile,
        steps=5,
        forecaster="ForecasterStats",
        estimator="Arima",
        estimator_kwargs={"order": [1, 0, 0]},
    )

    assert plan.estimator == "Arima"
    assert plan.estimator_kwargs == {"order": [1, 0, 0]}
    assert plan.forecaster_kwargs == {}


def test_plan_ValueError_when_baseline_with_multi_series():
    """
    Test that plan() rejects the baseline for multi-series data, since
    ForecasterEquivalentDate forecasts a single series.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )

    with pytest.raises(
        ValueError, match="Task type 'baseline' supports a single series only"
    ):
        assistant.plan(profile, steps=5, forecaster="ForecasterEquivalentDate")


def test_plan_UserWarning_when_baseline_with_missing_target():
    """
    Test that plan() warns when the baseline is built for a target with
    missing values, which it would repeat as missing predictions, and that
    the preprocessing step advises imputing the target.
    """
    assistant = ForecastingAssistant()
    with pytest.warns(MissingValuesWarning, match="pairwise deletion"):
        profile = assistant.profile(
            data=df_with_missing, target="sales", date_column="date"
        )

    warn_msg = re.escape(
        "'ForecasterEquivalentDate' cannot handle missing values: the target "
        "has missing values or missing timestamps, and "
        "ForecasterEquivalentDate repeats a missing value as a missing "
        "prediction. Impute the target before fitting, or the predictions "
        "and metrics will contain missing values."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        plan = assistant.plan(profile, steps=5, forecaster="ForecasterEquivalentDate")

    missing_steps = [
        step for step in plan.preprocessing_steps
        if step.action == "handle_missing_values"
    ]
    assert len(missing_steps) == 1
    assert missing_steps[0].reason == (
        "Impute the missing target values before training. "
        "ForecasterEquivalentDate repeats past values, so a missing value at "
        "an equivalent date becomes a missing prediction and the metrics "
        "cannot be computed."
    )


def test_plan_explanation_says_nothing_about_nan_when_no_missing_values():
    """
    Test that the plan explanation does not claim NaN rows are kept by a
    NaN-tolerant estimator when there is no missing value at all (Ridge is
    not NaN-tolerant), and that it still explains the NaN handling when
    there are missing values.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    with pytest.warns(MissingValuesWarning, match="pairwise deletion"):
        profile_missing = assistant.profile(
            data=df_with_missing, target="sales", date_column="date"
        )

    plan_ridge = assistant.plan(profile, steps=5, estimator="Ridge")
    plan_lgbm = assistant.plan(profile, steps=5, estimator="LGBMRegressor")
    plan_missing_ridge = assistant.plan(profile_missing, steps=5, estimator="Ridge")
    plan_missing_lgbm = assistant.plan(
        profile_missing, steps=5, estimator="LGBMRegressor"
    )

    assert "NaN" not in plan_ridge.explanation
    assert "NaN" not in plan_lgbm.explanation
    assert "NaN rows will be dropped before fitting." in plan_missing_ridge.explanation
    assert "NaN rows kept (NaN-tolerant estimator)." in plan_missing_lgbm.explanation


def test_plan_deterministic():
    """
    Test that plan() is deterministic: two identical calls produce
    equal plans.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan_1 = assistant.plan(profile, steps=10)
    plan_2 = assistant.plan(profile, steps=10)

    assert plan_1 == plan_2



def test_plan_output_when_estimator_kwargs_provided():
    """
    Test that plan() passes estimator_kwargs through to the plan.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    custom_kwargs = {"n_estimators": 200, "learning_rate": 0.05}
    plan = assistant.plan(
        profile, steps=10, estimator="LGBMRegressor",
        estimator_kwargs=custom_kwargs,
    )

    assert plan.estimator_kwargs == custom_kwargs


def test_plan_output_when_estimator_override():
    """
    Test that plan() uses the explicitly specified estimator.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, estimator="RandomForestRegressor"
    )

    assert plan.estimator == "RandomForestRegressor"


def test_plan_output_when_no_exog():
    """
    Test that plan() sets use_exog=False when no exogenous
    variables are present.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_no_exog, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    assert plan.use_exog is False


def test_plan_output_when_exog_present():
    """
    Test that plan() sets use_exog=True when exogenous variables
    are present in the data.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    assert plan.use_exog is True


# =============================================================================
# Tests: end_train
# =============================================================================
def test_plan_end_train_is_none():
    """
    Test that plan() always leaves end_train as None. The evaluation split
    boundary is a forecast-only concern resolved by forecast()/
    forecast_code() from their test_size argument, not by plan().
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    assert plan.end_train is None


def test_plan_ValueError_when_estimator_not_supported():
    """
    Test that plan() rejects an estimator the generated script cannot
    import, instead of rendering it and failing at execution.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape("'LightGBM' is not a supported estimator.")
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(profile, steps=10, estimator="LightGBM")


def test_plan_ValueError_when_estimator_kwargs_name_unknown():
    """
    Test that plan() rejects a misspelled keyword argument of the
    estimator, which would fail inside the script.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape("Ridge has no parameter 'alpah'. Did you mean 'alpha'?")
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(
            profile, steps=10, estimator="Ridge", estimator_kwargs={"alpah": 1.0}
        )


@pytest.mark.parametrize(
    "forecaster, interval, match",
    [
        (
            None,
            [5, 95],
            "`interval` must be `[lower, upper]` with 0 < lower < upper < 1, "
            "got [5, 95].",
        ),
        (
            "ForecasterEquivalentDate",
            [0.05, 0.9],
            "'ForecasterEquivalentDate' predicts symmetric intervals only",
        ),
    ],
    ids=["percentiles", "asymmetric conformal interval"],
)
def test_plan_ValueError_when_interval_invalid(forecaster, interval, match):
    """
    Test that plan() rejects an interval the forecaster cannot predict,
    instead of failing inside the executed script.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(ValueError, match=re.escape(match)):
        assistant.plan(profile, steps=10, forecaster=forecaster, interval=interval)


def test_plan_ValueError_when_datetime_index_has_no_frequency():
    """
    Test that plan() raises, also pointing at day-first dates, when the
    datetime index has no inferable frequency (irregular timestamps), since
    the script would fail inside skforecast. Day-first dates that a later
    date proves wrong are rejected earlier, by profile().
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_irregular, target="sales", date_column="date")

    err_msg = re.escape(
        "The frequency of the datetime index could not be inferred (the "
        "timestamps are irregular or too few), and 'ForecasterRecursive' needs "
        "a regular DatetimeIndex. Check the dates: day-first values such as "
        "'13/02/2023' are read month-first unless parsed explicitly, for "
        "example with pandas.to_datetime(..., dayfirst=True)."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(profile, steps=5)


# =============================================================================
# Tests: plans that cannot run
# =============================================================================
@pytest.mark.parametrize(
    "forecaster",
    ["ForecasterRecursiveMultiSeries", "ForecasterDirectMultiVariate"],
)
def test_plan_InvalidInputError_when_multi_series_forecaster_on_single_series(
    forecaster,
):
    """
    Test that plan() rejects a multi-series forecaster on data with a single
    series, with `forecaster` as field, instead of failing inside the script.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        f"{forecaster} forecasts several series, but the data has a single "
        f"series (target 'sales'). Use a single-series forecaster "
        f"(e.g. 'ForecasterRecursive'), or pass several series: a list of "
        f"target columns, or `series_id_column` for long format."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.plan(profile, steps=3, forecaster=forecaster)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "forecaster"


@pytest.mark.parametrize(
    "forecaster",
    ["ForecasterRecursiveMultiSeries", "ForecasterDirectMultiVariate"],
)
def test_plan_multi_series_forecaster_when_wide_data_has_several_series(forecaster):
    """
    Test that plan() still builds a multi-series plan on wide data with
    several series.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_wide, target=["series_a", "series_b"], date_column="date"
    )

    plan = assistant.plan(profile, steps=3, forecaster=forecaster)

    assert plan.forecaster == forecaster


@pytest.mark.parametrize("forecaster", ["ForecasterRecursive", "ForecasterDirect"])
@pytest.mark.parametrize("name", ["lag_1", "roll_mean_3"])
def test_plan_InvalidInputError_when_exog_named_like_predictor(name, forecaster):
    """
    Test that plan() rejects an exogenous column named like a lag ('lag_1')
    or a window feature ('roll_mean_3', from the explicit window features),
    with `data` as field and a hint: the script failed with duplicated
    feature names.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_single.rename(columns={"promo": name}),
        target="sales",
        date_column="date",
    )

    err_msg = re.escape(
        f"Exogenous column(s) '{name}' have the name of a predictor that "
        f"{forecaster} creates (a lag or a window feature), so the script "
        f"would fail with duplicated feature names. Rename them in the data."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.plan(
            profile, steps=3, forecaster=forecaster, lags=[1, 2],
            window_features=[{"stats": ["mean"], "window_size": 3}],
        )

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "data"
    assert exc_info.value.hint == (
        "Rename the exogenous columns named like lags ('lag_1') or window "
        "features ('roll_mean_7')."
    )


def test_plan_InvalidInputError_when_exog_named_like_default_window_feature():
    """
    Test that the check also reads the window features that plan() chooses
    for daily data (a rolling mean of 21 days).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_single.rename(columns={"promo": "roll_mean_21"}),
        target="sales",
        date_column="date",
    )

    err_msg = re.escape(
        "Exogenous column(s) 'roll_mean_21' have the name of a predictor "
        "that ForecasterRecursive creates"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        assistant.plan(profile, steps=3)


def test_plan_exog_named_differently_from_predictors_passes():
    """
    Test that plan() accepts exogenous columns whose names are close to, but
    not, those of the predictors it creates ('lag_9' with lags [1, 2], a
    rolling std when only the mean is created).
    """
    assistant = ForecastingAssistant()
    data = df_single.rename(columns={"promo": "lag_9"}).assign(roll_std_3=1.0)
    profile = assistant.profile(data=data, target="sales", date_column="date")

    plan = assistant.plan(
        profile, steps=3, lags=[1, 2],
        window_features=[{"stats": ["mean"], "window_size": 3}],
    )

    assert plan.forecaster == "ForecasterRecursive"
    assert plan.use_exog is True


def test_plan_InvalidInputError_when_multivariate_exog_named_with_series_prefix():
    """
    Test that for ForecasterDirectMultiVariate the lag names are prefixed
    with the series: 'series_a_lag_1' clashes, but 'lag_1' does not.
    """
    assistant = ForecastingAssistant()
    clashing = df_multi_wide.assign(series_a_lag_1=np.arange(100) % 3 * 1.0)
    profile = assistant.profile(
        data=clashing, target=["series_a", "series_b"], date_column="date"
    )

    err_msg = re.escape(
        "Exogenous column(s) 'series_a_lag_1' have the name of a predictor "
        "that ForecasterDirectMultiVariate creates (a lag or a window "
        "feature), so the script would fail with duplicated feature names."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.plan(profile, steps=3, forecaster="ForecasterDirectMultiVariate")
    assert exc_info.value.field == "data"

    plain = df_multi_wide.assign(lag_1=np.arange(100) % 3 * 1.0)
    profile = assistant.profile(
        data=plain, target=["series_a", "series_b"], date_column="date"
    )
    plan = assistant.plan(profile, steps=3, forecaster="ForecasterDirectMultiVariate")
    assert plan.forecaster == "ForecasterDirectMultiVariate"


@pytest.mark.parametrize(
    "forecaster",
    ["ForecasterStats", "ForecasterFoundation", "ForecasterEquivalentDate"],
)
def test_plan_does_not_check_exog_names_when_forecaster_has_no_lags(forecaster):
    """
    Test that plan() does not reject exogenous columns named 'lag_1' or
    'roll_mean_3' for the statistical, foundation and baseline forecasters.
    """
    assistant = ForecastingAssistant()
    data = df_single.rename(columns={"promo": "lag_1"}).assign(roll_mean_3=1.0)
    profile = assistant.profile(data=data, target="sales", date_column="date")

    plan = assistant.plan(profile, steps=3, forecaster=forecaster)

    assert plan.forecaster == forecaster


def test_plan_InvalidInputError_when_baseline_on_datetime_index_without_frequency():
    """
    Test that plan() rejects ForecasterEquivalentDate on a datetime index
    whose frequency cannot be inferred (irregular timestamps): its offset
    counts periods of the frequency.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_irregular, target="sales", date_column="date")

    err_msg = re.escape(
        "The frequency of the datetime index could not be inferred (the "
        "timestamps are irregular or too few), and 'ForecasterEquivalentDate' "
        "needs a regular DatetimeIndex. Check the dates: day-first values "
        "such as '13/02/2023' are read month-first unless parsed explicitly, "
        "for example with pandas.to_datetime(..., dayfirst=True)."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.plan(profile, steps=3, forecaster="ForecasterEquivalentDate")

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "profile"


def test_plan_InvalidInputError_without_warning_when_baseline_has_no_frequency_and_missing_target():
    """
    Test that, for ForecasterEquivalentDate on irregular timestamps with
    missing target values, the frequency error is raised before the warning
    about the missing values: no warning is emitted.
    """
    assistant = ForecastingAssistant()
    data = df_irregular.copy()
    data.loc[[10, 20], "sales"] = np.nan
    # The profile reports the interleaved missing values of the target.
    with pytest.warns(MissingValuesWarning):
        profile = assistant.profile(data=data, target="sales", date_column="date")

    err_msg = re.escape(
        "The frequency of the datetime index could not be inferred (the "
        "timestamps are irregular or too few), and 'ForecasterEquivalentDate' "
        "needs a regular DatetimeIndex."
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
            assistant.plan(profile, steps=3, forecaster="ForecasterEquivalentDate")

    assert exc_info.value.field == "profile"


def test_plan_baseline_when_index_is_a_range_index():
    """
    Test that ForecasterEquivalentDate still plans on data with a RangeIndex
    (no dates, so no frequency is needed).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_range_index, target="sales")

    plan = assistant.plan(profile, steps=3, forecaster="ForecasterEquivalentDate")

    assert plan.forecaster == "ForecasterEquivalentDate"


# =============================================================================
# Tests: error code and field
# =============================================================================
@pytest.mark.parametrize(
    "kwargs, expected_field, err_msg",
    [
        (
            {"steps": 0}, "steps",
            "`steps` must be an integer greater than or equal to 1, got 0.",
        ),
        (
            {"steps": 7, "lags": "12"}, "lags",
            "`lags` must be an int or a list of ints, got '12'.",
        ),
        (
            {"steps": 7, "estimator": "Unknown"}, "estimator",
            "'Unknown' is not a supported estimator. Supported estimators: "
            "['LGBMRegressor', 'Ridge', 'XGBRegressor', 'CatBoostRegressor', "
            "'RandomForestRegressor', 'HistGradientBoostingRegressor'].",
        ),
        (
            {"steps": 7, "interval": [0.9, 0.1]}, "interval",
            "`interval` must be `[lower, upper]` with 0 < lower < upper < 1, "
            "got [0.9, 0.1].",
        ),
        (
            {"steps": 7, "window_features": "mean"}, "window_features",
            "`window_features` must be a list of dicts, got str.",
        ),
        (
            {"steps": 7, "forecaster": "ForecasterStats", "lags": 3}, "lags",
            "'ForecasterStats' models the past values itself: it takes no lag "
            "or window features, so ['lags'] cannot be applied. Omit them.",
        ),
    ],
    ids=[
        "steps", "lags", "estimator", "interval", "window_features",
        "inapplicable_lags",
    ],
)
def test_plan_InvalidInputError_code_and_field(kwargs, expected_field, err_msg):
    """
    Test that the errors of plan() are InvalidInputError (a ValueError)
    with the code 'invalid_argument', the argument at fault as field and
    the message they had before.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        assistant.plan(profile, **kwargs)

    assert isinstance(exc_info.value, ValueError)
    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == expected_field


def test_plan_InvalidInputError_field_when_datetime_index_has_no_frequency():
    """
    Test that a profile without an inferable frequency raises
    InvalidInputError with `profile` as field, the argument plan() received
    the dates through.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_irregular, target="sales", date_column="date")

    err_msg = re.escape(
        "The frequency of the datetime index could not be inferred (the "
        "timestamps are irregular or too few), and 'ForecasterRecursive' needs "
        "a regular DatetimeIndex."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.plan(profile, steps=5)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "profile"


def test_plan_InvalidInputError_when_multivariate_on_long_format():
    """
    Test that plan() rejects ForecasterDirectMultiVariate on long-format data
    with several series before any script is rendered: forecast() failed
    inside the script (NameError on `exog_train`, or no series named as the
    level), in every mode.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long, target="value", date_column="date",
        series_id_column="series_id",
    )

    err_msg = re.escape(
        "ForecasterDirectMultiVariate cannot forecast long-format data with "
        "several series."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        assistant.plan(profile, steps=7, forecaster="ForecasterDirectMultiVariate")


@pytest.mark.parametrize(
    "forecaster, err_msg",
    [
        (
            "ForecasterDirectMultiVariate",
            "ForecasterDirectMultiVariate cannot forecast long-format data with "
            "several series.",
        ),
        ("ForecasterStats", "supports a single series only"),
    ],
    ids=lambda value: f"{value}"[:30],
)
def test_plan_InvalidInputError_without_UnrecommendedForecasterWarning_when_rejected(
    forecaster, err_msg
):
    """
    Test that a forecaster left out of the candidates of long-format data
    with several series, and rejected for that data, raises without first
    warning that it is used as requested: the warning is only emitted for a
    forecaster that accepts the data. ForecasterDirectMultiVariate is not a
    candidate there, since plan() rejects it.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long, target="value", date_column="date",
        series_id_column="series_id",
    )

    assert profile.forecaster_candidates == [
        "ForecasterRecursiveMultiSeries",
        "ForecasterFoundation",
    ]
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        with pytest.raises(InvalidInputError, match=re.escape(err_msg)):
            assistant.plan(profile, steps=7, forecaster=forecaster)

    assert not [w for w in record if w.category is UnrecommendedForecasterWarning]


@pytest.mark.parametrize(
    "kwargs",
    [{"lags": 3}, {"estimator": "Ridge"}, {"interval": [0.1, 0.8]}],
    ids=["lags", "estimator", "asymmetric_interval"],
)
def test_plan_InvalidInputError_without_UnrecommendedForecasterWarning_when_argument_rejected(
    kwargs,
):
    """
    Test that ForecasterStats, not a candidate for hourly data, raises for an
    argument it cannot use without first warning that it is used as
    requested: the warning is only emitted once the plan is built, so with
    warnings raised as errors it no longer hides the error.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_hourly, target="sales", date_column="date")

    assert "ForecasterStats" not in profile.forecaster_candidates
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        with pytest.raises(InvalidInputError):
            assistant.plan(profile, steps=24, forecaster="ForecasterStats", **kwargs)

    assert not [w for w in record if w.category is UnrecommendedForecasterWarning]


def test_plan_InvalidInputError_when_long_format_dated_by_index():
    """
    Test that plan() rejects long-format data with several series whose
    dates are the index: the script read a 'datetime' column that does not
    exist.
    """
    data = df_multi_long.set_index("date")
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=data, target="value", series_id_column="series_id"
    )

    err_msg = re.escape(
        "Long-format data with several series needs its dates in a column"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        assistant.plan(profile, steps=7)


@pytest.mark.parametrize(
    "estimator_kwargs, type_name",
    [([1, 2], "list"), ("alpha=1", "str")],
    ids=["list", "str"],
)
def test_plan_InvalidInputTypeError_when_estimator_kwargs_not_a_dict(
    estimator_kwargs, type_name
):
    """
    Test that plan() raises InvalidInputTypeError with the field
    'estimator_kwargs' when it is not a dict.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        f"`estimator_kwargs` must be a dict of keyword arguments, such as "
        f"{{'alpha': 0.5}}, got {type_name}."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        assistant.plan(profile, steps=5, estimator_kwargs=estimator_kwargs)

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "estimator_kwargs"


@pytest.mark.parametrize(
    "name, suggestion",
    [("foo", ""), ("ordr", " Did you mean 'order'?")],
    ids=["no close match", "close match"],
)
def test_plan_InvalidInputError_when_arima_kwarg_unknown(name, suggestion):
    """
    Test that plan() with ForecasterStats rejects a keyword argument that
    Arima does not have, with the closest name when there is one.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(f"Arima has no parameter '{name}'.{suggestion}")
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.plan(
            profile,
            steps            = 5,
            forecaster       = "ForecasterStats",
            estimator_kwargs = {name: 1},
        )

    assert exc_info.value.field == "estimator_kwargs"


def test_plan_output_when_arima_kwarg_valid():
    """
    Test that plan() with ForecasterStats accepts a parameter of Arima.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    plan = assistant.plan(
        profile,
        steps            = 5,
        forecaster       = "ForecasterStats",
        estimator_kwargs = {"order": (1, 0, 0)},
    )

    assert plan.forecaster == "ForecasterStats"
    assert plan.estimator_kwargs == {"order": (1, 0, 0)}


# =============================================================================
# Tests: plan.warnings
# =============================================================================
def _plan_recording_warnings(assistant, profile, **kwargs):
    """
    Call plan() recording every warning it emits, repeated ones included,
    and return the plan with the messages in emission order.
    """
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        plan = assistant.plan(profile, **kwargs)
    return plan, [str(w.message) for w in record]


def test_plan_warnings_empty_when_no_warning_emitted():
    """
    Test that a plan built without any warning has an empty `warnings`
    list.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    plan, emitted = _plan_recording_warnings(assistant, profile, steps=10)

    assert emitted == []
    assert plan.warnings == []


def test_plan_warnings_equal_emitted_when_forecaster_not_recommended():
    """
    Test that the UnrecommendedForecasterWarning emitted at the end of
    plan() is also kept, with the same text, in `plan.warnings`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_hourly, target="sales", date_column="date")

    plan, emitted = _plan_recording_warnings(
        assistant, profile, steps=10, forecaster="ForecasterStats"
    )

    assert plan.warnings == [
        "Forecaster 'ForecasterStats' is not among the recommended candidates "
        "for this profile (['ForecasterRecursive', 'ForecasterDirect', "
        "'ForecasterFoundation']), but it is used as requested. It may be slow "
        "or perform poorly on this data."
    ]
    assert plan.warnings == emitted


def test_plan_warnings_equal_emitted_when_baseline_on_missing_values():
    """
    Test that the warning of a baseline built on a target with missing
    values is kept, with the same text, in `plan.warnings`.
    """
    assistant = ForecastingAssistant()
    with pytest.warns(MissingValuesWarning):
        profile = assistant.profile(
            data=df_with_missing, target="sales", date_column="date"
        )

    plan, emitted = _plan_recording_warnings(
        assistant, profile, steps=5, forecaster="ForecasterEquivalentDate"
    )

    assert plan.warnings == [
        "'ForecasterEquivalentDate' cannot handle missing values: the target "
        "has missing values or missing timestamps, and "
        "ForecasterEquivalentDate repeats a missing value as a missing "
        "prediction. Impute the target before fitting, or the predictions "
        "and metrics will contain missing values."
    ]
    assert plan.warnings == emitted


def test_plan_warnings_equal_emitted_in_order_when_several_warnings():
    """
    Test that, with unknown LightGBM keyword arguments and an unrecommended
    forecaster, `plan.warnings` holds every warning emitted, in the order
    they were emitted (the forecaster warning last, once the plan is built).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    profile = profile.model_copy(
        update={"forecaster_candidates": ["ForecasterRecursive"]}
    )

    plan, emitted = _plan_recording_warnings(
        assistant,
        profile,
        steps            = 5,
        forecaster       = "ForecasterDirect",
        estimator        = "LGBMRegressor",
        estimator_kwargs = {"n_estimatorz": 10, "learnin_rate": 0.1},
    )

    assert plan.warnings == [
        "'n_estimatorz' is not a named parameter of LGBMRegressor. It is "
        "passed to the library as an extra parameter, which ignores it "
        "without an error if it does not exist. Did you mean 'n_estimators'?",
        "'learnin_rate' is not a named parameter of LGBMRegressor. It is "
        "passed to the library as an extra parameter, which ignores it "
        "without an error if it does not exist. Did you mean 'learning_rate'?",
        "Forecaster 'ForecasterDirect' is not among the recommended candidates "
        "for this profile (['ForecasterRecursive']), but it is used as "
        "requested. It may be slow or perform poorly on this data.",
    ]
    assert plan.warnings == emitted


def test_plan_warnings_kept_when_plan_reloaded_from_json():
    """
    Test that `plan.warnings` survives a JSON round trip unchanged, so a
    saved plan keeps the warnings of the call that built it.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_hourly, target="sales", date_column="date")
    with pytest.warns(UnrecommendedForecasterWarning):
        plan = assistant.plan(profile, steps=10, forecaster="ForecasterStats")

    reloaded = ForecastPlan.model_validate_json(plan.model_dump_json())

    assert reloaded.warnings == plan.warnings
    assert len(reloaded.warnings) == 1


def test_plan_output_overridden_fields_record_the_arguments_given():
    """
    Test that `overridden_fields` names the arguments passed with a value,
    in the canonical order, and not those left to the rules: None and an
    empty `estimator_kwargs`, and `steps` and `interval`, which have no
    rule.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    default = assistant.plan(profile, steps=10, interval=[0.1, 0.9])
    chosen = assistant.plan(
        profile,
        steps            = 10,
        window_features  = [{"stats": ["mean"], "window_size": 7}],
        lags             = 3,
        estimator        = "Ridge",
        estimator_kwargs = {},
        forecaster       = "ForecasterRecursive",
    )

    assert default.overridden_fields == []
    assert chosen.overridden_fields == [
        "forecaster", "estimator", "lags", "window_features"
    ]


@pytest.mark.parametrize(
    "metric, expected_metric, expected_metrics, sentence",
    [
        (
            "mean_squared_error",
            "mean_squared_error",
            ["mean_squared_error"],
            "Metric: mean_squared_error, as requested.",
        ),
        (
            ["median_absolute_error", "mean_absolute_error"],
            "median_absolute_error",
            ["median_absolute_error", "mean_absolute_error"],
            "Primary metric: median_absolute_error, as requested; also "
            "computed: mean_absolute_error.",
        ),
    ],
    ids=["one metric", "list"],
)
def test_plan_output_when_metric_given(
    metric, expected_metric, expected_metrics, sentence
):
    """
    Test that `metric` sets the primary metric (the first one) and the only
    metrics computed, records the decision and replaces the sentence that
    explains the selected metric.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    plan = assistant.plan(profile, steps=10, metric=metric)

    assert plan.metric == expected_metric
    assert plan.metrics_to_compute == expected_metrics
    assert plan.overridden_fields == ["metric"]
    assert plan.explanation.endswith(sentence)
    assert "MAE is interpretable" not in plan.explanation


@pytest.mark.parametrize(
    "metric, error, message",
    [
        ([], ValueError, "`metric` must not be an empty list."),
        (
            ["mean_squared_error", "mean_squared_error"],
            ValueError,
            "`metric` repeats ['mean_squared_error']: list each metric once.",
        ),
        ("accuracy", ValueError, "Unknown metric 'accuracy'."),
        (3, TypeError, "`metric` must be a metric name or a list of metric names"),
        ([1], TypeError, "`metric` must be a metric name or a list of metric names"),
    ],
    ids=["empty", "repeated", "unknown", "int", "list of int"],
)
def test_plan_error_when_metric_invalid(metric, error, message):
    """
    Test that an empty, repeated, unknown or non-text metric is rejected
    with `field='metric'`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(error, match=re.escape(message)) as info:
        assistant.plan(profile, steps=10, metric=metric)

    assert info.value.field == "metric"


def test_plan_TypeError_when_metric_given_positionally():
    """
    Test that `metric` is keyword-only, so the positional order of the
    arguments of 0.3 does not change.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(TypeError):
        assistant.plan(profile, 10, None, None, None, None, None, None, "mae")


def test_plan_output_when_use_exog_false():
    """
    Test that `use_exog=False` leaves out the exogenous columns of the
    data (no transformer for them), records the decision and says so in
    the explanation, and that True keeps the rule's choice without that
    sentence.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    without = assistant.plan(profile, steps=10, estimator="Ridge", use_exog=False)
    with_exog = assistant.plan(profile, steps=10, estimator="Ridge", use_exog=True)

    assert without.use_exog is False
    assert "transformer_exog" not in without.forecaster_kwargs
    assert without.overridden_fields == ["estimator", "use_exog"]
    assert without.explanation.endswith(
        "Exogenous variables ['promo'] are not used, as requested."
    )
    assert with_exog.use_exog is True
    assert with_exog.forecaster_kwargs["transformer_exog"] == "StandardScaler"
    assert "as requested" not in with_exog.explanation


@pytest.mark.parametrize(
    "data, forecaster, estimator, reason",
    [
        (df_no_exog, None, None, "the data has no exogenous columns"),
        (
            df_single,
            "ForecasterEquivalentDate",
            None,
            "'ForecasterEquivalentDate' only repeats past values of the target",
        ),
        (
            df_single,
            "ForecasterFoundation",
            "Salesforce/moirai-2.0-R-small",
            "'Salesforce/moirai-2.0-R-small' does not accept the exogenous "
            "columns of the data as covariates",
        ),
    ],
    ids=["no exog", "baseline", "foundation without covariates"],
)
def test_plan_ValueError_when_use_exog_true_cannot_apply(
    data, forecaster, estimator, reason
):
    """
    Test that `use_exog=True` is rejected with `field='use_exog'` when the
    data has no exogenous columns or the forecaster cannot use them.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=data, target="sales", date_column="date")

    err_msg = re.escape(f"`use_exog=True` cannot be applied: {reason}.")
    with pytest.raises(ValueError, match=err_msg) as info:
        assistant.plan(
            profile, steps=10, forecaster=forecaster, estimator=estimator,
            use_exog=True,
        )

    assert info.value.field == "use_exog"


def test_plan_ValueError_when_use_exog_true_and_profile_leaves_exog_out():
    """
    Test that `use_exog=True` with a profile whose `exog_columns` left every
    exogenous column out says that the profile left them out.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data         = df_single,
        target       = "sales",
        date_column  = "date",
        exog_columns = [],
    )

    err_msg = re.escape(
        "`use_exog=True` cannot be applied: the profile has no exogenous "
        "columns (`exog_columns` of profile() left them out)."
    )
    with pytest.raises(ValueError, match=err_msg) as info:
        assistant.plan(profile, steps=10, use_exog=True)

    assert info.value.field == "use_exog"


def test_plan_TypeError_when_use_exog_not_bool():
    """
    Test that a `use_exog` that is not True, False or None is rejected.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(TypeError, match=re.escape("`use_exog` must be True, False")):
        assistant.plan(profile, steps=10, use_exog="no")


def test_plan_explanation_names_the_series_multivariate_predicts():
    """
    Test that the explanation of a ForecasterDirectMultiVariate plan names
    the series it predicts, the first of the target.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_wide, target=["series_a", "series_b"], date_column="date"
    )

    plan = assistant.plan(profile, steps=5, forecaster="ForecasterDirectMultiVariate")

    assert plan.explanation.endswith(
        "It predicts 'series_a', the first series of the target, from the lags "
        "of all the series."
    )


def test_plan_output_when_use_exog_false_ignores_the_exog_left_out():
    """
    Test that the exogenous columns left out with `use_exog=False` do not
    shape the plan: their missing values neither set `dropna_from_series`
    nor add a preprocessing step, and categorical columns need no step.
    """
    assistant = ForecastingAssistant()
    data = df_categorical_exog.assign(
        promo=df_categorical_exog["promo"].where(
            df_categorical_exog.index != 20
        )
    )
    profile = assistant.profile(data=data, target="sales", date_column="date")

    default = assistant.plan(profile, steps=10, estimator="Ridge")
    without = assistant.plan(profile, steps=10, estimator="Ridge", use_exog=False)

    assert default.forecaster_kwargs["dropna_from_series"] is True
    assert {step.action for step in default.preprocessing_steps} >= {
        "handle_missing_values", "handle_categorical_exog"
    }
    assert without.forecaster_kwargs["dropna_from_series"] is False
    assert without.preprocessing_steps == []
    assert "NaN" not in without.explanation


def test_plan_ValueError_when_use_exog_true_and_stats_has_only_categorical_exog():
    """
    Test that `use_exog=True` is rejected for ForecasterStats when every
    exogenous column is categorical, which its script leaves out, while
    the rule keeps its choice and `use_exog=False` is accepted.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_categorical_exog.drop(columns="promo"),
        target="sales",
        date_column="date",
    )

    err_msg = re.escape(
        "`use_exog=True` cannot be applied: 'ForecasterStats' only uses numeric "
        "exogenous columns, and ['weekday'] are categorical."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(profile, steps=10, forecaster="ForecasterStats", use_exog=True)
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats", use_exog=False
    )

    assert plan.use_exog is False


def test_plan_output_when_differentiation_given():
    """
    Test that `differentiation` is written into the forecaster arguments,
    recorded, explained, and reserved from the lag budget: the lags
    selected leave room for the order.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    plan = assistant.plan(profile, steps=10, differentiation=2)

    assert plan.forecaster_kwargs["differentiation"] == 2
    assert plan.overridden_fields == ["differentiation"]
    assert plan.forecaster_kwargs["lags"] == [1, 2, 3, 4, 5, 7]
    assert plan.explanation.endswith(
        "The target is differenced (order 2) before training, as requested, "
        "and the predictions are integrated back."
    )


@pytest.mark.parametrize(
    "differentiation, error",
    [(0, ValueError), (-1, ValueError), (1.5, TypeError), (True, TypeError), ("1", TypeError)],
    ids=lambda dt: f"{dt!r}",
)
def test_plan_ValueError_or_TypeError_when_differentiation_invalid(differentiation, error):
    """
    Test that a differentiation order that is not an integer of at least 1
    is rejected with `field='differentiation'`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        f"`differentiation` must be an integer greater than or equal to 1, got "
        f"{differentiation!r}."
    )
    with pytest.raises(error, match=err_msg) as info:
        assistant.plan(profile, steps=10, differentiation=differentiation)

    assert info.value.field == "differentiation"


@pytest.mark.parametrize(
    "forecaster",
    ["ForecasterStats", "ForecasterEquivalentDate", "ForecasterFoundation"],
)
def test_plan_ValueError_when_differentiation_for_forecaster_without_it(forecaster):
    """
    Test that a forecaster that is not a machine learning one rejects
    `differentiation`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        f"['differentiation'] only apply to the machine learning forecasters "
        f"(['ForecasterDirect', 'ForecasterDirectMultiVariate', "
        f"'ForecasterRecursive', 'ForecasterRecursiveMultiSeries']), not to "
        f"'{forecaster}'. Omit them."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(profile, steps=10, forecaster=forecaster, differentiation=1)


def test_plan_ValueError_when_explicit_lags_and_differentiation_exceed_budget():
    """
    Test that the differentiation order counts in the window budget of
    explicit lags: 33 lags fit 100 observations, not with an order of 1.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    assistant.plan(profile, steps=10, lags=33)
    err_msg = re.escape(
        "Explicit lags/window_features span up to 33 observations plus 1 for "
        "the differentiation, exceeding the maximum of 33"
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(profile, steps=10, lags=33, differentiation=1)


def test_plan_InvalidInputError_names_differentiation_when_the_order_does_not_fit():
    """
    Test that an order larger than the lags and the windows, which fit on
    their own, raises with the field 'differentiation' instead of blaming
    lags the user did not pass.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    err_msg = re.escape(
        "`differentiation=40` plus the largest lag or window size (1) exceeds "
        "the maximum of 33 (33% of 100 observations). Use a smaller order (1 "
        "or 2 remove a trend), or fewer lags and smaller window sizes."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        assistant.plan(profile, steps=10, differentiation=40)

    assert exc_info.value.code == "insufficient_data"
    assert exc_info.value.field == "differentiation"


def test_plan_output_when_differentiation_drops_default_windows_without_room():
    """
    Test that the default window features that leave no room for the
    differentiation order are dropped instead of rejected: on 100 weekly
    observations the rule picks a window of 33, the whole budget.
    """
    assistant = ForecastingAssistant()
    data = pd.DataFrame({
        "date": pd.date_range("2020-01-05", periods=100, freq="W"),
        "y": np.arange(100, dtype=float),
    })
    profile = assistant.profile(data=data, target="y", date_column="date")

    plan = assistant.plan(profile, steps=5, differentiation=1)

    assert profile.window_features == [
        {"stats": ["mean", "std"], "window_size": 3},
        {"stats": ["mean"], "window_size": 33},
    ]
    assert plan.forecaster_kwargs["window_features"] == [
        {"stats": ["mean", "std"], "window_size": 3}
    ]
    assert plan.explanation.endswith(
        "Window features of size [33] are left out: with the differentiation "
        "they exceed the data budget."
    )


def test_plan_output_when_feature_overrides_given():
    """
    Test that `calendar_features`, `target_transformer` and
    `dropna_from_series` replace the rules, are recorded and explained;
    the calendar encoding follows the estimator.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    plan = assistant.plan(
        profile, steps=10, estimator="Ridge",
        calendar_features=["month", "day_of_week"], target_transformer="none",
        dropna_from_series=True,
    )
    none = assistant.plan(profile, steps=10, calendar_features=[])

    assert plan.forecaster_kwargs["calendar_features"] == {
        "features": ["month", "day_of_week"], "encoding": "cyclical"
    }
    assert "transformer_y" not in plan.forecaster_kwargs
    assert plan.forecaster_kwargs["dropna_from_series"] is True
    assert plan.overridden_fields == [
        "estimator", "calendar_features", "target_transformer",
        "dropna_from_series",
    ]
    assert plan.explanation.endswith(
        "Calendar features as requested. Target not scaled, as requested. "
        "Training rows with missing values are dropped, as requested."
    )
    assert none.forecaster_kwargs["calendar_features"] is None
    assert none.explanation.endswith("No calendar features, as requested.")


def test_plan_output_when_target_transformer_on_multi_series():
    """
    Test that `target_transformer` is written as `transformer_series` for a
    multi-series forecaster, also with a tree-based estimator, which the
    rule leaves unscaled.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_wide, target=["series_a", "series_b"], date_column="date"
    )

    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor",
        target_transformer="StandardScaler",
    )

    assert plan.forecaster_kwargs["transformer_series"] == "StandardScaler"


@pytest.mark.parametrize(
    "arguments, error, message",
    [
        (
            {"calendar_features": "month"},
            TypeError,
            "`calendar_features` must be a list of calendar feature names",
        ),
        (
            {"calendar_features": ["month", "holiday"]},
            ValueError,
            "Unknown calendar features ['holiday'].",
        ),
        (
            {"calendar_features": ["month", "month"]},
            ValueError,
            "`calendar_features` repeats ['month']: list each feature once.",
        ),
        (
            {"target_transformer": "MinMaxScaler"},
            ValueError,
            "`target_transformer` must be one of ['StandardScaler', 'none'], "
            "got 'MinMaxScaler'.",
        ),
        (
            {"dropna_from_series": "yes"},
            TypeError,
            "`dropna_from_series` must be True, False or None, got 'yes'.",
        ),
        (
            {"forecaster": "ForecasterStats", "calendar_features": []},
            ValueError,
            "['calendar_features'] only apply to the machine learning forecasters",
        ),
    ],
    ids=["str", "unknown", "repeated", "transformer", "dropna", "stats"],
)
def test_plan_ValueError_or_TypeError_when_feature_override_invalid(
    arguments, error, message
):
    """
    Test that an invalid calendar feature list, scaler or NaN flag, or one
    given to a forecaster that is not a machine learning one, is rejected
    with the name of the argument in `field`.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    with pytest.raises(error, match=re.escape(message)) as info:
        assistant.plan(profile, steps=10, **arguments)

    assert info.value.field == [k for k in arguments if k != "forecaster"][0]


def test_plan_ValueError_when_chosen_calendar_feature_is_an_exog_column():
    """
    Test that a chosen calendar feature whose column is an exogenous column
    is rejected (the rule leaves it out), and accepted when the plan does
    not use the exogenous columns.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_calendar_named_exog, target="sales", date_column="date"
    )

    err_msg = re.escape(
        "Calendar features ['month'] create columns already among the "
        "exogenous columns ['promo', 'month', 'weekend']."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(
            profile, steps=5, estimator="LGBMRegressor",
            calendar_features=["month", "quarter"],
        )
    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor",
        calendar_features=["month"], use_exog=False,
    )

    assert plan.forecaster_kwargs["calendar_features"]["features"] == ["month"]


def test_plan_ValueError_when_calendar_features_without_datetime_index():
    """
    Test that chosen calendar features on data without dates are rejected.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_range_index, target="sales")

    with pytest.raises(ValueError, match=re.escape("need a datetime index")):
        assistant.plan(profile, steps=5, calendar_features=["month"])


def test_plan_ValueError_when_dropna_false_cannot_run():
    """
    Test that `dropna_from_series=False` is rejected when the data has
    missing values and the estimator does not accept them, and accepted
    with one that does.
    """
    assistant = ForecastingAssistant()
    with pytest.warns(MissingValuesWarning):
        profile = assistant.profile(
            data=df_with_missing, target="sales", date_column="date"
        )

    err_msg = re.escape(
        "`dropna_from_series=False` cannot be applied: the data has missing "
        "values and 'Ridge' does not accept them."
    )
    with pytest.raises(ValueError, match=err_msg):
        assistant.plan(profile, steps=5, estimator="Ridge", dropna_from_series=False)
    plan = assistant.plan(
        profile, steps=5, estimator="LGBMRegressor", dropna_from_series=False
    )

    assert plan.forecaster_kwargs["dropna_from_series"] is False
