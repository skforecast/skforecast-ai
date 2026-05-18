# Unit test agent skforecast_ai.llm

import re

import pytest

from skforecast_ai.llm.prompts import (
    build_context_message,
    build_system_prompt,
    load_llms_reference,
    load_skill,
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


def test_build_context_message_empty_when_no_args():
    """
    Test that build_context_message returns empty string when both
    arguments are None.
    """
    assert build_context_message() == ""


def test_build_context_message_includes_profile_fields():
    """
    Test that build_context_message includes key profile fields when a
    ForecasterProfile is provided.
    """
    from skforecast_ai.schemas import (
        DataProfile,
        ForecasterAnalysis,
        ForecasterProfile,
    )

    dp = DataProfile(
        n_series=1,
        n_observations=200,
        target="y",
        index_type="datetime",
        frequency="D",
        exog_columns=["temp"],
        warnings=[],
    )
    profile = ForecasterProfile(
        data_profile=dp,
        task_type="single_series",
        forecaster="ForecasterRecursive",
        forecaster_candidates=["ForecasterRecursive"],
        estimator="LGBMRegressor",
        estimator_candidates=["LGBMRegressor"],
        analysis_context=ForecasterAnalysis(effective_n_observations=200),
        explanation="Test explanation.",
    )

    result = build_context_message(forecaster_profile=profile)
    assert "200" in result
    assert "ForecasterRecursive" in result
    assert "LGBMRegressor" in result
    assert "temp" in result


def test_create_forecasting_agent_returns_agent():
    """
    Test that create_forecasting_agent returns a Pydantic AI Agent
    instance configured with output_type=str and no tools.
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


def test_agent_returns_str():
    """
    Test that the agent produces a plain string response (output_type=str)
    when run with TestModel.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.test import TestModel

    from skforecast_ai.llm.agent import create_forecasting_agent

    agent = create_forecasting_agent(
        model=TestModel(),
        skills=["choosing-a-forecaster"],
        include_reference=False,
    )

    result = agent.run_sync("What is skforecast?")
    assert isinstance(result.output, str)


def test_agent_has_no_tools():
    """
    Test that the forecasting agent has no tools registered.
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
    assert len(tool_names) == 0
