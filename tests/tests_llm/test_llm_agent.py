# Unit test agent skforecast_ai.llm

import re

import pytest

from skforecast_ai.llm.prompts import (
    build_explain_prompt,
    build_system_prompt,
    load_llms_reference,
    load_skill,
)
from skforecast_ai.schemas import DataProfile, ForecastPlan

profile_single_daily = DataProfile(
    n_observations=365,
    n_series=1,
    index_type="datetime",
    frequency="D",
    target="sales",
    date_column="date",
    exog_columns=["temperature", "promotion"],
    categorical_exog=["promotion"],
    missing_values={},
    inferred_seasonalities=[7, 365],
    warnings=[],
)

plan_single_recursive = ForecastPlan(
    task_type="single_series",
    forecaster="ForecasterRecursive",
    estimator="LGBMRegressor",
    horizon=10,
    frequency="D",
    lags=[1, 2, 3, 4, 5, 6, 7],
    metric="mean_absolute_error",
    backtesting_strategy="TimeSeriesFold",
    interval_method="bootstrapping",
    use_exog=True,
    data_requirements=["impute_missing", "encode_categorical"],
    warnings=[],
    rationale="Single daily series with exogenous variables.",
)


def test_load_skill_FileNotFoundError_when_skill_does_not_exist():
    """
    Test that load_skill raises FileNotFoundError when the skill directory
    does not exist.
    """
    msg = re.escape("Skill 'nonexistent-skill' not found.")
    with pytest.raises(FileNotFoundError, match=msg):
        load_skill("nonexistent-skill")


def test_load_skill_output_when_valid_skill():
    """
    Test that load_skill returns a string containing the skill's SKILL.md
    content for a valid skill name.
    """
    result = load_skill("choosing-a-forecaster")
    assert isinstance(result, str)
    assert "Choosing a Forecaster" in result
    assert len(result) > 100


def test_load_skill_output_includes_references():
    """
    Test that load_skill appends reference files from the skill's
    references subdirectory when they exist.
    """
    result = load_skill("feature-engineering")
    assert "Reference:" in result


def test_load_llms_reference_output():
    """
    Test that load_llms_reference returns the content of llms-full.txt
    containing skforecast API information.
    """
    result = load_llms_reference()
    assert isinstance(result, str)
    assert "Skforecast" in result or "skforecast" in result
    assert "0.22" in result


def test_build_system_prompt_includes_skills():
    """
    Test that build_system_prompt includes skill content when specific
    skills are requested.
    """
    result = build_system_prompt(
        skills=["choosing-a-forecaster"],
        include_reference=False,
    )
    assert "Choosing a Forecaster" in result
    assert "forecasting assistant" in result
    assert "(Reference not included)" in result


def test_build_system_prompt_includes_reference():
    """
    Test that build_system_prompt includes the llms-full.txt API reference
    when include_reference is True.
    """
    result = build_system_prompt(
        skills=["choosing-a-forecaster"],
        include_reference=True,
    )
    assert "Skforecast" in result or "skforecast" in result
    assert "(Reference not included)" not in result


def test_build_system_prompt_includes_default_skills_when_none():
    """
    Test that build_system_prompt loads DEFAULT_SKILLS when the skills
    parameter is None.
    """
    result = build_system_prompt(skills=None, include_reference=False)
    assert "choosing-a-forecaster" in result
    assert "forecasting-single-series" in result
    assert "forecasting-multiple-series" in result


def test_build_system_prompt_includes_all_skills_when_explicit():
    """
    Test that build_system_prompt loads all skills when ALL_SKILLS is
    passed explicitly.
    """
    from skforecast_ai.llm.prompts import ALL_SKILLS

    result = build_system_prompt(skills=ALL_SKILLS, include_reference=False)
    assert "choosing-a-forecaster" in result
    assert "statistical-models" in result
    assert "deep-learning-forecasting" in result


def test_build_explain_prompt_uses_plan():
    """
    Test that build_explain_prompt produces a prompt string containing
    key fields from both the plan and profile.
    """
    result = build_explain_prompt(plan_single_recursive, profile_single_daily)
    assert "ForecasterRecursive" in result
    assert "single_series" in result
    assert "365" in result
    assert "LGBMRegressor" in result
    assert "mean_absolute_error" in result
    assert "temperature" in result


def test_create_forecasting_agent_returns_agent():
    """
    Test that create_forecasting_agent returns a Pydantic AI Agent
    instance configured with the correct output type.
    """
    pydantic_ai = pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.test import TestModel

    from skforecast_ai.llm.agent import create_forecasting_agent

    agent = create_forecasting_agent(
        model=TestModel(),
        skills=["choosing-a-forecaster"],
        include_reference=False,
    )
    assert isinstance(agent, pydantic_ai.Agent)


def test_agent_tools_registered():
    """
    Test that the forecasting agent has the three expected tools
    registered (profile_data, recommend, generate_code_tool).
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.test import TestModel

    from skforecast_ai.llm.agent import create_forecasting_agent

    agent = create_forecasting_agent(
        model=TestModel(),
        skills=["choosing-a-forecaster"],
        include_reference=False,
    )

    tool_names = set(agent._function_toolset.tools.keys())
    assert "profile_data" in tool_names
    assert "recommend" in tool_names
    assert "generate_code_tool" in tool_names


def test_agent_returns_forecast_plan():
    """
    Test that the agent produces a valid ForecastPlan when run with
    TestModel providing structured output without calling tools.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.test import TestModel

    from skforecast_ai.llm.agent import create_forecasting_agent

    agent = create_forecasting_agent(
        model=TestModel(call_tools=[]),
        skills=["choosing-a-forecaster"],
        include_reference=False,
    )

    result = agent.run_sync("Forecast daily sales for the next 10 days.")
    assert isinstance(result.output, ForecastPlan)
