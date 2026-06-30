import pytest
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.console import Group

from skforecast_ai._display import (
    render_code,
    render_explanation,
    render_dataframe,
    render_metrics,
    render_profile,
    render_plan,
    render_cv_config,
)
from skforecast_ai.schemas.profiles import ForecastingProfile, DataProfile
from skforecast_ai.schemas.plans import ForecastPlan
from skforecast_ai.schemas.results import (
    CodeGenerationResult,
    AskResult,
    ForecastResult,
    BacktestResult,
)


@pytest.fixture
def sample_dataframe():
    return pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})


@pytest.fixture
def sample_metrics():
    return pd.DataFrame({"MAE": [1.5], "MSE": [2.5]})


@pytest.fixture
def sample_profile():
    return ForecastingProfile(
        data_profile=DataProfile(
            target="target_col",
            date_column="date",
            frequency="D",
            rows=100,
            columns=2,
            missing_values=0,
            exog_columns=["exog1"],
            n_series=1,
            series_lengths={"target_col": 100},
            index_type="datetime",
        ),
        task_type="single_series",
        forecaster="ForecasterAutoreg",
        estimator="RandomForestRegressor",
        estimator_kwargs={"n_estimators": 100},
        lag_selection="lags=10",
        preprocessing=["StandardScaler()"],
        explanation="Sample explanation",
    )


@pytest.fixture
def sample_plan():
    return ForecastPlan(
        forecaster="ForecasterAutoreg",
        estimator="RandomForestRegressor",
        estimator_kwargs={"n_estimators": 100},
        steps=10,
        interval=[0.1, 0.9],
        lag_selection="lags=10",
        preprocessing=["StandardScaler()"],
        explanation="Sample explanation",
        task_type="single_series",
    )


def test_render_code():
    code = "print('hello')"
    result = render_code(code, title=None)
    assert isinstance(result, Syntax)
    assert result.code == code


def test_render_explanation():
    text = "This is a test explanation."
    result = render_explanation(text)
    assert isinstance(result, Panel)


def test_render_dataframe(sample_dataframe):
    result = render_dataframe(sample_dataframe, title="Test DF")
    assert isinstance(result, Panel)


def test_render_metrics(sample_metrics):
    result = render_metrics(sample_metrics)
    assert isinstance(result, Table)


def test_render_profile(sample_profile):
    result = render_profile(sample_profile)
    assert isinstance(result, Group)


def test_render_plan(sample_plan):
    result = render_plan(sample_plan)
    assert isinstance(result, Group)


def test_render_cv_config():
    cv_config = {"initial_train_size": 50, "steps": 10, "refit": False}
    result = render_cv_config(cv_config)
    assert isinstance(result, Table)


class TestDisplayMixin:
    def test_forecast_plan_display(self, sample_plan):
        sample_plan.show()
        mimebundle = sample_plan._repr_mimebundle_(include=[], exclude=[])
        assert "text/html" in mimebundle
        assert "<pre" in mimebundle["text/html"]

    def test_forecasting_profile_display(self, sample_profile):
        sample_profile.show()
        mimebundle = sample_profile._repr_mimebundle_(include=[], exclude=[])
        assert "text/html" in mimebundle
        assert "<pre" in mimebundle["text/html"]

    def test_code_generation_result_display(self, sample_profile, sample_plan):
        result = CodeGenerationResult(
            code="print('test')",
            profile=sample_profile,
            plan=sample_plan,
        )
        # Test .show() doesn't crash
        result.show()
        
        # Test _repr_html_ returns non-empty string
        mimebundle = result._repr_mimebundle_(include=[], exclude=[])
        assert "text/html" in mimebundle
        assert "<pre" in mimebundle["text/html"]

    def test_ask_result_display(self, sample_profile, sample_plan):
        result = AskResult(
            explanation="Test answer",
            code="print('test')",
            profile=sample_profile,
            plan=sample_plan,
        )
        result.show()
        mimebundle = result._repr_mimebundle_(include=[], exclude=[])
        assert "text/html" in mimebundle
        assert "<pre" in mimebundle["text/html"]

    def test_forecast_result_display(self, sample_profile, sample_plan, sample_metrics, sample_dataframe):
        result = ForecastResult(
            code="print('test')",
            profile=sample_profile,
            plan=sample_plan,
            metrics=sample_metrics,
            predictions=sample_dataframe,
        )
        result.show()
        mimebundle = result._repr_mimebundle_(include=[], exclude=[])
        assert "text/html" in mimebundle
        assert "<pre" in mimebundle["text/html"]

    def test_backtest_result_display(self, sample_profile, sample_plan, sample_metrics, sample_dataframe):
        result = BacktestResult(
            explanation="Test backtest",
            cv_config={"initial_train_size": 50, "steps": 10, "refit": False},
            metrics=sample_metrics,
            predictions=sample_dataframe,
            code="print('test')",
            profile=sample_profile,
            plan=sample_plan,
        )
        result.show()
        mimebundle = result._repr_mimebundle_(include=[], exclude=[])
        assert "text/html" in mimebundle
        assert "<pre" in mimebundle["text/html"]
