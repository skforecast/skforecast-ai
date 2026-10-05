# Unit test schemas skforecast_ai

import json
import re

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from skforecast_ai.schemas import (
    CV_OVERRIDE_NAMES,
    CandidateConfig,
    CompareProgress,
    DataProfile,
    ForecastPlan,
    RefinePlanOverrides,
)
from skforecast_ai.schemas.plans import CVParams, PlanOverrides, WindowFeature

from tests.fixtures_llm import (
    make_backtest_result,
    make_code_generation_result,
    make_comparison_result,
    make_cv_result,
    make_forecast_result,
)

RESULT_BUILDERS = {
    "ForecastResult":       make_forecast_result,
    "BacktestResult":       make_backtest_result,
    "ComparisonResult":     lambda: make_comparison_result(with_baseline=True),
    "CodeGenerationResult": make_code_generation_result,
    "CVResult":             make_cv_result,
}


def test_data_profile_invalid_index_type():
    """
    Test DataProfile raises ValidationError when index_type is not a valid
    Literal value.
    """
    err_msg = re.escape("index_type")
    with pytest.raises(ValidationError, match=err_msg):
        DataProfile(
            n_series=1,
            series_lengths={"y": 100},
            target="y",
            index_type="invalid",
        )


def test_data_profile_ValidationError_when_frequency_not_an_alias():
    """
    Test DataProfile loaded from JSON raises ValidationError when its
    frequency, which the generated script writes into `asfreq()`, is not a
    pandas frequency alias.
    """
    fields = {
        "n_series": 1,
        "series_lengths": {"y": 100},
        "target": "y",
        "index_type": "datetime",
        "frequency": "D') or ('D",
    }
    err_msg = re.escape(
        "`frequency` must be a pandas frequency alias made of letters, digits "
        "and hyphens"
    )
    with pytest.raises(ValidationError, match=err_msg):
        DataProfile.model_validate_json(json.dumps(fields))


def test_forecast_plan_invalid_task_type():
    """
    Test ForecastPlan raises ValidationError when task_type is not a valid
    Literal value.
    """
    err_msg = re.escape("task_type")
    with pytest.raises(ValidationError, match=err_msg):
        ForecastPlan(
            task_type="unknown_task",
            forecaster="ForecasterRecursive",
            steps=24,
            explanation="Test.",
        )


@pytest.mark.parametrize(
    "task_type, forecaster, estimator",
    [
        ("single_series", "ForecasterRecursive", "Ridge"),
        ("multi_series", "ForecasterRecursiveMultiSeries", "Ridge"),
        ("statistical", "ForecasterStats", "Arima"),
    ],
    ids=["single_series", "multi_series", "statistical"],
)
def test_forecast_plan_ValidationError_when_interval_without_interval_method(
    task_type, forecaster, estimator
):
    """
    Test that a ForecastPlan built by hand or loaded from JSON with an
    `interval` and no `interval_method` raises: the backtest took
    skforecast's default method and forecast() computed no interval,
    without a warning. plan() always sets both.
    """
    err_msg = re.escape(
        "`interval` needs an `interval_method`: 'bootstrapping' for the machine "
        "learning forecasters, 'conformal' for ForecasterEquivalentDate and "
        "'native' for ForecasterStats and ForecasterFoundation, as plan() sets "
        "it."
    )
    with pytest.raises(ValidationError, match=err_msg):
        ForecastPlan(
            task_type   = task_type,
            forecaster  = forecaster,
            estimator   = estimator,
            steps       = 10,
            interval    = [0.1, 0.9],
            explanation = "Test.",
        )


@pytest.mark.parametrize(
    "estimator, estimator_kwargs, interval, match",
    [
        (None, {}, None, "needs the Hugging Face model ID"),
        ("Chronos-2", {}, None, "'Chronos-2' is not a foundation model"),
        (
            "autogluon/chronos-2-small",
            {"model_id": "google/timesfm-3.0-pytorch"},
            None,
            "cannot contain 'model_id'",
        ),
        (
            "google/timesfm-3.0-pytorch",
            {},
            [0.05, 0.95],
            "only predicts the quantile levels",
        ),
    ],
    ids=lambda dt: f"estimator, estimator_kwargs, interval, match: {dt}",
)
def test_forecast_plan_ValidationError_when_foundation_model_invalid(
    estimator, estimator_kwargs, interval, match
):
    """
    Test that a foundation ForecastPlan built by hand is validated like the
    plans built by `plan()`: the estimator must be a supported model ID,
    `estimator_kwargs` cannot hold the model ID, and the model must predict
    the interval.
    """
    with pytest.raises(ValidationError, match=re.escape(match)):
        ForecastPlan(
            task_type        = "foundation",
            forecaster       = "ForecasterFoundation",
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            steps            = 10,
            interval         = interval,
            explanation      = "Test.",
        )


