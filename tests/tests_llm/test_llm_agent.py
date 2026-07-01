# Unit test agent skforecast_ai.llm

import re

import pytest

from skforecast_ai.llm.context import build_context_message
from skforecast_ai.llm.skills import load_llms_reference, load_skill


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
    Test that load_llms_reference returns the content of llms-base.txt
    containing skforecast API information.
    """
    result = load_llms_reference()
    assert isinstance(result, str)
    assert "Skforecast" in result or "skforecast" in result
    # Reference ships a skforecast version string (e.g. "0.23.0"); assert the
    # series prefix without pinning an exact patch that changes on every bump.
    assert "0.2" in result


def test_build_context_message_empty_when_no_args():
    """
    Test that build_context_message returns empty string when both
    arguments are None.
    """
    assert build_context_message() == ""


def test_build_context_message_includes_profile_fields():
    """
    Test that build_context_message includes key profile fields when a
    ForecastingProfile is provided.
    """
    from skforecast_ai.schemas import (
        DataProfile,
        ForecastingProfile,
    )

    dp = DataProfile(
        n_series=1,
        series_lengths={"y": 200},
        target="y",
        index_type="datetime",
        frequency="D",
        exog_columns=["temp"],
        warnings=[],
    )
    profile = ForecastingProfile(
        data_profile=dp,
        task_type="single_series",
        forecaster="ForecasterRecursive",
        forecaster_candidates=["ForecasterRecursive"],
        estimator="LGBMRegressor",
        estimator_candidates=["LGBMRegressor"],
        series_pacf=[],
        window_features=None,
        explanation="A single-series ML forecaster (ForecasterRecursive) is recommended. Estimator: LGBMRegressor.",
    )

    result = build_context_message(profile=profile)
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

    agent = create_forecasting_agent(model=TestModel())
    assert isinstance(agent, pydantic_ai.Agent)


def test_agent_returns_str():
    """
    Test that the agent produces a plain string response (output_type=str)
    when run with TestModel.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.test import TestModel

    from skforecast_ai.llm.agent import AskDeps, create_forecasting_agent

    agent = create_forecasting_agent(model=TestModel())

    deps = AskDeps(
        profile=None,
        plan=None,
        question="What is skforecast?",
        include_reference=False,
        skills_override=["choosing-a-forecaster"],
    )
    result = agent.run_sync("What is skforecast?", deps=deps)
    assert isinstance(result.output, str)


def test_agent_has_no_tools():
    """
    Test that the forecasting agent has no tools registered.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.test import TestModel

    from skforecast_ai.llm.agent import create_forecasting_agent

    agent = create_forecasting_agent(model=TestModel())

    tool_names = set(agent._function_toolset.tools.keys())
    assert len(tool_names) == 0


def test_plan_refinement_agent_injects_max_allowed_budget():
    """
    Test that the plan refinement agent's dynamic instructions surface the
    concrete data-budget hard limit derived from span_index_length, so the
    LLM does not have to compute it from the vague 0.33 rule.
    """
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from skforecast_ai import ForecastingAssistant
    from skforecast_ai.llm.agent import PlanRefinementDeps, create_plan_refinement_agent

    from tests.fixtures_assistant import df_single

    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    captured = {}

    def respond(messages, info):
        captured["instructions"] = info.instructions
        tool_name = info.output_tools[0].name
        return ModelResponse(
            parts=[ToolCallPart(
                tool_name=tool_name,
                args={"lags": [1, 2], "window_features": None, "reasoning": "ok"},
            )]
        )

    agent = create_plan_refinement_agent(FunctionModel(respond))
    deps = PlanRefinementDeps(profile=profile, plan=plan, prompt="weekly seasonality")
    agent.run_sync("weekly seasonality", deps=deps)

    # 100 observations -> budget is int(100 * 0.33) = 33.
    assert "Max allowed lag / window size (hard limit): 33" in captured["instructions"]
