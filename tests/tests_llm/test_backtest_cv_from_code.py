# Unit test backtest_cv_from_code skforecast_ai.llm.context

import pandas as pd
import pytest

from skforecast_ai.execution.backtesting_runner import render_backtesting_script
from skforecast_ai.llm.context import backtest_cv_from_code, render_script_section

from tests.fixtures_llm import code_backtest_script
from tests.tests_rendering.fixtures_rendering import (
    cv_basic,
    plan_baseline,
    plan_foundation,
    plan_multi_series,
    plan_multivariate,
    plan_single_recursive,
    plan_statistical,
    profile_multi_long,
    profile_multi_wide,
    profile_single,
    profile_single_no_exog,
)


def _script(cv_call: str) -> str:
    """Wrap a `TimeSeriesFold` call in a minimal backtesting script."""
    return (
        "import pandas as pd\n"
        "from skforecast.model_selection import TimeSeriesFold\n"
        f"cv = {cv_call}\n"
        "metrics, predictions = backtesting_forecaster(cv=cv)\n"
    )


def test_backtest_cv_from_code_output_when_rendered_script():
    """
    Test that the splitter of a script rendered by `backtest_code()` is
    read with the values it writes.
    """
    cv = backtest_cv_from_code(code_backtest_script)

    assert cv.steps == 5
    assert cv.initial_train_size == 70
    assert cv.refit is False


@pytest.mark.parametrize(
    "cv_call, expected",
    [
        (
            "TimeSeriesFold(steps=3, initial_train_size=pd.Timestamp('2020-03-31'), "
            "refit=2, fixed_train_size=False, gap=1, skip_folds=[1, 2])",
            {
                "steps": 3,
                "initial_train_size": pd.Timestamp("2020-03-31"),
                "refit": 2,
                "fixed_train_size": False,
                "gap": 1,
                "skip_folds": [1, 2],
            },
        ),
        (
            "TimeSeriesFold(steps=4, initial_train_size='2020-03-31', refit=True)",
            {
                "steps": 4,
                "initial_train_size": "2020-03-31",
                "refit": True,
                "fixed_train_size": True,
            },
        ),
    ],
    ids=["timestamp, integer refit", "date string, refit"],
)
def test_backtest_cv_from_code_output_when_literal_arguments(cv_call, expected):
    """
    Test that every literal argument the renderer writes is read, the
    `pd.Timestamp('...')` of a date included, and that a script that
    refits keeps the default `fixed_train_size` of `TimeSeriesFold`.
    """
    cv = backtest_cv_from_code(_script(cv_call))

    for name, value in expected.items():
        assert getattr(cv, name) == value


@pytest.mark.parametrize(
    "code",
    [
        "forecaster.fit(y=y)\n",
        _script("TimeSeriesFold(steps=n_steps, initial_train_size=10)"),
        _script("TimeSeriesFold(steps=3, initial_train_size=pd.Timestamp(day))"),
        _script("TimeSeriesFold(steps=0, initial_train_size=10)"),
        _script("TimeSeriesFold(steps=3, initial_train_size=pd.Timestamp('garbage'))"),
        "cv = TimeSeriesFold(\n",
    ],
    ids=[
        "no splitter", "variable", "timestamp of a variable", "invalid",
        "timestamp that does not parse", "syntax error",
    ],
)
def test_backtest_cv_from_code_returns_none_when_not_readable(code):
    """
    Test that a script without a splitter, with an argument that is not a
    literal, with arguments `TimeSeriesFold` rejects, with a date edited by
    hand that does not parse (it raised `DateParseError` from describe()),
    or that does not compile gives None instead of running anything or
    raising.
    """
    assert backtest_cv_from_code(code) is None


@pytest.mark.parametrize(
    "plan, profile",
    [
        (plan_single_recursive, profile_single),
        (plan_multi_series, profile_multi_long),
        (plan_multivariate, profile_multi_wide),
        (plan_statistical, profile_single),
        (plan_foundation, profile_single),
        (plan_baseline, profile_single_no_exog),
    ],
    ids=[
        "single series", "multi-series", "multivariate", "statistical",
        "foundation", "baseline",
    ],
)
def test_backtest_cv_from_code_output_when_each_backtesting_renderer(plan, profile):
    """
    Test that the script of every backtesting renderer is read as a
    backtest: its splitter is found (with the refit that ForecasterStats
    runs) and its script section describes a backtest, so the description
    cannot drift from the renderers.
    """
    code = render_backtesting_script(profile=profile, plan=plan, cv=cv_basic).full_script

    cv = backtest_cv_from_code(code)
    section = render_script_section(plan, code)

    # ForecasterStats writes the strategy that skforecast runs: a refit in
    # every fold.
    expected_refit = plan.forecaster == "ForecasterStats"
    assert (cv.steps, cv.initial_train_size, cv.refit) == (10, 80, expected_refit)
    assert "- Mode: backtesting: " in section