@pytest.mark.parametrize(
    "update, match",
    [
        (
            {"estimator": "__import__('os').system('ls')"},
            "is not a supported estimator",
        ),
        (
            {"estimator": "Ridge", "estimator_kwargs": {"alpha=1) or (x": 1}},
            "`estimator_kwargs` keys must be valid Python parameter names",
        ),
        (
            {"estimator": "Ridge", "metrics_to_compute": ["f1_score"]},
            "Unknown metric 'f1_score'",
        ),
        (
            {"estimator": "Ridge", "interval": [5, 95]},
            "`interval` must be `[lower, upper]` with 0 < lower < upper < 1",
        ),
        (
            {"estimator": "Ridge", "forecaster": "ForecasterRecursive\nimport os"},
            "is not a supported forecaster",
        ),
        (
            {"estimator": "Ridge", "forecaster_kwargs": {"encoding": "ordinal"}},
            "`forecaster_kwargs` of 'ForecasterRecursive' cannot contain "
            "['encoding']",
        ),
        (
            {
                "estimator": "Ridge",
                "forecaster_kwargs": {"dropna_from_series": "False or True"},
            },
            "`forecaster_kwargs['dropna_from_series']` must be a bool",
        ),
        (
            {
                "estimator": "Ridge",
                "preprocessing_steps": [
                    {
                        "action": "drop_duplicates",
                        "reason": "Injected.",
                        "code_snippet": "import os",
                        "blocking": True,
                    }
                ],
            },
            "The blocking preprocessing step 'drop_duplicates' is not one of "
            "the steps the scripts can contain",
        ),
    ],
    ids=[
        "estimator",
        "estimator_kwargs key",
        "metric",
        "interval",
        "forecaster",
        "forecaster_kwargs key",
        "forecaster_kwargs value",
        "blocking preprocessing snippet",
    ],
)
def test_forecast_plan_ValidationError_when_script_inputs_invalid(update, match):
    """
    Test that a machine-learning ForecastPlan built by hand or loaded from
    JSON is validated like the plans built by `plan()`: the forecaster and
    the estimator must be supported, the keyword argument keys valid
    parameter names, the forecaster arguments and the blocking
    preprocessing steps within their closed sets, and the metrics and
    interval valid, since all of them reach the script.
    """
    fields = {
        "task_type": "single_series",
        "forecaster": "ForecasterRecursive",
        "steps": 10,
        "explanation": "Test.",
        **update,
    }
    with pytest.raises(ValidationError, match=re.escape(match)):
        ForecastPlan.model_validate(json.loads(json.dumps(fields)))


def test_forecast_plan_output_when_loaded_with_blocking_steps_of_version_0_3_1():
    """
    Test that a plan saved by skforecast-ai 0.3.1, with the three blocking
    preprocessing steps it could generate and the forecaster arguments it
    built, still loads.
    """
    fields = {
        "task_type": "single_series",
        "forecaster": "ForecasterRecursive",
        "forecaster_kwargs": {
            "lags": [1, 2, 3, 7],
            "window_features": [{"stats": ["mean", "std"], "window_size": 7}],
            "calendar_features": {
                "features": ["day_of_week", "weekend", "month"],
                "encoding": "cyclical",
            },
            "transformer_y": "StandardScaler",
            "transformer_exog": "StandardScaler",
            "categorical_features": "auto",
            "dropna_from_series": False,
        },
        "estimator": "Ridge",
        "estimator_kwargs": {},
        "steps": 12,
        "frequency": "D",
        "interval": [0.1, 0.9],
        "interval_method": "bootstrapping",
        "use_exog": True,
        "preprocessing_steps": [
            {
                "action": "drop_duplicates",
                "reason": "Duplicate timestamps cause errors in skforecast.",
                "code_snippet": "data = data[~data.index.duplicated(keep='first')]",
                "blocking": True,
            },
            {
                "action": "provide_datetime_index",
                "reason": "Provide a DatetimeIndex or date column for "
                          "time-based features.",
                "code_snippet": (
                    "# Set a DatetimeIndex:\n"
                    "# data.index = pd.date_range(start=..., "
                    "periods=len(data), freq=...)"
                ),
                "blocking": True,
            },
            {
                "action": "encode_target",
                "reason": "The target column is not numeric. Regression "
                          "forecasters require a numeric target.",
                "code_snippet": "# Convert target to numeric",
                "blocking": True,
            },
            {
                "action": "handle_missing_values",
                "reason": "Impute or handle missing values before training.",
                "code_snippet": "# Option 1: Use dropna_from_series=True",
                "blocking": False,
            },
        ],
        "explanation": "Plan saved by 0.3.1.",
    }

    plan = ForecastPlan.model_validate_json(json.dumps(fields))

    assert [step.action for step in plan.preprocessing_steps] == [
        "drop_duplicates",
        "provide_datetime_index",
        "encode_target",
        "handle_missing_values",
    ]
    assert plan.forecaster_kwargs == fields["forecaster_kwargs"]


