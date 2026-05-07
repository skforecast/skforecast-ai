"""Pydantic AI agent definition and tools for forecasting assistance."""

from pydantic_ai import Agent, RunContext

from ..generation.code_templates import generate_code
from ..profiling.data_profile import create_data_profile
from ..profiling.analysis import create_analysis_context
from ..recommendation import (
    _build_profile_explanation,
    build_data_requirements,
    build_explanation,
    check_exog_usage,
    select_backtesting,
    select_dropna_from_series,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_interval_method,
    select_autoregressive,
    select_metric,
    select_task_type_from_forecaster,
)
from ..preparation import derive_preprocessing_steps
from ..schemas import DataProfile, ForecasterProfile, ForecastPlan
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
    async def build_forecaster_profile_tool(
        ctx: RunContext[None],
        data_profile: DataProfile,
    ) -> ForecasterProfile:
        """Select forecaster + estimator (with candidates) from a DataProfile."""
        fc, fc_candidates = select_forecaster_and_candidates(data_profile)
        task_type = select_task_type_from_forecaster(fc)
        context = create_analysis_context(None, data_profile, fc)
        est, est_candidates = select_estimator_and_candidates(
            task_type=task_type, n_observations=context.effective_n_observations
        )
        explanation = _build_profile_explanation(
            task_type=task_type,
            forecaster=fc,
            forecaster_candidates=fc_candidates,
            estimator=est,
            estimator_candidates=est_candidates,
            data_profile=data_profile,
        )
        return ForecasterProfile(
            data_profile          = data_profile,
            task_type             = task_type,
            forecaster            = fc,
            forecaster_candidates = fc_candidates,
            estimator             = est,
            estimator_candidates  = est_candidates,
            analysis_context      = context,
            explanation           = explanation,
        )

    @agent.tool
    async def generate_plan_tool(
        ctx: RunContext[None],
        forecaster_profile: ForecasterProfile,
        steps: int = 10,
    ) -> ForecastPlan:
        """Build a detailed ForecastPlan from a ForecasterProfile."""
        data_profile = forecaster_profile.data_profile
        context      = forecaster_profile.analysis_context
        task_type    = forecaster_profile.task_type
        fc           = forecaster_profile.forecaster
        est          = forecaster_profile.estimator

        if task_type in ("statistical", "foundation"):
            lags = None
            window_features = None
        else:
            lags, window_features = select_autoregressive(
                n_observations = context.effective_n_observations,
                frequency      = data_profile.frequency,
                target_series  = context.target_series,
            )

        metric               = select_metric(task_type)
        backtesting_strategy = select_backtesting(
            context.effective_n_observations, steps
        )
        interval_method      = select_interval_method(
            fc, context.effective_n_observations
        )
        dropna_from_series   = select_dropna_from_series(
            est, data_profile.missing_target, data_profile.missing_exog, task_type
        )
        use_exog             = check_exog_usage(data_profile.exog_columns)
        data_requirements    = build_data_requirements(data_profile)
        preprocessing_steps  = derive_preprocessing_steps(data_profile, fc)

        plan_warnings: list[str] = []
        if steps > data_profile.n_observations:
            plan_warnings.append(
                f"Forecast horizon ({steps}) exceeds available observations "
                f"({data_profile.n_observations})."
            )

        explanation = build_explanation(
            task_type, fc, est, lags, metric, interval_method, data_profile
        )

        return ForecastPlan(
            task_type            = task_type,
            forecaster           = fc,
            estimator            = est,
            steps                = steps,
            frequency            = data_profile.frequency,
            lags                 = lags,
            metric               = metric,
            backtesting_strategy = backtesting_strategy,
            interval_method      = interval_method,
            dropna_from_series   = dropna_from_series,
            use_exog             = use_exog,
            preprocessing_steps  = preprocessing_steps,
            data_requirements    = data_requirements,
            warnings             = plan_warnings,
            explanation          = explanation,
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
