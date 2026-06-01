# Unit test render_backtesting_script execution/backtesting_runner

import pytest

from skforecast_ai.execution.backtesting_runner import render_backtesting_script
from skforecast_ai.schemas import ForecastPlan, RenderedScript

from .fixtures_execution import (
    cv_multi,
    cv_single,
    plan_multi,
    plan_short,
    plan_single,
    plan_statistical,
    profile_multi,
    profile_short,
    profile_single,
    profile_single_no_exog,
)


# Tests: render_backtesting_script — error handling


def test_render_backtesting_script_ValueError_when_unsupported_task_type():
    """
    Test that render_backtesting_script raises ValueError when the plan
    has an unsupported task_type, and the error message lists supported
    types.
    """
    plan_bad = ForecastPlan(
        task_type="single_series",
        forecaster="ForecasterRecursive",
        forecaster_kwargs={"lags": [1, 2, 3], "dropna_from_series": False},
        estimator="Ridge",
        steps=5,
        frequency="D",
        explanation="Bad task type.",
    )
    object.__setattr__(plan_bad, "task_type", "unsupported_type")

    with pytest.raises(ValueError, match="Unsupported task_type"):
        render_backtesting_script(
            profile=profile_single, plan=plan_bad, cv=cv_single
        )


# Tests: render_backtesting_script — single series output structure


def test_render_backtesting_script_single_series_returns_RenderedScript():
    """
    Test that render_backtesting_script returns a RenderedScript instance
    for a single-series plan.
    """
    rendered = render_backtesting_script(
        profile=profile_single, plan=plan_single, cv=cv_single
    )

    assert isinstance(rendered, RenderedScript)


def test_render_backtesting_script_single_series_imports_contain_skforecast():
    """
    Test that the rendered imports section contains skforecast imports
    necessary for backtesting.
    """
    rendered = render_backtesting_script(
        profile=profile_single, plan=plan_single, cv=cv_single
    )

    assert "skforecast" in rendered.imports
    assert "import" in rendered.imports


def test_render_backtesting_script_single_series_core_contains_backtesting_call():
    """
    Test that the rendered core section contains the backtesting_forecaster
    function call for a single-series plan.
    """
    rendered = render_backtesting_script(
        profile=profile_single, plan=plan_single, cv=cv_single
    )

    assert "backtesting_forecaster" in rendered.core


def test_render_backtesting_script_single_series_executable_excludes_data_loading():
    """
    Test that the executable property does not contain CSV file loading
    code (data is injected at runtime).
    """
    rendered = render_backtesting_script(
        profile=profile_single, plan=plan_single, cv=cv_single
    )

    assert "read_csv" not in rendered.executable


# Tests: render_backtesting_script — multi series


def test_render_backtesting_script_multi_series_contains_multiseries_call():
    """
    Test that the rendered core section contains the multiseries
    backtesting function call for a multi-series plan.
    """
    rendered = render_backtesting_script(
        profile=profile_multi, plan=plan_multi, cv=cv_multi
    )

    assert "backtesting_forecaster_multiseries" in rendered.core


# Tests: render_backtesting_script — statistical


def test_render_backtesting_script_statistical_contains_stats_call():
    """
    Test that the rendered core section contains the backtesting_stats
    function call for a statistical plan.
    """
    rendered = render_backtesting_script(
        profile=profile_single_no_exog, plan=plan_statistical, cv=cv_single
    )

    assert "backtesting_stats" in rendered.core


# Tests: render_backtesting_script — dispatch coverage


@pytest.mark.parametrize(
    "task_type, plan, profile, cv",
    [
        ("single_series", plan_single, profile_single, cv_single),
        ("multi_series", plan_multi, profile_multi, cv_multi),
        ("statistical", plan_statistical, profile_single_no_exog, cv_single),
    ],
    ids=["single_series", "multi_series", "statistical"],
)
def test_render_backtesting_script_dispatches_supported_task_types(
    task_type, plan, profile, cv
):
    """
    Test that render_backtesting_script dispatches correctly for each
    supported task_type and returns a RenderedScript.
    """
    rendered = render_backtesting_script(profile=profile, plan=plan, cv=cv)

    assert isinstance(rendered, RenderedScript)
    assert rendered.imports != ""
    assert rendered.core != ""