@pytest.mark.parametrize(
    "steps",
    [True, "12", 12.5],
    ids=lambda steps: f"steps: {steps!r}",
)
def test_forecast_plan_ValidationError_when_steps_not_integer(steps):
    """
    Test ForecastPlan raises ValidationError for a bool, a string or a
    non-integer `steps`, which pydantic would otherwise coerce.
    """
    err_msg = re.escape(
        f"`steps` must be an integer greater than or equal to 1, got {steps!r}."
    )
    with pytest.raises(ValidationError, match=err_msg):
        ForecastPlan(
            task_type   = "single_series",
            forecaster  = "ForecasterRecursive",
            steps       = steps,
            explanation = "Test.",
        )


def test_forecast_plan_steps_normalized_when_integral_float():
    """
    Test that an integral float `steps` (12.0) is stored as the int 12.
    """
    plan = ForecastPlan(
        task_type   = "single_series",
        forecaster  = "ForecasterRecursive",
        steps       = 12.0,
        explanation = "Test.",
    )

    assert plan.steps == 12
    assert type(plan.steps) is int


def test_forecast_plan_invalid_steps_zero():
    """
    Test ForecastPlan raises ValidationError when steps is 0.
    """
    err_msg = re.escape("steps")
    with pytest.raises(ValidationError, match=err_msg):
        ForecastPlan(
            task_type="single_series",
            forecaster="ForecasterRecursive",
            steps=0,
            explanation="Test.",
        )


def test_data_profile_minimal():
    """
    Test DataProfile can be created with only required fields and defaults
    are correctly assigned.
    """
    profile = DataProfile(
        n_series=1,
        series_lengths={"y": 100},
        target="y",
        index_type="datetime",
    )
    assert profile.series_lengths["y"].length == 100
    assert profile.n_series == 1
    assert profile.index_type == "datetime"
    assert profile.target == "y"
    assert profile.frequency is None
    assert profile.date_column is None
    assert profile.series_id_column is None
    assert profile.exog_columns == []
    assert profile.categorical_exog == []
    assert profile.missing_target == {}
    assert profile.missing_exog == {}
    assert profile.unused_columns == []
    assert profile.warnings == []
    assert profile.span_index_length == 100
    assert profile.n_total_observations == 100


def test_data_profile_output_when_json_has_no_unused_columns():
    """
    Test that a profile saved before `unused_columns` existed loads with an
    empty list, and that the field survives a JSON round trip.
    """
    profile = DataProfile(
        n_series       = 1,
        series_lengths = {"y": 100},
        target         = "y",
        index_type     = "datetime",
        unused_columns = ["extra"],
    )
    saved = profile.model_dump(mode="json")
    del saved["unused_columns"]

    assert DataProfile.model_validate(saved).unused_columns == []
    assert DataProfile.model_validate_json(
        profile.model_dump_json()
    ).unused_columns == ["extra"]


@pytest.mark.parametrize(
    "data_format, series_lengths, start_date, frequency, expected",
    [
        (
            "single",
            {"y": {"length": 10, "start": "2023-01-05", "end": "2023-01-14"}},
            "2023-01-05", "D", "2023-01-05",
        ),
        (
            "long",
            {
                "a": {"length": 100, "start": "2023-01-01", "end": "2023-04-10"},
                "b": {"length": 40, "start": "2023-03-02", "end": "2023-04-10"},
            },
            "2023-03-02", "D", "2023-01-01",
        ),
        ("long", {"a": 100, "b": 40}, "2023-03-02", "D", "2023-03-02"),
        (
            "long",
            {
                "a": {
                    "length": 48,
                    "start": "2023-01-01 06:00:00",
                    "end": "2023-01-03 05:00:00",
                },
                "b": {
                    "length": 24,
                    "start": "2023-01-02 06:00:00",
                    "end": "2023-01-03 05:00:00",
                },
            },
            "2023-01-02 06:00:00", "h", "2023-01-01 06:00:00",
        ),
        (
            "long",
            {
                "a": {
                    "length": 200,
                    "start": "2023-01-01",
                    "end": "2023-01-09 07:00:00+01:00",
                },
                "b": {
                    "length": 200,
                    "start": "2023-01-02",
                    "end": "2023-01-10 07:00:00+01:00",
                },
            },
            "2023-01-02", "h", "2023-01-02",
        ),
    ],
    ids=["single", "long_staggered", "long_without_starts", "long_with_time",
         "long_dates_mixing_time_zones"],
)
def test_data_profile_span_start_date(
    data_format, series_lengths, start_date, frequency, expected
):
    """
    Test that the span of the data starts at `start_date`, except in long
    format, where it starts at the earliest first date of the series
    (`start_date` is the latest), written as `start_date` is (the date
    alone at midnight). The earliest is taken only when the span runs from
    it to the last date: without the dates of the series, or with dates
    that mix time zones (the span counted as the longest series), it is
    `start_date`.
    """
    profile = DataProfile(
        data_format    = data_format,
        n_series       = len(series_lengths),
        series_lengths = series_lengths,
        target         = "y",
        index_type     = "datetime",
        frequency      = frequency,
        start_date     = start_date,
    )

    assert profile.span_start_date == expected


