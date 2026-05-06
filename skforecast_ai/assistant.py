"""ForecastingAssistant: unified public API for skforecast-ai."""

from __future__ import annotations

import asyncio
import warnings
from pathlib import Path

import pandas as pd

from .exceptions import LLMRequiredError
from .execution import run_forecast, validate_run_inputs
from .generation import generate_code as _generate_code
from .preparation import derive_preprocessing_steps
from .profiling import create_analysis_context, create_data_profile
from .schemas import (
    AskResult,
    DataProfile,
    ForecasterProfile,
    ForecastPlan,
    GenerateResult,
    RunResult,
)
from .recommendation import (
    _build_profile_explanation,
    build_data_requirements,
    build_explanation,
    check_exog_usage,
    select_backtesting,
    select_dropna_from_series,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_interval_method,
    select_lags,
    select_metric,
    select_task_type_from_forecaster,
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
    chain the two stages plus code generation / execution. `ask()` and
    `explain()` provide LLM-powered interfaces.

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

        data = _coerce_to_dataframe(data)

        data_profile = create_data_profile(
            data             = data,
            target           = target,
            date_column      = date_column,
            series_id_column = series_id_column,
        )

        fc, forecaster_candidates = select_forecaster_and_candidates(data_profile)
        task_type = select_task_type_from_forecaster(fc)
        analysis_context = create_analysis_context(data, data_profile, fc)

        est, estimator_candidates = select_estimator_and_candidates(
            task_type=task_type, n_observations=analysis_context.effective_n_observations
        )

        explanation = _build_profile_explanation(
            task_type=task_type,
            forecaster=fc,
            forecaster_candidates=forecaster_candidates,
            estimator=est,
            estimator_candidates=estimator_candidates,
            data_profile=data_profile,
        )

        return ForecasterProfile(
            data_profile          = data_profile,
            task_type             = task_type,
            forecaster            = fc,
            forecaster_candidates = forecaster_candidates,
            estimator             = est,
            estimator_candidates  = estimator_candidates,
            analysis_context      = analysis_context,
            explanation           = explanation,
        )

    def generate_plan(
        self,
        forecaster_profile: ForecasterProfile,
        steps: int = 10,
        forecaster: str | None = None,
        estimator: str | None = None,
    ) -> ForecastPlan:
        """
        Build a detailed `ForecastPlan` from a `ForecasterProfile`.

        Performs the fine-grained configuration (lags, metric,
        backtesting strategy, prediction intervals, NaN handling,
        exogenous usage, preprocessing steps) without re-evaluating the
        coarse decisions already encoded in `forecaster_profile`.

        Parameters
        ----------
        forecaster_profile : ForecasterProfile
            Output of `profile()`.
        steps : int, default 10
            Forecast horizon (number of steps ahead to predict).
        forecaster : str, default None
            Explicit forecaster class name to override the profile
            recommendation. Must be in `forecaster_profile.forecaster_candidates`.
        estimator : str, default None
            Explicit estimator class name to override the profile
            recommendation. Must be in `forecaster_profile.estimator_candidates`.

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

        est = forecaster_profile.estimator
        if task_type in ("statistical", "foundation", "baseline"):
            est = None
        if estimator is not None:
            if estimator not in forecaster_profile.estimator_candidates:
                raise ValueError(
                    f"Estimator '{estimator}' is not compatible with this "
                    f"profile. Available candidates: "
                    f"{forecaster_profile.estimator_candidates}."
                )
            est = estimator

        if task_type in ("statistical", "foundation", "baseline"):
            lags = None
        else:
            lags = select_lags(context.effective_n_observations)

        metric               = select_metric(task_type)
        backtesting_strategy = select_backtesting(
            context.effective_n_observations, steps
        )
        interval_method      = select_interval_method(
            fc, context.effective_n_observations
        )
        dropna_from_series   = select_dropna_from_series(
            est,
            data_profile.missing_target,
            data_profile.missing_exog,
            task_type,
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
            task_type, fc, est, lags, metric, interval_method,
            data_profile,
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

    def generate_code(
        self,
        data: pd.DataFrame | str | Path,
        target: str | list[str],
        date_column: str | None = None,
        series_id_column: str | None = None,
        steps: int = 10,
        forecaster: str | None = None,
        estimator: str | None = None,
        data_path: str = "data.csv",
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
        data_path : str, default `'data.csv'`
            File path used in the generated script for loading data.

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
            steps      = steps,
            forecaster = forecaster,
            estimator  = estimator,
        )
        code = _generate_code(
            plan      = plan,
            profile   = forecaster_profile.data_profile,
            data_path = data_path,
        )
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
        This method does not use `exec()`. The workflow is executed
        programmatically by calling skforecast functions directly with
        parameters derived from the `ForecastPlan`.
        """
        data_df = _coerce_to_dataframe(data)

        forecaster_profile = self.profile(
            data             = data_df,
            target           = target,
            date_column      = date_column,
            series_id_column = series_id_column,
        )
        plan = self.generate_plan(
            forecaster_profile,
            steps      = steps,
            forecaster = forecaster,
            estimator  = estimator,
        )
        code = _generate_code(
            plan      = plan,
            profile   = forecaster_profile.data_profile,
            data_path = "data.csv",
        )

        run_warnings = validate_run_inputs(
            data    = data_df,
            profile = forecaster_profile.data_profile,
            plan    = plan,
        )

        result = run_forecast(
            data        = data_df,
            profile     = forecaster_profile.data_profile,
            plan        = plan,
            exog_future = exog_future,
        )

        all_warnings = run_warnings + result.get("warnings", [])

        return RunResult(
            forecaster_profile = forecaster_profile,
            plan               = plan,
            code               = code,
            metric_value       = result["metric_value"],
            metric_name        = result["metric_name"],
            predictions        = result["predictions"],
            intervals          = result["intervals"],
            warnings           = all_warnings,
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
            from .llm.agent import create_forecasting_agent

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

    def explain(
        self,
        plan: ForecastPlan,
        profile: DataProfile | None = None,
    ) -> str:
        """
        Generate a plain-language explanation of a forecasting plan.

        Parameters
        ----------
        plan : ForecastPlan
            Validated forecast plan to explain.
        profile : DataProfile, default None
            Data profile providing context. If None, a minimal profile
            is constructed from the plan metadata.

        Returns
        -------
        explanation : str
            Human-readable explanation of the plan.

        Notes
        -----
        Requires an LLM. If `llm=None` was passed at init,
        `LLMRequiredError` is raised.
        """
        if self.llm is None:
            raise LLMRequiredError("explain")

        try:
            model = self._resolve_model()
            from .llm.prompts import build_explain_prompt

            if profile is None:
                profile = DataProfile(
                    n_series       = 1,
                    n_observations = 0,
                    index_type     = "datetime",
                    target         = "unknown",
                )

            from pydantic_ai import Agent

            explain_agent = Agent(
                model,
                output_type   = str,
                system_prompt = "You are a forecasting expert. Explain plans clearly.",
            )
            prompt = build_explain_prompt(plan=plan, profile=profile)
            _patch_event_loop()
            result = explain_agent.run_sync(
                prompt, model_settings=self._build_model_settings()
            )
            return result.output
        except LLMRequiredError:
            raise
        except Exception as exc:
            warnings.warn(
                f"LLM call failed ({exc}), using deterministic explanation.",
                UserWarning,
                stacklevel=2,
            )
            return f"[LLM unavailable] {plan.explanation}"

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
            from .llm.provider import create_model

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

    The CSV is loaded with `parse_dates=True` (no `index_col`), leaving
    every column intact so callers can reference a `date_column` by
    name. When the input is already a DataFrame, it is returned
    unchanged.

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
        from .profiling.data_profile import _try_parse_first_date_column

        df = pd.read_csv(data, parse_dates=True)
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
