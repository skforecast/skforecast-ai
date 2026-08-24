# Unit test schemas skforecast_ai

import re

import pytest
from pydantic import ValidationError

from skforecast_ai.schemas import DataProfile, ForecastPlan
from skforecast_ai.schemas.plans import PlanOverrides, WindowFeature


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


@pytest.mark.parametrize("window_size", [0, -3])
def test_window_feature_rejects_non_positive_window_size(window_size):
    """
    Test WindowFeature raises ValidationError when window_size is not > 0,
    so pydantic-ai blocks the value before it reaches the forecaster.
    """
    with pytest.raises(ValidationError, match=re.escape("window_size")):
        WindowFeature(stats=["mean"], window_size=window_size)


def test_window_feature_accepts_positive_window_size():
    """Test WindowFeature builds with a positive window_size."""
    wf = WindowFeature(stats=["mean"], window_size=7)
    assert wf.window_size == 7


@pytest.mark.parametrize("lags", [0, -1, [-1], [1, 0], [True], True])
def test_plan_overrides_rejects_non_positive_lags(lags):
    """
    Test PlanOverrides raises ValidationError for non-positive lags (scalar
    or any list element) and for booleans.
    """
    with pytest.raises(ValidationError, match="positive"):
        PlanOverrides(lags=lags, reasoning="x")


@pytest.mark.parametrize("lags", [None, 7, [1, 2, 7]])
def test_plan_overrides_accepts_valid_lags(lags):
    """Test PlanOverrides builds with None, a positive int, or positive ints."""
    overrides = PlanOverrides(lags=lags, reasoning="x")
    assert overrides.lags == lags


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
