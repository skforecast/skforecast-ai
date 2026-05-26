"""ForecastingAssistant: unified public API for skforecast-ai."""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

from .exceptions import LLMRequiredError
from .execution import run_forecast
from .generation import generate_template
from .llm import (
    build_context_message,
    create_model,
    ensure_ollama_reachable,
    estimate_prompt_tokens,
    select_skills,
)
from .profiling import create_forecasting_analysis, create_data_profile
from .recommendation import (
    _build_profile_explanation,
    build_plan_explanation,
    build_forecaster_kwargs,
    check_exog_usage,
    derive_preprocessing_steps,
    select_dropna_from_series,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_lags_and_window_features,
    select_metric,
    select_task_type_from_forecaster,
    select_transformer_exog,
    select_transformer_series,
)
from .schemas import (
    AskResult,
    DataProfile,
    ForecastingProfile,
    ForecastPlan,
    CodeGenerationResult,
    ForecastResult,
)
from ._utils import _coerce_to_dataframe, _patch_event_loop, _strip_code_blocks


class ForecastingAssistant:
    """
    Unified forecasting assistant.

    Exposes a two-step deterministic workflow:

    1. `profile()` — inspects the dataset and returns a
       `ForecastingProfile` with the recommended forecaster + estimator
       and their compatible candidates.
    2. `generate_plan()` — takes the `ForecastingProfile` and produces a
       detailed `ForecastPlan` (lags, metric, backtesting, intervals,
       NaN handling, preprocessing).

    `generate_code()` and `forecast()` are convenience wrappers that
    chain the two stages plus code generation / execution. `ask()`
    provides an LLM-powered interface.

    Parameters
    ----------
    llm : str, default None
        LLM provider string in format `'provider:model_name'`. If None,
        only deterministic methods are available.
    base_url : str, default None
        Custom base URL for the LLM provider (used for Ollama or
        OpenAI-compatible endpoints).
    api_key : str, default None
        Explicit API key for the LLM provider. When None, Pydantic AI
        resolves credentials from environment variables (e.g.
        `OPENAI_API_KEY`, `GOOGLE_API_KEY`). Use this for notebook
        workflows or multi-tenant scenarios.
    send_data_to_llm : bool, default False
        Whether raw data may be sent to the LLM. When False, only
        metadata (schema, summary stats) is shared with the LLM.

    Attributes
    ----------
    llm : str, None
        LLM provider string or None for deterministic-only mode.
    base_url : str, None
        Custom base URL for the LLM provider.
    api_key : str, None
        Explicit API key or None (resolve from environment).
    send_data_to_llm : bool
        Whether raw data may be sent to the LLM.
    """

    def __init__(
        self,
        llm: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        send_data_to_llm: bool = False,
    ) -> None:
        
        self.llm = llm
        self.base_url = base_url
        self.api_key = api_key
        self.send_data_to_llm = send_data_to_llm
        self._model = None
        self._agent = None

    def profile(
        self,
        data: pd.DataFrame | str | Path,
        target: str | list[str],
        date_column: str | None = None,
        series_id_column: str | None = None,
    ) -> ForecastingProfile:
        """
        Profile a dataset and select the recommended forecaster + estimator.

        Wraps `create_data_profile` and `build_forecasting_profile` into a
        single call. The returned `ForecastingProfile` carries the
        `DataProfile` plus the coarse modeling decisions and their
        alternative candidates.

        Parameters
        ----------
        data : pandas DataFrame, str, Path
            Input dataset or path to a CSV file.
        target : str, list of str
            Name of the column to forecast. For wide-format multi-series,
            pass a list of column names where each column is a series.
        date_column : str, default None
            Name of the column containing timestamps.
        series_id_column : str, default None
            Name of the column identifying individual series.

        Returns
        -------
        profile : ForecastingProfile
            Dataset profile + recommended forecaster + estimator
            (with alternative candidates) + analysis context.
        """

        data_path = str(data) if isinstance(data, (str, Path)) else "data.csv"
        data = _coerce_to_dataframe(data)

        data_profile = create_data_profile(
            data             = data,
            target           = target,
            date_column      = date_column,
            series_id_column = series_id_column,
            data_path        = data_path,
        )

        forecaster, forecaster_candidates = select_forecaster_and_candidates(data_profile)
        task_type = select_task_type_from_forecaster(forecaster)
        analysis_context = create_forecasting_analysis(data, data_profile, forecaster)

        estimator, estimator_candidates = select_estimator_and_candidates(
            task_type=task_type, n_observations=analysis_context.effective_n_observations
        )

        explanation = _build_profile_explanation(
            task_type             = task_type,
            forecaster            = forecaster,
            forecaster_candidates = forecaster_candidates,
            estimator             = estimator,
            estimator_candidates  = estimator_candidates,
            data_profile          = data_profile,
        )

        return ForecastingProfile(
            data_profile          = data_profile,
            task_type             = task_type,
            forecaster            = forecaster,
            forecaster_candidates = forecaster_candidates,
            estimator             = estimator,
            estimator_candidates  = estimator_candidates,
            analysis_context      = analysis_context,
            explanation           = explanation,
        )

    def generate_plan(
        self,
        profile: ForecastingProfile,
        steps: int,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[int] | None = None,
    ) -> ForecastPlan:
        """
        Build a detailed `ForecastPlan` from a `ForecastingProfile`.

        Performs the fine-grained configuration (lags, prediction
        intervals, NaN handling, exogenous usage, preprocessing steps)
        without re-evaluating the coarse decisions already encoded in
        `profile`.

        Parameters
        ----------
        profile : ForecastingProfile
            Output of `profile()`.
        steps : int
            Forecast horizon (number of steps ahead to predict).
        forecaster : str, default None
            Explicit forecaster class name to override the profile
            recommendation. Must be in `profile.forecaster_candidates`.
        estimator : str, default None
            Explicit estimator class name to override the profile
            recommendation (e.g. `'HistGradientBoostingRegressor'`).
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200, 'learning_rate': 0.05}`). Merged
            on top of built-in defaults (`random_state`, silencing
            flags). User values take precedence.
        interval : list of int, default None
            Prediction interval percentiles as a two-element list
            `[lower, upper]` (e.g. `[10, 90]` for 80 % interval). If
            None, no prediction intervals are computed.

        Returns
        -------
        plan : ForecastPlan
            Detailed forecasting plan.
        """

        data_profile = profile.data_profile
        context      = profile.analysis_context

        fc = profile.forecaster
        if forecaster is not None:
            if forecaster not in profile.forecaster_candidates:
                raise ValueError(
                    f"Forecaster '{forecaster}' is not compatible with this "
                    f"profile. Available candidates: "
                    f"{profile.forecaster_candidates}."
                )
            fc = forecaster

        task_type = select_task_type_from_forecaster(fc)

        if task_type != profile.task_type:
            est, _ = select_estimator_and_candidates(
                task_type      = task_type,
                n_observations = context.effective_n_observations,
            )
        else:
            est = profile.estimator

        if estimator is not None:
            est = estimator

        # TODO: Enhance autoreg selection with skill when ready
        if task_type in ("statistical", "foundation"):
            lags = None
            window_features = None
            transformer_series = None
            transformer_exog = None
            dropna_from_series = None
        else:
            if context.target_series is None or len(context.target_series) == 0:
                # Fallback: PACF-based selection requires a non-empty series.
                # Use a safe default lag range when the target is unavailable.
                n_lags = min(5, max(context.effective_n_observations // 3, 1))
                lags = list(range(1, n_lags + 1))
                window_features = None
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
                estimator        = est,
                missing_target   = data_profile.missing_target,
                missing_exog     = data_profile.missing_exog,
                task_type        = task_type,
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

        interval_method = None
        if interval is not None:
            if task_type in {"statistical", "foundation"}:
                interval_method = "native"
            else:
                interval_method = "bootstrapping"

        use_exog = check_exog_usage(data_profile.exog_columns)

        preprocessing_steps = derive_preprocessing_steps(data_profile, fc)

        metric, metric_explanation, metrics_to_compute = select_metric(
            data_profile = data_profile,
        )

        explanation = build_plan_explanation(
            forecaster         = fc,
            estimator          = est,
            lags               = lags,
            window_features    = window_features,
            interval_method    = interval_method,
            dropna_from_series = dropna_from_series,
            use_exog           = use_exog,
            metric_explanation = metric_explanation,
        )

        return ForecastPlan(
            task_type           = task_type,
            forecaster          = fc,
            forecaster_kwargs   = forecaster_kwargs,
            estimator           = est,
            estimator_kwargs    = estimator_kwargs or {},
            steps               = steps,
            frequency           = data_profile.frequency,
            interval            = interval,
            interval_method     = interval_method,
            metric              = metric,
            metrics_to_compute  = metrics_to_compute,
            use_exog            = use_exog,
            preprocessing_steps = preprocessing_steps,
            explanation         = explanation,
        )

    def refine_plan(
        self,
        profile: ForecastingProfile,
        plan: ForecastPlan,
        **overrides,
    ) -> ForecastPlan:
        """
        Re-derive a forecast plan applying user overrides.

        Takes an existing plan and a set of overrides, then calls
        `generate_plan()` with the merged parameters. Only the
        overridden fields change; everything else is re-derived
        deterministically from the original profile.

        Supported overrides: `forecaster`, `estimator`,
        `estimator_kwargs`, `steps`, `interval`.

        Parameters
        ----------
        profile : ForecastingProfile
            Original profile that produced the plan.
        plan : ForecastPlan
            Existing plan to refine.
        **overrides
            Keyword arguments to override. Accepted keys:
            `forecaster`, `estimator`, `estimator_kwargs`, `steps`,
            `interval`.

        Returns
        -------
        plan : ForecastPlan
            Updated plan with overrides applied.
        """

        allowed_keys = {"forecaster", "estimator", "estimator_kwargs", "steps", "interval"}
        invalid_keys = set(overrides) - allowed_keys
        if invalid_keys:
            raise ValueError(
                f"Invalid override keys: {sorted(invalid_keys)}. "
                f"Allowed keys: {sorted(allowed_keys)}."
            )

        steps = overrides.get("steps", plan.steps)
        forecaster = overrides.get("forecaster", plan.forecaster)
        estimator = overrides.get("estimator", plan.estimator)
        estimator_kwargs = overrides.get("estimator_kwargs", plan.estimator_kwargs or None)
        interval = overrides.get("interval", plan.interval)

        return self.generate_plan(
            profile          = profile,
            steps            = steps,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            interval         = interval,
        )

    def generate_code_from_plan(
        self,
        profile: DataProfile,
        plan: ForecastPlan,
    ) -> str:
        """
        Generate a complete Python script from a plan and data profile.

        Unlike the convenience `generate_code()` method, this allows
        advanced users to modify the `ForecastPlan` or `DataProfile`
        before generating code.

        Parameters
        ----------
        profile : DataProfile
            Profile of the input dataset (available via
            `profile.data_profile`).
        plan : ForecastPlan
            Validated forecast plan (output of `generate_plan()`).

        Returns
        -------
        code : str
            Syntactically valid Python script implementing the
            forecasting workflow.
        """

        generated = generate_template(profile=profile, plan=plan)

        return generated.full_script

    def generate_code(
        self,
        data: pd.DataFrame | str | Path,
        target: str | list[str],
        steps: int,
        date_column: str | None = None,
        series_id_column: str | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[int] | None = None,
    ) -> CodeGenerationResult:
        """
        Profile, plan, and generate a complete forecasting script.

        Convenience wrapper that chains `profile()`, `generate_plan()`,
        and code generation in a single call.

        Parameters
        ----------
        data : pandas DataFrame, str, Path
            Input dataset or path to a CSV file.
        target : str, list of str
            Name of the column to forecast.
        steps : int
            Forecast horizon (number of steps ahead to predict).
        date_column : str, default None
            Name of the column containing timestamps.
        series_id_column : str, default None
            Name of the column identifying individual series.
        forecaster : str, default None
            Explicit forecaster class name. See `profile()`.
        estimator : str, default None
            Explicit estimator class name. See `profile()`.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200}`). See `generate_plan()`.
        interval : list of int, default None
            Prediction interval percentiles as a two-element list
            `[lower, upper]` (e.g. `[10, 90]` for 80 % interval). If
            None, no prediction intervals are computed.

        Returns
        -------
        result : CodeGenerationResult
            Forecasting profile, plan, and generated code.
        """

        profile = self.profile(
            data             = data,
            target           = target,
            date_column      = date_column,
            series_id_column = series_id_column,
        )

        plan = self.generate_plan(
            profile          = profile,
            steps            = steps,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            interval         = interval,
        )

        code = self.generate_code_from_plan(profile=profile.data_profile, plan=plan)

        return CodeGenerationResult(
            profile = profile,
            plan    = plan,
            code    = code,
        )

    def forecast(
        self,
        data: pd.DataFrame | str | Path,
        target: str | list[str],
        steps: int,
        date_column: str | None = None,
        series_id_column: str | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[int] | None = None,
        exog_future: pd.DataFrame | None = None,
        profile: ForecastingProfile | None = None,
        plan: ForecastPlan | None = None,
    ) -> ForecastResult:
        """
        Execute a full forecasting workflow end-to-end.

        Convenience wrapper that chains `profile()`, `generate_plan()`,
        validation and programmatic execution.

        Parameters
        ----------
        data : pandas DataFrame, str, Path
            Input dataset or path to a CSV file.
        target : str, list of str
            Name of the column to forecast.
        steps : int
            Forecast horizon (number of steps ahead to predict).
        date_column : str, default None
            Name of the column containing timestamps.
        series_id_column : str, default None
            Name of the column identifying individual series.
        forecaster : str, default None
            Explicit forecaster class name. See `profile()`.
        estimator : str, default None
            Explicit estimator class name. See `profile()`.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200}`). See `generate_plan()`.
        interval : list of int, default None
            Prediction interval percentiles as a two-element list
            `[lower, upper]` (e.g. `[10, 90]` for 80 % interval). If
            None, no prediction intervals are computed.
        exog_future : pandas DataFrame, default None
            Exogenous variables covering the forecast horizon
            (`steps` rows). Required for final predictions when
            exogenous variables are used. If None and exog is present,
            the last `steps` rows of the training data exog are used
            (backtesting mode).
        profile : ForecastingProfile, default None
            Pre-computed profile to skip profiling. If None, profiling
            is performed from `data`.
        plan : ForecastPlan, default None
            Pre-computed plan to skip planning. If None, a plan is
            generated from the profile. Requires `profile` to also be
            provided.

        Returns
        -------
        result : ForecastResult
            Forecasting profile, plan, generated code, predictions,
            backtesting metric, and optional prediction intervals.

        Notes
        -----
        This method executes the same code that `generate_code()`
        produces, ensuring perfect fidelity between the inspectable
        script (`ForecastResult.code`) and the actual execution.

        """

        data_df = _coerce_to_dataframe(data)

        if profile is None:
            profile = self.profile(
                data             = data_df,
                target           = target,
                date_column      = date_column,
                series_id_column = series_id_column,
            )
        if plan is None:
            plan = self.generate_plan(
                profile          = profile,
                steps            = steps,
                forecaster       = forecaster,
                estimator        = estimator,
                estimator_kwargs = estimator_kwargs,
                interval         = interval,
            )

        result = run_forecast(
            data        = data_df,
            profile     = profile.data_profile,
            plan        = plan,
            exog_future = exog_future,
        )

        return ForecastResult(
            profile     = profile,
            plan        = plan,
            code        = result["generated_code"].full_script,
            metrics     = result["metrics"],
            predictions = result["predictions"],
            intervals   = result["intervals"],
        )

    def ask(
        self,
        prompt: str,
        data: pd.DataFrame | str | Path | None = None,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        profile: ForecastingProfile | None = None,
        plan: ForecastPlan | None = None,
        forecast_result: ForecastResult | None = None,
        steps: int | None = None,
        skills: list[str] | None = None,
        include_reference: bool = False,
    ) -> AskResult:
        """
        Ask a forecasting question or explain a pre-computed plan.

        Operates in three modes:

        - **Q&A mode** (no data, no profile, no forecast_result): The LLM
        answers general forecasting or skforecast questions using its
        skills.
        - **Explain mode** (data or profile provided): Deterministic
        profiling runs first, then the LLM explains the result.
        - **Results mode** (forecast_result provided): The LLM explains
        forecast predictions, metrics, and intervals from a
        completed `forecast()` run.

        Parameters
        ----------
        prompt : str
            Natural-language question or instruction.
        data : pandas DataFrame, str, Path, default None
            Optional dataset or path to a CSV file. When provided
            (without a pre-computed profile), triggers deterministic
            profiling + plan generation before the LLM call.
        target : str, list of str, default None
            Name of the target column(s). Required when `data` is
            provided and `profile` is None.
        date_column : str, default None
            Name of the column containing timestamps.
        series_id_column : str, default None
            Name of the column identifying individual series.
        profile : ForecastingProfile, default None
            Pre-computed profile. If provided, profiling is skipped.
        plan : ForecastPlan, default None
            Pre-computed plan. If provided, plan generation is skipped.
        forecast_result : ForecastResult, default None
            Result from a previous `forecast()` call. When provided,
            the LLM receives predictions, metrics, and intervals in
            context so it can explain the forecast results. Extracts
            `profile` and `plan` from the result unless
            explicitly provided.
        steps : int, default None
            Forecast horizon used when generating a plan from data.
            Required when `data` or `profile` is provided
            without a pre-computed `plan`.
        skills : list of str, default None
            List of skill names to include in the agent system prompt.
            If None, skills are selected automatically based on the
            task type and question content. See `skforecast_ai.ALL_SKILLS`
            for valid names.
        include_reference : bool, default False
            Whether to include the skforecast API reference in the
            prompt.

        Returns
        -------
        result : AskResult
            Response with optional forecaster profile, plan, generated code,
            and LLM-generated explanation.

        Notes
        -----
        Requires an LLM. If `llm=None` was passed at init,
        `LLMRequiredError` is raised.

        """

        if self.llm is None:
            raise LLMRequiredError("ask")

        # --- Extract from forecast_result if provided ---
        predictions = None
        metrics = None
        intervals = None
        if forecast_result is not None:
            profile = profile or forecast_result.profile
            plan = plan or forecast_result.plan
            predictions = forecast_result.predictions
            metrics = forecast_result.metrics
            intervals = forecast_result.intervals

        # --- Deterministic stage: compute profile/plan if needed ---
        if data is not None and profile is None:
            if target is None:
                raise ValueError(
                    "`target` is required when `data` is provided."
                )
            profile = self.profile(
                data             = data,
                target           = target,
                date_column      = date_column,
                series_id_column = series_id_column,
            )
        if profile is not None and plan is None:
            if steps is None:
                raise ValueError(
                    "`steps` is required when `data` or "
                    "`profile` is provided without a "
                    "pre-computed `plan`."
                )
            plan = self.generate_plan(profile, steps=steps)

        # --- Generate deterministic code from plan ---
        if forecast_result is not None:
            generated_code = forecast_result.code
        elif plan is not None and profile is not None:
            generated_code = self.generate_code_from_plan(
                profile.data_profile, plan
            )
        else:
            generated_code = None

        # --- Pre-flight check for Ollama ---
        if self.llm is not None and self.llm.startswith("ollama:"):
            ensure_ollama_reachable(self.base_url)

        # --- Build user message with context ---
        # In results mode, always send prediction data so the LLM can
        # discuss specific values. Otherwise respect the user setting.
        send_data = (
            True if forecast_result is not None else self.send_data_to_llm
        )
        context = build_context_message(
            profile, plan,
            predictions=predictions,
            metrics=metrics,
            intervals=intervals,
            send_data=send_data,
        )
        user_message = (
            f"{context}\n\n## Question\n\n{prompt}" if context else prompt
        )

        # --- Dynamic skill selection when not explicitly provided ---
        resolved_skills = skills
        if resolved_skills is None:
            task_type = (
                profile.task_type
                if profile is not None
                else None
            )
            resolved_skills = select_skills(
                task_type=task_type,
                question=prompt,
            )

        # --- LLM call ---
        from .llm import AskDeps

        agent = self._resolve_agent()
        deps = AskDeps(
            profile=profile,
            plan=plan,
            question=prompt,
            include_reference=include_reference,
            skills_override=resolved_skills,
        )

        estimated_tokens = estimate_prompt_tokens(
            resolved_skills, include_reference
        )
        model_settings = self._build_ollama_settings(
            estimated_tokens, user_message
        )

        _patch_event_loop()
        try:
            result = agent.run_sync(
                user_message,
                deps=deps,
                model_settings=model_settings,
            )
            explanation = result.output

            # Strip code blocks in Explain/Results mode (validated code exists)
            if generated_code is not None:
                explanation = _strip_code_blocks(explanation)
        except Exception as exc:
            warnings.warn(
                f"LLM call failed ({exc}), returning deterministic result.",
                UserWarning,
                stacklevel=2,
            )
            if plan is not None:
                explanation = f"[LLM unavailable] {plan.explanation}"
            else:
                explanation = f"[LLM unavailable] {exc}"

        return AskResult(
            profile     = profile,
            plan        = plan,
            code        = generated_code,
            explanation = explanation,
        )

    # --------------------------------------------------------------- private
    def _resolve_model(self):
        """
        Lazily resolve the LLM model from the provider string.

        Returns
        -------
        model : str, OllamaModel
            Resolved Pydantic AI model instance.
        """

        if self._model is None:
            self._model = create_model(
                llm=self.llm, base_url=self.base_url, api_key=self.api_key
            )
        
        return self._model

    def _resolve_agent(self):
        """
        Lazily create and cache the pydantic-ai Agent instance.

        The agent is created once per assistant and reused across calls.
        Dynamic behavior (skill selection, reference inclusion) is
        handled via `AskDeps` passed at run time.

        Returns
        -------
        agent : Agent[AskDeps, str]
            Cached agent instance.
        """
        if self._agent is None:
            from .llm.agent import create_forecasting_agent

            model = self._resolve_model()
            self._agent = create_forecasting_agent(model)

        return self._agent

    def _build_ollama_settings(
        self, estimated_prompt_tokens: int, user_message: str
    ) -> dict | None:
        """
        Build Ollama-specific model settings with dynamic context sizing.

        Uses the pre-computed token estimate for system prompt content
        plus the user message length to determine the appropriate
        `num_ctx`. Clamps between 4096 and 32768. Warns when the
        prompt approaches the hard maximum. Returns None for non-Ollama
        providers.

        Parameters
        ----------
        estimated_prompt_tokens : int
            Estimated tokens for the system prompt (skills + reference).
        user_message : str
            The user message to send.

        Returns
        -------
        settings : dict, None
            Model settings dict or None for cloud providers.
        """
        if self.llm is None or not self.llm.startswith("ollama:"):
            return None

        user_tokens = len(user_message) // 4
        estimated_tokens = estimated_prompt_tokens + user_tokens
        num_ctx = max(4096, min(estimated_tokens + 2048, 32768))

        if estimated_tokens > 30000:
            warnings.warn(
                f"Estimated prompt size (~{estimated_tokens} tokens) approaches "
                f"the Ollama context limit (32768). Output may be truncated. "
                f"Consider using `skills=[]` or `include_reference=False`.",
                UserWarning,
                stacklevel=3,
            )

        return {
            "extra_body": {
                "keep_alive": "10m",
                "options": {"num_ctx": num_ctx},
            }
        }