def test_data_profile_span_start_date_falls_back_to_start_date_when_span_does_not_fit():
    """
    Test that in long format the span starts at the earliest first date
    only when the dates at `frequency` give exactly `span_index_length`
    observations; with a `span_index_length` that does not match, shorter
    or longer (here the value is replaced after validation), it is
    `start_date`.
    """
    profile = DataProfile(
        data_format    = "long",
        n_series       = 2,
        series_lengths = {
            "a": {"length": 100, "start": "2023-01-01", "end": "2023-04-10"},
            "b": {"length": 40, "start": "2023-03-02", "end": "2023-04-10"},
        },
        target         = "y",
        index_type     = "datetime",
        frequency      = "D",
        start_date     = "2023-03-02",
    )
    shorter = profile.model_copy(update={"span_index_length": 99})
    longer = profile.model_copy(update={"span_index_length": 101})

    assert profile.span_index_length == 100
    assert profile.span_start_date == "2023-01-01"
    assert shorter.span_start_date == "2023-03-02"
    assert longer.span_start_date == "2023-03-02"


def test_data_profile_full():
    """
    Test DataProfile with all fields populated.
    """
    profile = DataProfile(
        n_series=3,
        series_lengths={"s1": 500, "s2": 500, "s3": 500},
        target="sales",
        index_type="datetime",
        frequency="h",
        date_column="timestamp",
        series_id_column="store_id",
        exog_columns=["temperature", "holiday"],
        categorical_exog=["holiday"],
        missing_target={"sales": 5},
        missing_exog={"temperature": 2},
        warnings=["Missing values detected"],
    )
    assert profile.n_series == 3
    assert profile.frequency == "h"
    assert profile.date_column == "timestamp"
    assert profile.series_id_column == "store_id"
    assert profile.exog_columns == ["temperature", "holiday"]
    assert profile.categorical_exog == ["holiday"]
    assert profile.missing_target == {"sales": 5}
    assert profile.missing_exog == {"temperature": 2}
    assert profile.warnings == ["Missing values detected"]
    assert profile.n_total_observations == 1500


def test_data_profile_observation_counts_span_from_datetime_bounds():
    """
    Test span_index_length is computed from the union datetime index and
    n_total_observations is the pooled sum when series have datetime
    bounds and a frequency.
    """
    profile = DataProfile(
        n_series=2,
        series_lengths={
            "s1": {"start": "2020-01-01", "end": "2020-04-09", "length": 100},
            "s2": {"start": "2020-02-10", "end": "2020-06-28", "length": 140},
        },
        target="sales",
        index_type="datetime",
        frequency="D",
    )
    assert profile.span_index_length == 180
    assert profile.n_total_observations == 240


def test_data_profile_observation_counts_fallback_without_frequency():
    """
    Test span_index_length falls back to the longest individual series
    when no frequency is available.
    """
    profile = DataProfile(
        n_series=2,
        series_lengths={
            "s1": {"start": "2020-01-01", "end": "2020-04-09", "length": 100},
            "s2": {"start": "2020-02-10", "end": "2020-06-28", "length": 140},
        },
        target="sales",
        index_type="datetime",
    )
    assert profile.span_index_length == 140
    assert profile.n_total_observations == 240


def test_data_profile_n_observations_display_when_single_series_uses_length():
    """
    Test n_observations_display returns the single series length.
    """
    profile = DataProfile(
        n_series=1,
        series_lengths={
            "value": {"start": "2023-01-01", "end": "2023-04-10", "length": 100}
        },
        target="value",
        index_type="datetime",
        frequency="D",
    )
    assert profile.n_observations_display == 100


def test_data_profile_n_observations_display_when_multi_series_uses_span():
    """
    Test n_observations_display returns the union span for multi-series
    data, not the pooled total nor the longest series.
    """
    profile = DataProfile(
        n_series=2,
        series_lengths={
            "A": {"start": "2023-01-01", "end": "2023-04-10", "length": 60},
            "B": {"start": "2023-02-01", "end": "2023-03-01", "length": 29},
        },
        target="value",
        index_type="datetime",
        frequency="D",
    )
    assert profile.n_observations_display == 100


