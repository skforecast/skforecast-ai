"""ForecastingAssistant: unified public API for skforecast-ai."""

from __future__ import annotations

import asyncio
import warnings
from pathlib import Path

import pandas as pd

from .exceptions import LLMRequiredError
from .execution import run_forecast
from .generation.code_templates import generate_template
from .llm.agent import create_forecasting_agent
from .llm.provider import create_model
from .profiling import create_forecaster_analysis, create_data_profile
from .profiling.data_profile import _try_parse_first_date_column
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
    select_task_type_from_forecaster,
    select_transformer_exog,
    select_transformer_series,
)
from .schemas import (
    AskResult,
    DataProfile,
    ForecasterProfile,
    ForecastPlan,
    GenerateResult,
    RunResult,
)


class ForecastingAssistant:
    """
    Unified forecasting assistant.

    Exposes a two-step deterministic workflow:

    1. `profile()` — inspects the dataset and returns a
       `ForecasterProfile` with the recommended forecaster + estimator
       and their compatible candidates.
    2. `generate_plan()` — takes the `ForecasterProfile` and produces a
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
    send_data_to_llm : bool, default False
        Whether raw data may be sent to the LLM. When False, only
        metadata (schema, summary stats) is shared with the LLM.

    Attributes
    ----------
    llm : str, None
        LLM provider string or None for deterministic-only mode.
    base_url : str, None
        Custom base URL for the LLM provider.
    send_data_to_llm : bool
        Whether raw data may be sent to the LLM.
    _model : object, None
        Cached LLM model instance (internal use).    
    
    """

    def __init__(
        self,
        llm: str | None = None,
        base_url: str | None = None,
        send_data_to_llm: bool = False,
    ) -> None:
        
        self.llm = llm
        self.base_url = base_url
        self.send_data_to_llm = send_data_to_llm
        self._model = None

    def profile(
        self,
        data: pd.DataFrame | str | Path,
        target: str | list[str],
        date_column: str | None = None,
        series_id_column: str | None = None,
    ) -> ForecasterProfile:
        """
        Profile a dataset and select the recommended forecaster + estimator.

        Wraps `create_data_profile` and `build_forecaster_profile` into a
        single call. The returned `ForecasterProfile` carries the
        `DataProfile` plus the coarse modeling decisions and their
        alternative candidates.

        Parameters
        ----------
        data : pandas DataFrame, str, Path
            Input dataset or path to a CSV file.
        target : str, list
            Name of the column to forecast. For wide-format multi-series,
            pass a list of column names where each column is a series.
        date_column : str, default None
            Name of the column containing timestamps.
        series_id_column : str, default None
            Name of the column identifying individual series.

        Returns
        -------
        forecaster_profile : ForecasterProfile
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
        analysis_context = create_forecaster_analysis(data, data_profile, forecaster)

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

        return ForecasterProfile(
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
        forecaster_profile: ForecasterProfile,
        steps: int,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[int] | None = None,
    ) -> ForecastPlan:
        """
        Build a detailed `ForecastPlan` from a `ForecasterProfile`.

        Performs the fine-grained configuration (lags, prediction
        intervals, NaN handling, exogenous usage, preprocessing steps)
        without re-evaluating the coarse decisions already encoded in
        `forecaster_profile`.

        Parameters
        ----------
        forecaster_profile : ForecasterProfile
            Output of `profile()`.
        steps : int
            Forecast horizon (number of steps ahead to predict).
        forecaster : str, default None
            Explicit forecaster class name to override the profile
            recommendation. Must be in `forecaster_profile.forecaster_candidates`.
        estimator : str, default None
            Explicit estimator class name to override the profile
            recommendation. Must be in `forecaster_profile.estimator_candidates`.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200, 'learning_rate': 0.05}`). Merged
            on top of built-in defaults (`random_state`, silencing
            flags). User values take precedence.
        interval : list, default None
            Prediction interval percentiles as a two-element list
            `[lower, upper]` (e.g. `[10, 90]` for 80 % interval). If
            None, no prediction intervals are computed.

        Returns
        -------
        plan : ForecastPlan
            Detailed forecasting plan.
        
        """

        data_profile = forecaster_profile.data_profile
        context      = forecaster_profile.analysis_context

        fc = forecaster_profile.forecaster
        if forecaster is not None:
            if forecaster not in forecaster_profile.forecaster_candidates:
                raise ValueError(
                    f"Forecaster '{forecaster}' is not compatible with this "
                    f"profile. Available candidates: "
                    f"{forecaster_profile.forecaster_candidates}."
                )
            fc = forecaster

        task_type = select_task_type_from_forecaster(fc)

        if task_type != forecaster_profile.task_type:
            est, est_candidates = select_estimator_and_candidates(
                task_type      = task_type,
                n_observations = context.effective_n_observations,
            )
        else:
            est = forecaster_profile.estimator
            est_candidates = forecaster_profile.estimator_candidates

        if estimator is not None:
            if estimator not in est_candidates:
                raise ValueError(
                    f"Estimator '{estimator}' is not compatible with this "
                    f"profile. Available candidates: {est_candidates}."
                )
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

        explanation = build_plan_explanation(
            forecaster         = fc,
            estimator          = est,
            lags               = lags,
            window_features    = window_features,
            interval_method    = interval_method,
            dropna_from_series = dropna_from_series,
            use_exog           = use_exog,
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
            use_exog            = use_exog,
            preprocessing_steps = preprocessing_steps,
            explanation         = explanation,
        )

    def refine_plan(
        self,
        plan: ForecastPlan,
        forecaster_profile: ForecasterProfile,
        **overrides,
    ) -> ForecastPlan:
        """
        Re-derive a forecast plan applying user overrides.

        .. note:: Not implemented yet.

        Parameters
        ----------
        plan : ForecastPlan
            Existing plan to refine.
        forecaster_profile : ForecasterProfile
            Original profile that produced the plan.
        **overrides
            Keyword arguments to override (e.g. ``forecaster``,
            ``estimator``, ``steps``, ``lags``, ``interval``).

        Returns
        -------
        plan : ForecastPlan
            Updated plan with overrides applied.
        
        """
        # TODO: Implement interactive refinement of an existing plan.
        #
        # The idea is to let users (or the LLM agent via a
        # `refine_plan_tool`) request changes on top of a previously
        # generated plan — e.g. "use RandomForest instead", "predict 48
        # steps", "add 90 % prediction intervals".
        #
        # The LLM's role is limited to mapping natural-language requests
        # into concrete override parameters; every decision stays
        # deterministic: `generate_plan()` is called again with the
        # overrides merged into the existing profile/plan.
        #
        # A corresponding `refine_plan_tool` should be registered in
        # `llm/agent.py` so the agent can invoke this method during a
        # conversation.
        raise NotImplementedError("refine_plan is not yet implemented.")

    def generate_code_from_plan(
        self,
        plan: ForecastPlan,
        data_profile: DataProfile,
    ) -> str:
        """
        Generate a complete Python script from a plan and data profile.

        Unlike the convenience `generate_code()` method, this allows
        advanced users to modify the `ForecastPlan` or `DataProfile`
        before generating code.

        Parameters
        ----------
        plan : ForecastPlan
            Validated forecast plan (output of `generate_plan()`).
        data_profile : DataProfile
            Profile of the input dataset (available via
            ``forecaster_profile.data_profile``).

        Returns
        -------
        code : str
            Syntactically valid Python script implementing the
            forecasting workflow.
        
        """

        generated = generate_template(plan, data_profile)

        return generated.full_script

    def generate_code(
        self,
        data: pd.DataFrame | str | Path,
        target: str | list[str],
        date_column: str | None = None,
        series_id_column: str | None = None,
        steps: int = 10,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[int] | None = None,
    ) -> GenerateResult:
        """
        Profile, plan, and generate a complete forecasting script.

        Convenience wrapper that chains `profile()`, `generate_plan()`,
        and code generation in a single call.

        Parameters
        ----------
        data : pandas DataFrame, str, Path
            Input dataset or path to a CSV file.
        target : str, list
            Name of the column to forecast.
        date_column : str, default None
            Name of the column containing timestamps.
        series_id_column : str, default None
            Name of the column identifying individual series.
        steps : int, default 10
            Forecast horizon.
        forecaster : str, default None
            Explicit forecaster class name. See `profile()`.
        estimator : str, default None
            Explicit estimator class name. See `profile()`.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200}`). See `generate_plan()`.
        interval : list, default None
            Prediction interval percentiles as a two-element list
            `[lower, upper]` (e.g. `[10, 90]` for 80 % interval). If
            None, no prediction intervals are computed.

        Returns
        -------
        result : GenerateResult
            Forecaster profile, plan, and generated code.
        
        """

        forecaster_profile = self.profile(
            data             = data,
            target           = target,
            date_column      = date_column,
            series_id_column = series_id_column,
        )

        plan = self.generate_plan(
            forecaster_profile,
            steps            = steps,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            interval         = interval,
        )

        code = self.generate_code_from_plan(plan, forecaster_profile.data_profile)

        return GenerateResult(
            forecaster_profile = forecaster_profile,
            plan               = plan,
            code               = code,
        )

    def forecast(
        self,
        data: pd.DataFrame | str | Path,
        target: str | list[str],
        date_column: str | None = None,
        series_id_column: str | None = None,
        steps: int = 10,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[int] | None = None,
        exog_future: pd.DataFrame | None = None,
    ) -> RunResult:
        """
        Execute a full forecasting workflow end-to-end.

        Convenience wrapper that chains `profile()`, `generate_plan()`,
        validation and programmatic execution.

        Parameters
        ----------
        data : pandas DataFrame, str, Path
            Input dataset or path to a CSV file.
        target : str, list
            Name of the column to forecast.
        date_column : str, default None
            Name of the column containing timestamps.
        series_id_column : str, default None
            Name of the column identifying individual series.
        steps : int, default 10
            Forecast horizon.
        forecaster : str, default None
            Explicit forecaster class name. See `profile()`.
        estimator : str, default None
            Explicit estimator class name. See `profile()`.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200}`). See `generate_plan()`.
        interval : list, default None
            Prediction interval percentiles as a two-element list
            `[lower, upper]` (e.g. `[10, 90]` for 80 % interval). If
            None, no prediction intervals are computed.
        exog_future : pandas DataFrame, default None
            Exogenous variables covering the forecast horizon
            (`steps` rows). Required for final predictions when
            exogenous variables are used. If None and exog is present,
            the last `steps` rows of the training data exog are used
            (backtesting mode).

        Returns
        -------
        result : RunResult
            Forecaster profile, plan, generated code, predictions,
            backtesting metric, and optional prediction intervals.

        Notes
        -----
        This method executes the same code that ``generate_code()``
        produces, ensuring perfect fidelity between the inspectable
        script (``RunResult.code``) and the actual execution.

        """

        data_df = _coerce_to_dataframe(data)

        forecaster_profile = self.profile(
            data             = data_df,
            target           = target,
            date_column      = date_column,
            series_id_column = series_id_column,
        )
        plan = self.generate_plan(
            forecaster_profile = forecaster_profile,
            steps              = steps,
            forecaster         = forecaster,
            estimator          = estimator,
            estimator_kwargs   = estimator_kwargs,
            interval           = interval,
        )

        result = run_forecast(
            data        = data_df,
            profile     = forecaster_profile.data_profile,
            plan        = plan,
            exog_future = exog_future,
        )

        return RunResult(
            forecaster_profile = forecaster_profile,
            plan               = plan,
            code               = result["generated_code"].full_script,
            metrics            = result["metrics"],
            predictions        = result["predictions"],
            intervals          = result["intervals"],
        )

    def ask(
        self,
        question: str,
        data: pd.DataFrame | str | Path | None = None,
        skills: list[str] | None = None,
        include_reference: bool = False,
    ) -> AskResult:
        """
        Ask a free-form forecasting question using the LLM agent.

        Parameters
        ----------
        question : str
            Natural-language question or instruction.
        data : pandas DataFrame, str, Path, default None
            Optional dataset or path to a CSV file for context.
        skills : list, default None
            List of skill names to include in the agent system prompt.
            If None, a compact default set is loaded. Pass `'all'` as
            a single-element list to load every available skill.
        include_reference : bool, default False
            Whether to include the skforecast API reference in the
            prompt. The reference is ~195 KB and may exceed the context
            window of smaller models.

        Returns
        -------
        result : AskResult
            Agent's structured response with optional forecaster
            profile, plan, code, and explanation.

        Notes
        -----
        Requires an LLM. If `llm=None` was passed at init,
        `LLMRequiredError` is raised.

        """

        if self.llm is None:
            raise LLMRequiredError("ask")

        try:
            model = self._resolve_model()

            agent = create_forecasting_agent(
                model             = model,
                skills            = skills,
                include_reference = include_reference,
            )
            _patch_event_loop()
            result = agent.run_sync(
                question, model_settings=self._build_model_settings()
            )

            plan = result.output if isinstance(result.output, ForecastPlan) else None
            return AskResult(
                plan        = plan,
                explanation = str(result.output),
            )
        except LLMRequiredError:
            raise
        except Exception as exc:
            warnings.warn(
                f"LLM call failed ({exc}), falling back to deterministic mode.",
                UserWarning,
                stacklevel=2,
            )
            if data is not None:
                df = _coerce_to_dataframe(data)
                numeric = df.select_dtypes(include="number").columns
                target = numeric[0] if len(numeric) > 0 else df.columns[-1]
                forecaster_profile = self.profile(
                    data   = df,
                    target = target,
                )
                plan = self.generate_plan(forecaster_profile, steps=10)
                return AskResult(
                    forecaster_profile = forecaster_profile,
                    plan               = plan,
                    explanation        = f"[LLM unavailable] {plan.explanation}",
                )
            return AskResult(
                explanation=(
                    f"[LLM unavailable] {exc}. "
                    "Provide data to get a deterministic recommendation."
                ),
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
            self._model = create_model(llm=self.llm, base_url=self.base_url)
        
        return self._model

    # TODO: Review when reviews LLMs capabilities
    def _build_model_settings(self) -> dict | None:
        """
        Build provider-specific model settings.

        For Ollama models, sets `num_ctx` to ensure the context window
        is large enough for the system prompt, tool schemas, and
        conversation history.

        Returns
        -------
        settings : dict, None
            Model settings dict or None for cloud providers.

        """

        if self.llm is not None and self.llm.startswith("ollama:"):
            return {"extra_body": {"options": {"num_ctx": 32768}}}
        
        return None


def _coerce_to_dataframe(
    data: pd.DataFrame | str | Path,
) -> pd.DataFrame:
    """
    Load a CSV path into a DataFrame, or return the DataFrame unchanged.

    The CSV is loaded without ``parse_dates`` (deprecated in pandas
    2.2+). Date columns are detected and parsed by
    ``_try_parse_first_date_column`` instead, leaving every column
    intact so callers can reference a ``date_column`` by name.

    Parameters
    ----------
    data : pandas DataFrame, str, Path
        Input dataset or path to a CSV file.

    Returns
    -------
    df : pandas DataFrame
        Loaded DataFrame.
    
    """

    if isinstance(data, (str, Path)):
        df = pd.read_csv(data)
        return _try_parse_first_date_column(df)
    
    return data


def _patch_event_loop() -> None:
    """
    Apply `nest_asyncio` when an event loop is already running.

    Enables `run_sync()` to work inside Jupyter notebooks and other
    environments that already have an active asyncio event loop. The
    patch is applied at most once per process.

    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # No running loop — nothing to patch

    if not getattr(loop, "_nest_patched", False):
        import nest_asyncio

        nest_asyncio.apply()
