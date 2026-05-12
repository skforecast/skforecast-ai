"""Pydantic AI agent definition and tools for forecasting assistance."""

from pydantic_ai import Agent, RunContext

from ..generation.code_templates import (
    _template_foundation,
    _template_multi_series,
    _template_multivariate,
    _template_single_series,
    _template_statistical,
)
from ..profiling.data_profile import create_data_profile
from ..profiling.analysis import create_forecaster_analysis
from ..recommendation import (
    _build_profile_explanation,
    build_plan_explanation,
    build_forecaster_kwargs,
    check_exog_usage,
    select_dropna_from_series,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_lags_and_window_features,
    select_task_type_from_forecaster,
    select_transformer_exog,
    select_transformer_series,
)
from ..recommendation import derive_preprocessing_steps
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
        context = create_forecaster_analysis(None, data_profile, fc)
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
            transformer_series = None
            transformer_exog = None
            dropna_from_series = None
        else:
            lags, window_features = select_lags_and_window_features(
                n_observations = context.effective_n_observations,
                frequency      = data_profile.frequency,
                target_series  = context.target_series,
            )
            transformer_series = select_transformer_series(est, task_type)
            transformer_exog = select_transformer_exog(
                estimator        = est,
                task_type        = task_type,
                exog_columns     = data_profile.exog_columns,
                categorical_exog = data_profile.categorical_exog,
            )
            dropna_from_series = select_dropna_from_series(
                est, data_profile.missing_target,
                data_profile.missing_exog, task_type,
            )

        forecaster_kwargs = build_forecaster_kwargs(
            forecaster         = fc,
            task_type          = task_type,
            steps              = steps,
            lags               = lags,
            window_features    = window_features,
            transformer_series = transformer_series,
            transformer_exog   = transformer_exog,
            dropna_from_series = dropna_from_series,
        )

        use_exog            = check_exog_usage(data_profile.exog_columns)
        preprocessing_steps = derive_preprocessing_steps(data_profile, fc)

        explanation = build_plan_explanation(
            forecaster         = fc,
            estimator          = est,
            lags               = lags,
            window_features    = window_features,
            interval_method    = None,
            dropna_from_series = dropna_from_series,
            use_exog           = use_exog,
        )

        return ForecastPlan(
            task_type           = task_type,
            forecaster          = fc,
            estimator           = est,
            steps               = steps,
            frequency           = data_profile.frequency,
            forecaster_kwargs   = forecaster_kwargs,
            interval_method     = None,
            use_exog            = use_exog,
            preprocessing_steps = preprocessing_steps,
            explanation         = explanation,
        )

    @agent.tool
    async def generate_code_tool(
        ctx: RunContext[None],
        plan: ForecastPlan,
        profile: DataProfile,
    ) -> str:
        """Produce a complete Python script from a forecast plan and profile."""
        dispatch = {
            "single_series": _template_single_series,
            "multi_series": _template_multi_series,
            "multivariate": _template_multivariate,
            "statistical": _template_statistical,
            "foundation": _template_foundation,
        }
        template_fn = dispatch.get(plan.task_type)
        if template_fn is None:
            supported = list(dispatch.keys())
            raise ValueError(
                f"Unsupported task_type '{plan.task_type}'. "
                f"Supported types: {supported}"
            )
        return template_fn(plan, profile, profile.data_path)

    return agent