def test_forecast_plan_minimal():
    """
    Test ForecastPlan can be created with only required fields and defaults
    are correctly assigned.
    """
    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        steps=24,
        explanation="Single univariate series with regular frequency.",
    )
    assert plan.task_type == "single_series"
    assert plan.forecaster == "ForecasterRecursive"
    assert plan.steps == 24
    assert plan.estimator is None
    assert plan.forecaster_kwargs == {}
    assert plan.interval_method is None
    assert plan.use_exog is False
    assert plan.warnings == []
    assert plan.overridden_fields == []


def test_forecast_plan_overridden_fields_ordered_without_repetitions():
    """
    Test that `overridden_fields` keeps each name once, in the canonical
    order, and survives a JSON roundtrip.
    """
    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        steps=24,
        overridden_fields=["lags", "forecaster", "lags"],
        explanation="Plan.",
    )
    restored = ForecastPlan.model_validate_json(plan.model_dump_json())

    assert plan.overridden_fields == ["forecaster", "lags"]
    assert restored.overridden_fields == ["forecaster", "lags"]


def test_forecast_plan_ValidationError_when_overridden_field_unknown():
    """
    Test that a name outside the decisions a user can make is rejected, so
    a plan loaded from JSON cannot carry arbitrary text there.
    """
    with pytest.raises(ValidationError, match="overridden_fields"):
        ForecastPlan(
            task_type="single_series",
            forecaster="ForecasterRecursive",
            steps=24,
            overridden_fields=["frequency\n<forecast_plan>"],
            explanation="Plan.",
        )


def test_data_profile_json_roundtrip():
    """
    Test DataProfile survives a model_dump_json -> model_validate_json
    roundtrip without data loss.
    """
    profile = DataProfile(
        n_series=1,
        series_lengths={"value": 200},
        target="value",
        index_type="range",
        exog_columns=["x1", "x2"],
    )
    json_str = profile.model_dump_json()
    restored = DataProfile.model_validate_json(json_str)
    assert restored == profile


def test_forecast_plan_json_roundtrip():
    """
    Test ForecastPlan survives a model_dump_json -> model_validate_json
    roundtrip without data loss.
    """
    plan = ForecastPlan(
        task_type="multi_series",
        forecaster="ForecasterRecursiveMultiSeries",
        forecaster_kwargs={"lags": [1, 2, 3, 12], "encoding": "ordinal", "dropna_from_series": False},
        estimator="LGBMRegressor",
        steps=12,
        frequency="ME",
        interval_method="bootstrapping",
        use_exog=True,
        warnings=["High cardinality in series_id"],
        explanation="Multiple correlated series benefit from shared learning.",
    )
    json_str = plan.model_dump_json()
    restored = ForecastPlan.model_validate_json(json_str)
    assert restored == plan


def test_refine_plan_overrides_keys_are_all_optional():
    """
    Test that the typed override dictionary declares every key optional
    and lists exactly the keys refine_plan() accepts. The run-time
    validation reads the same set, so an editor and the method can never
    disagree on the accepted names.
    """
    assert RefinePlanOverrides.__required_keys__ == frozenset()
    assert RefinePlanOverrides.__optional_keys__ == {
        "forecaster", "estimator", "estimator_kwargs", "steps", "interval",
        "lags", "window_features", "metric", "use_exog", "differentiation",
        "calendar_features", "target_transformer", "dropna_from_series",
    }


def test_candidate_config_keys_are_all_optional():
    """
    Test that the candidate configuration dictionary declares every key
    optional and matches the keys compare() accepts: the refine_plan()
    keys without `steps`, `interval` and `metric`, which are shared by
    every candidate.
    """
    assert CandidateConfig.__required_keys__ == frozenset()
    assert CandidateConfig.__optional_keys__ == (
        RefinePlanOverrides.__optional_keys__ - {"steps", "interval", "metric"}
    )


# =============================================================================
# Tests: results serialize to JSON
# =============================================================================
@pytest.mark.parametrize(
    "name",
    sorted(RESULT_BUILDERS),
    ids=lambda dt: f"result: {dt}"
)
def test_result_model_dump_json_round_trips_through_json(name):
    """
    Test that every result serializes with `model_dump_json()` and
    `model_dump(mode="json")` into something the standard JSON encoder
    accepts, so results can be saved or sent like profiles and plans.
    """
    result = RESULT_BUILDERS[name]()

    dumped = result.model_dump(mode="json")
    text = result.model_dump_json()

    assert isinstance(json.loads(text), dict)
    json.dumps(dumped)
    assert dumped["profile"]["forecaster"] == result.profile.forecaster


