"""Pydantic AI agent definition and tools for forecasting assistance."""

from pydantic_ai import Agent, RunContext

from ..generation.code_templates import generate_code
from ..profiling.data_profile import create_data_profile
from ..recommendation.forecaster_selection import recommend_plan
from ..schemas import DataProfile, ForecastPlan
from .prompts import build_system_prompt


def create_forecasting_agent(
    model,
    skills: list[str] | None = None,
    include_reference: bool = True,
) -> Agent[None, ForecastPlan]:
    """
    Create a Pydantic AI agent configured for forecasting assistance.

    Parameters
    ----------
    model : str, Model
        Pydantic AI model instance or string identifier. Typically
        produced by `create_model()` from the provider module.
    skills : list, default None
        List of skill names to include in the system prompt. If None,
        all available skills are loaded.
    include_reference : bool, default True
        Whether to include the `llms-full.txt` API reference in the
        system prompt.

    Returns
    -------
    agent : Agent
        Configured Pydantic AI agent with forecasting tools registered.

    Notes
    -----
    The agent does NOT make forecasting decisions. It translates user
    intent into tool calls and explains the deterministic outputs.
    """
    system_prompt = build_system_prompt(
        skills=skills,
        include_reference=include_reference,
    )

    agent = Agent(
        model,
        output_type=ForecastPlan,
        system_prompt=system_prompt,
        retries=2,
    )

    @agent.tool
    async def profile_data(
        ctx: RunContext[None],
        data_path: str,
        target: str,
        date_column: str | None = None,
        series_id_column: str | None = None,
    ) -> DataProfile:
        """Inspect a dataset and return its profile with metadata and warnings."""
        return create_data_profile(
            data=data_path,
            target=target,
            date_column=date_column,
            series_id_column=series_id_column,
        )

    @agent.tool
    async def recommend(
        ctx: RunContext[None],
        profile: DataProfile,
        steps: int = 10,
        prefer_foundation: bool = False,
        prefer_statistical: bool = False,
    ) -> ForecastPlan:
        """Generate a deterministic forecasting plan from a data profile."""
        return recommend_plan(
            profile=profile,
            steps=steps,
            prefer_foundation=prefer_foundation,
            prefer_statistical=prefer_statistical,
        )

    @agent.tool
    async def generate_code_tool(
        ctx: RunContext[None],
        plan: ForecastPlan,
        profile: DataProfile,
        data_path: str = "data.csv",
    ) -> str:
        """Produce a complete Python script from a forecast plan and profile."""
        return generate_code(
            plan=plan,
            profile=profile,
            data_path=data_path,
        )

    return agent
