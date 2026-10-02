# Unit test plan ForecastingAssistant

import re
import warnings

import pytest

from skforecast.exceptions import MissingValuesWarning

from skforecast_ai import ForecastingAssistant
from skforecast_ai.exceptions import (
    InvalidInputError,
    UnrecommendedForecasterWarning,
)
from skforecast_ai.schemas import ForecastPlan

from tests.fixtures_assistant import (
    df_all_calendar_named_exog,
    df_calendar_named_exog,
    df_categorical_exog,
    df_hourly,
    df_multi_long,
    df_multi_wide,
    df_no_exog,
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
        "TimesFM Non-Commercial License v1.0, which restricts commercial use "
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


def test_plan_output_when_foundation_model_is_gated():
    """
    Test that the explanation warns that the weights of a gated foundation
    model need an authenticated Hugging Face account.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile    = profile,
        steps      = 10,
        forecaster = "ForecasterFoundation",
        estimator  = "theforecastingcompany/t0-alpha",
    )

    assert (
        "The weights of 'theforecastingcompany/t0-alpha' are gated on the "
        "Hugging Face Hub: log in with an account that has accepted the model "
        "license before running the script."
    ) in plan.explanation


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


def test_plan_ValueError_when_datetime_index_has_no_frequency(tmp_path):
    """
    Test that plan() raises, pointing at day-first dates, when the datetime
    index has no inferable frequency: dd/mm/yyyy strings read month-first
    give irregular timestamps, and the script would fail inside skforecast.
    """
    csv_path = tmp_path / "dayfirst.csv"
    df_single.assign(
        date=df_single["date"].dt.strftime("%d/%m/%Y")
    ).to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=csv_path, target="sales", date_column="date")

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


def test_plan_InvalidInputError_field_when_datetime_index_has_no_frequency(
    tmp_path,
):
    """
    Test that a profile without an inferable frequency raises
    InvalidInputError with `profile` as field, the argument plan() received
    the dates through.
    """
    csv_path = tmp_path / "dayfirst.csv"
    df_single.assign(
        date=df_single["date"].dt.strftime("%d/%m/%Y")
    ).to_csv(csv_path, index=False)
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=csv_path, target="sales", date_column="date")

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