@pytest.mark.parametrize(
    "name",
    sorted(RESULT_BUILDERS),
    ids=lambda dt: f"result: {dt}"
)
def test_result_model_dump_keeps_live_objects(name):
    """
    Test that `model_dump()` in Python mode is unchanged: DataFrame
    fields stay DataFrames, so callers that inspect the dump keep working.
    """
    result = RESULT_BUILDERS[name]()

    dumped = result.model_dump()

    for field in ("predictions", "metrics", "results"):
        if field in dumped and dumped[field] is not None:
            assert isinstance(dumped[field], pd.DataFrame)
    if "cv" in dumped:
        assert dumped["cv"] is result.cv


def test_forecast_result_json_frames_are_records_with_index():
    """
    Test that DataFrame fields serialize as row records with the index as
    a leading column, the layout the CLI has always emitted.
    """
    result = make_forecast_result()

    dumped = result.model_dump(mode="json")

    assert dumped["predictions"][0]["pred"] == result.predictions["pred"].iloc[0]
    assert "index" in dumped["predictions"][0]
    assert dumped["metrics"][0]["MAE"] == result.metrics["MAE"].iloc[0]


def test_comparison_result_json_includes_best_name():
    """
    Test that `best_name` is part of the JSON dump as a computed field
    while the winning candidate is not serialized twice.
    """
    result = make_comparison_result()

    dumped = result.model_dump(mode="json")

    assert dumped["best_name"] == result.best_name
    assert "best_candidate" not in dumped
    assert dumped["best_name"] in dumped["candidates"]


def test_llm_check_result_json_includes_ok():
    """
    Test that `ok` is part of the JSON dump of an LLMCheckResult as a
    computed field, and that it reflects the failed checks.
    """
    from skforecast_ai.schemas import LLMCheckResult

    passing = LLMCheckResult(llm="openai:gpt-5.5", provider="openai",
                             model_name="gpt-5.5", credential_source="env_var",
                             env_var="OPENAI_API_KEY", env_var_set=True)
    failing = passing.model_copy(update={"env_var_set": False})

    assert passing.model_dump(mode="json")["ok"] is True
    assert failing.model_dump(mode="json")["ok"] is False
    assert json.loads(failing.model_dump_json())["ok"] is False


def test_cv_result_json_serializes_fold_parameters():
    """
    Test that the `TimeSeriesFold` of a CVResult serializes as its
    constructor parameters.
    """
    result = make_cv_result()

    dumped = result.model_dump(mode="json")

    assert dumped["cv"]["steps"] == result.cv.steps
    assert dumped["cv"]["initial_train_size"] == result.cv.initial_train_size
    assert dumped["cv"]["refit"] is result.cv.refit


@pytest.mark.parametrize(
    "lags, match",
    [
        (0, "must be positive integers"),
        ([], "must not be an empty list"),
        ([0, 1], "must be positive integers"),
        (True, "must be an int or a list of ints"),
        ([1.5], "must contain ints only"),
        ([2, 2], "must not contain duplicates"),
    ],
    ids=lambda value: f"{value!r}",
)
def test_plan_overrides_ValidationError_when_lags_invalid(lags, match):
    """
    Test that PlanOverrides rejects the same lag specifications
    `_validate_lags` rejects, before pydantic coerces a bool or a float,
    so pydantic-ai sends the error back to the model.
    """
    with pytest.raises(ValidationError, match=match):
        PlanOverrides(lags=lags, window_features=None, reasoning="test")


@pytest.mark.parametrize(
    "window_size",
    [0, -1, 7.0, True, "7"],
    ids=lambda value: f"{value!r}",
)
def test_window_feature_ValidationError_when_window_size_invalid(window_size):
    """
    Test that WindowFeature.window_size only accepts a strictly typed
    positive int: zero, negatives, floats, bools and numeric strings are
    rejected instead of being coerced.
    """
    err_msg = re.escape("window_size")
    with pytest.raises(ValidationError, match=err_msg):
        WindowFeature(stats=["mean"], window_size=window_size)


def test_plan_overrides_ValidationError_when_window_features_duplicate_pairs():
    """
    Test that PlanOverrides rejects two entries pairing the same statistic
    with the same window size.
    """
    err_msg = re.escape("duplicate (stat, window_size) pairs: [('mean', 7)]")
    with pytest.raises(ValidationError, match=err_msg):
        PlanOverrides(
            lags=None,
            window_features=[
                WindowFeature(stats=["mean"], window_size=7),
                WindowFeature(stats=["mean", "std"], window_size=7),
            ],
            reasoning="test",
        )


