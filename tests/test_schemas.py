# Unit test schemas skforecast_ai

import re

import pytest
from pydantic import ValidationError

from skforecast_ai.schemas import DataProfile, ForecastPlan


def test_data_profile_invalid_index_type():
    """
    Test DataProfile raises ValidationError when index_type is not a valid
    Literal value.
    """
    err_msg = re.escape("index_type")
    with pytest.raises(ValidationError, match=err_msg):
        DataProfile(
            n_series=1,
            n_observations=100,
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
            metric="mean_absolute_error",
            backtesting_strategy="TimeSeriesFold",
            rationale="Test.",
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
            metric="mean_absolute_error",
            backtesting_strategy="TimeSeriesFold",
            rationale="Test.",
        )


def test_data_profile_minimal():
    """
    Test DataProfile can be created with only required fields and defaults
    are correctly assigned.
    """
    profile = DataProfile(
        n_series=1,
        n_observations=100,
        target="y",
        index_type="datetime",
    )
    assert profile.n_observations == 100
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


def test_data_profile_full():
    """
    Test DataProfile with all fields populated.
    """
    profile = DataProfile(
        n_series=3,
        n_observations=500,
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


def test_forecast_plan_minimal():
    """
    Test ForecastPlan can be created with only required fields and defaults
    are correctly assigned.
    """
    plan = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        steps=24,
        metric="mean_absolute_error",
        backtesting_strategy="TimeSeriesFold",
        rationale="Single univariate series with regular frequency.",
    )
    assert plan.task_type == "single_series"
    assert plan.forecaster == "ForecasterRecursive"
    assert plan.steps == 24
    assert plan.estimator is None
    assert plan.lags is None
    assert plan.interval_method is None
    assert plan.use_exog is False
    assert plan.data_requirements == []
    assert plan.warnings == []


def test_data_profile_json_roundtrip():
    """
    Test DataProfile survives a model_dump_json -> model_validate_json
    roundtrip without data loss.
    """
    profile = DataProfile(
        n_series=1,
        n_observations=200,
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
        estimator="LGBMRegressor",
        steps=12,
        frequency="ME",
        lags=[1, 2, 3, 12],
        metric="mean_squared_error",
        backtesting_strategy="TimeSeriesFold",
        interval_method="bootstrapping",
        use_exog=True,
        data_requirements=["At least 2 complete seasonal cycles"],
        warnings=["High cardinality in series_id"],
        rationale="Multiple correlated series benefit from shared learning.",
    )
    json_str = plan.model_dump_json()
    restored = ForecastPlan.model_validate_json(json_str)
    assert restored == plan
