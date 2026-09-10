# Unit test schemas skforecast_ai

import json
import re

import pandas as pd
import pytest
from pydantic import ValidationError

from skforecast_ai.schemas import (
    CandidateConfig,
    DataProfile,
    ForecastPlan,
    RefinePlanOverrides,
)

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
    "ComparisonResult":     make_comparison_result,
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
    assert profile.warnings == []
    assert profile.span_index_length == 100
    assert profile.n_total_observations == 100


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
        "lags", "window_features",
    }


def test_candidate_config_keys_are_all_optional():
    """
    Test that the candidate configuration dictionary declares every key
    optional and matches the keys compare() accepts: the refine_plan()
    keys without `steps` and `interval`, which are shared by every
    candidate.
    """
    assert CandidateConfig.__required_keys__ == frozenset()
    assert CandidateConfig.__optional_keys__ == (
        RefinePlanOverrides.__optional_keys__ - {"steps", "interval"}
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