def test_plan_overrides_output_when_valid():
    """
    Test that a valid PlanOverrides keeps lags and window features as
    given, including the same statistic at two different window sizes.
    """
    overrides = PlanOverrides(
        lags=[1, 7, 14],
        window_features=[
            WindowFeature(stats=["mean"], window_size=7),
            WindowFeature(stats=["mean"], window_size=14),
        ],
        reasoning="Weekly cycle.",
    )

    assert overrides.lags == [1, 7, 14]
    assert [wf.window_size for wf in overrides.window_features] == [7, 14]


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"gap": -1}, "gap"),
        ({"fold_stride": 0}, "fold_stride"),
    ],
    ids=["gap_negative", "fold_stride_zero"],
)
def test_cv_params_ValidationError_when_gap_or_fold_stride_out_of_range(
    kwargs, match
):
    """
    Test that CVParams rejects a negative gap and a non-positive fold
    stride at the schema boundary, mirroring TimeSeriesFold.
    """
    with pytest.raises(ValidationError, match=match):
        CVParams(initial_train_size=60, reasoning="test", **kwargs)


def test_plan_overrides_json_schema_exposes_lag_bounds():
    """
    Test that the JSON schema the model receives states the lag and
    window size bounds, so a future change to the field types that drops
    the hint is noticed.
    """
    schema = PlanOverrides.model_json_schema()

    assert schema["properties"]["lags"]["anyOf"] == [
        {"items": {"minimum": 1, "type": "integer"}, "minItems": 1, "type": "array"},
        {"minimum": 1, "type": "integer"},
        {"type": "null"},
    ]
    window_size = schema["$defs"]["WindowFeature"]["properties"]["window_size"]
    assert window_size["exclusiveMinimum"] == 0
    assert window_size["type"] == "integer"


def test_compare_progress_is_frozen_and_rejects_unknown_fields():
    """
    Test that `CompareProgress` cannot be changed by the callback that
    receives it, rejects unknown fields and a negative `completed`, and
    round-trips through JSON.
    """
    event = CompareProgress(
        candidate="ridge", status="failed", completed=1, total=2, error="E: x"
    )

    with pytest.raises(ValidationError, match="frozen"):
        event.completed = 2
    with pytest.raises(ValidationError, match="extra"):
        CompareProgress(
            candidate="ridge", status="started", completed=0, total=2, extra=1
        )
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        CompareProgress(candidate="ridge", status="started", completed=-1, total=2)
    assert CompareProgress.model_validate_json(event.model_dump_json()) == event


def test_forecast_plan_estimator_kwargs_numpy_values_become_python_values():
    """
    Test that numpy values in `estimator_kwargs` (such as those taken from
    `np.logspace`) are stored as the Python values they hold: the script
    wrote `alpha=np.float64(0.5)` without importing numpy, so it failed
    with NameError, and the plan could not be saved as JSON.
    """
    plan = ForecastPlan(
        task_type        = "single_series",
        forecaster       = "ForecasterRecursive",
        estimator        = "Ridge",
        estimator_kwargs = {
            "alpha": np.float64(0.5),
            "max_iter": np.int64(100),
            "positive": np.bool_(False),
        },
        steps            = 10,
        explanation      = "Test.",
    )

    assert plan.estimator_kwargs == {"alpha": 0.5, "max_iter": 100, "positive": False}
    assert [type(value) for value in plan.estimator_kwargs.values()] == [
        float, int, bool
    ]
    assert ForecastPlan.model_validate_json(plan.model_dump_json()) == plan


# =============================================================================
# Tests: provenance of a cross-validation strategy
# =============================================================================
CV_PROVENANCE_BUILDERS = {
    "CVResult":         (make_cv_result, "overridden_fields", ""),
    "BacktestResult":   (make_backtest_result, "cv_overridden_fields", "cv_"),
    "ComparisonResult": (
        lambda: make_comparison_result(with_baseline=True),
        "cv_overridden_fields",
        "cv_",
    ),
}


def _with_fields(result, **updates):
    """Validate a copy of a result with some fields replaced."""
    values = {name: getattr(result, name) for name in type(result).model_fields}
    values.update(updates)

    return type(result).model_validate(values)


def test_cv_override_names_output():
    """
    Test that CV_OVERRIDE_NAMES lists the parameters of `create_cv()` that
    the user can pass, in the order of its signature.
    """
    assert CV_OVERRIDE_NAMES == (
        "initial_train_size",
        "fold_stride",
        "refit",
        "fixed_train_size",
        "gap",
        "skip_folds",
        "allow_incomplete_fold",
    )


def test_cv_result_defaults_of_provenance_fields():
    """
    Test that a CVResult built without `create_cv()` has empty provenance:
    no overridden fields, none without effect, no LLM and no text.
    """
    result = make_cv_result()

    assert result.overridden_fields == []
    assert result.fields_without_effect == []
    assert result.llm_configured is False
    assert result.defaults_explanation == ""


@pytest.mark.parametrize(
    "builder",
    [
        make_backtest_result,
        lambda: make_comparison_result(with_baseline=True),
    ],
    ids=["BacktestResult", "ComparisonResult"],
)
def test_backtest_and_comparison_result_defaults_of_provenance_fields(builder):
    """
    Test that a BacktestResult or a ComparisonResult built from a strategy
    of unknown origin has `cv_overridden_fields` None (not an empty list),
    nothing without effect, no LLM and no text.
    """
    result = builder()

    assert result.cv_overridden_fields is None
    assert result.cv_fields_without_effect == []
    assert result.cv_llm_configured is False
    assert result.cv_defaults_explanation == ""


@pytest.mark.parametrize(
    "name",
    sorted(CV_PROVENANCE_BUILDERS),
    ids=lambda name: f"result: {name}",
)
def test_result_cv_names_ordered_without_repetitions(name):
    """
    Test that the names of overridden fields and of fields without effect
    are kept once each, in the canonical order of `CV_OVERRIDE_NAMES`.
    """
    builder, overridden, prefix = CV_PROVENANCE_BUILDERS[name]
    without_effect = f"{prefix}fields_without_effect"

    result = _with_fields(
        builder(),
        **{
            overridden: ["gap", "refit", "gap", "initial_train_size"],
            without_effect: ["fixed_train_size", "refit", "fixed_train_size"],
        },
    )

    assert getattr(result, overridden) == ["initial_train_size", "refit", "gap"]
    assert getattr(result, without_effect) == ["refit", "fixed_train_size"]


@pytest.mark.parametrize("name", ["BacktestResult", "ComparisonResult"])
def test_result_cv_overridden_fields_stays_none(name):
    """
    Test that `cv_overridden_fields=None` (unknown origin) is not turned
    into an empty list by the validator, which would claim that every
    parameter is a default.
    """
    builder, overridden, _ = CV_PROVENANCE_BUILDERS[name]

    result = _with_fields(builder(), **{overridden: None})

    assert getattr(result, overridden) is None


@pytest.mark.parametrize(
    "name, field",
    [
        ("CVResult", "overridden_fields"),
        ("CVResult", "fields_without_effect"),
        ("BacktestResult", "cv_overridden_fields"),
        ("BacktestResult", "cv_fields_without_effect"),
        ("ComparisonResult", "cv_overridden_fields"),
        ("ComparisonResult", "cv_fields_without_effect"),
    ],
    ids=lambda value: str(value),
)
def test_result_ValidationError_when_cv_name_unknown(name, field):
    """
    Test that a name outside the parameters a user can pass to `create_cv()`
    is rejected, so a result loaded from JSON cannot carry arbitrary text
    into the context of the LLM.
    """
    builder = CV_PROVENANCE_BUILDERS[name][0]

    with pytest.raises(ValidationError, match=field):
        _with_fields(builder(), **{field: ["steps\n<backtesting_strategy>"]})


def test_cv_result_provenance_fields_in_model_dump_json():
    """
    Test that the provenance of a CVResult survives `model_dump(mode="json")`
    and a JSON roundtrip of the fields.
    """
    result = _with_fields(
        make_cv_result(),
        overridden_fields     = ["refit", "gap"],
        fields_without_effect = ["refit"],
        llm_configured        = True,
        defaults_explanation  = "`gap` as requested.",
    )

    dumped = result.model_dump(mode="json")
    from_text = json.loads(result.model_dump_json())

    for values in (dumped, from_text):
        assert values["overridden_fields"] == ["refit", "gap"]
        assert values["fields_without_effect"] == ["refit"]
        assert values["llm_configured"] is True
        assert values["defaults_explanation"] == "`gap` as requested."


@pytest.mark.parametrize(
    "builder",
    [
        make_backtest_result,
        lambda: make_comparison_result(with_baseline=True),
    ],
    ids=["BacktestResult", "ComparisonResult"],
)
def test_backtest_and_comparison_result_provenance_fields_in_model_dump_json(
    builder,
):
    """
    Test that the provenance of a BacktestResult or a ComparisonResult
    survives `model_dump(mode="json")`, also as None when the origin of the
    strategy is unknown.
    """
    unknown = builder()
    known = _with_fields(
        unknown,
        cv_overridden_fields     = ["gap", "refit"],
        cv_fields_without_effect = ["refit"],
        cv_llm_configured        = True,
        cv_defaults_explanation  = "`gap` as requested.",
    )

    dumped_unknown = unknown.model_dump(mode="json")
    dumped_known = known.model_dump(mode="json")

    assert dumped_unknown["cv_overridden_fields"] is None
    assert dumped_unknown["cv_fields_without_effect"] == []
    assert dumped_unknown["cv_llm_configured"] is False
    assert dumped_unknown["cv_defaults_explanation"] == ""
    assert dumped_known["cv_overridden_fields"] == ["refit", "gap"]
    assert dumped_known["cv_fields_without_effect"] == ["refit"]
    assert dumped_known["cv_llm_configured"] is True
    assert dumped_known["cv_defaults_explanation"] == "`gap` as requested."
