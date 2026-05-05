"""ForecastingAssistant: unified public API for skforecast-ai."""

from __future__ import annotations

import asyncio
import warnings
from pathlib import Path

import pandas as pd

from .exceptions import LLMRequiredError
from .execution import run_forecast, validate_run_inputs
from .generation import generate_code
from .profiling import create_data_profile
from .recommendation import recommend_plan
from .schemas import (
    AskResult,
    DataProfile,
    ForecastPlan,
    GenerateResult,
    RecommendResult,
    RunResult,
)


class ForecastingAssistant:
    """
    Unified forecasting assistant that ties profiling, recommendation,
    code generation, and optional LLM capabilities into a single API.

    Parameters
    ----------
    llm : str, default None
        LLM provider string in format `'provider:model_name'`. If None,
        only deterministic Tier 0 methods are available.
    base_url : str, default None
        Custom base URL for the LLM provider (used for Ollama or
        OpenAI-compatible endpoints).
    send_data_to_llm : bool, default False
        Whether raw data may be sent to the LLM. When False, only metadata
        (schema, summary stats) is shared with the LLM.

    Attributes
    ----------
    llm : str, None
        LLM provider string or None for Tier 0 mode.
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
    ) -> DataProfile:
        """
        Profile a time series dataset.

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
        profile : DataProfile
            Structured profile with metadata, detected features, and warnings.
        """
        return create_data_profile(
            data=data,
            target=target,
            date_column=date_column,
            series_id_column=series_id_column,
        )

    def recommend(
        self,
        data: pd.DataFrame | str | Path,
        target: str | list[str],
        date_column: str | None = None,
        series_id_column: str | None = None,
        steps: int = 10,
        **kwargs,
    ) -> RecommendResult:
        """
        Profile a dataset and generate a deterministic forecasting plan.

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
        steps : int, default 10
            Number of steps ahead to predict.
        **kwargs
            Additional keyword arguments passed to `recommend_plan()`.

        Returns
        -------
        result : RecommendResult
            Contains the data profile and recommended forecast plan.
        """
        if isinstance(data, (str, Path)):
            data = pd.read_csv(data, parse_dates=True)

        profile = create_data_profile(
            data=data,
            target=target,
            date_column=date_column,
            series_id_column=series_id_column,
        )
        plan = recommend_plan(profile=profile, steps=steps, data=data, **kwargs)
        return RecommendResult(profile=profile, plan=plan)

    def generate_code(
        self,
        data: pd.DataFrame | str | Path,
        target: str | list[str],
        date_column: str | None = None,
        series_id_column: str | None = None,
        steps: int = 10,
        data_path: str = "data.csv",
        **kwargs,
    ) -> GenerateResult:
        """
        Profile, recommend, and generate a complete forecasting script.

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
        steps : int, default 10
            Number of steps ahead to predict.
        data_path : str, default `'data.csv'`
            File path used in the generated script for loading data.
        **kwargs
            Additional keyword arguments passed to `recommend_plan()`.

        Returns
        -------
        result : GenerateResult
            Contains the data profile, forecast plan, and generated code.
        """
        if isinstance(data, (str, Path)):
            data = pd.read_csv(data, parse_dates=True)

        profile = create_data_profile(
            data=data,
            target=target,
            date_column=date_column,
            series_id_column=series_id_column,
        )
        plan = recommend_plan(profile=profile, steps=steps, data=data, **kwargs)
        code = generate_code(plan=plan, profile=profile, data_path=data_path)
        return GenerateResult(profile=profile, plan=plan, code=code)

    def forecast(
        self,
        data: pd.DataFrame | str | Path,
        target: str | list[str],
        date_column: str | None = None,
        series_id_column: str | None = None,
        steps: int = 10,
        exog_future: pd.DataFrame | None = None,
        **kwargs,
    ) -> RunResult:
        """
        Execute a full forecasting workflow end-to-end.

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
        steps : int, default 10
            Number of steps ahead to predict.
        exog_future : pandas DataFrame, default None
            Exogenous variables covering the forecast horizon (``steps``
            rows). Required for final predictions when exogenous variables
            are used. If None and exog is present, the last ``steps`` rows
            of the training data exog are used (backtesting mode).
        **kwargs
            Additional keyword arguments passed to `recommend_plan()`.

        Returns
        -------
        result : RunResult
            Contains the profile, plan, generated code, predictions,
            backtesting metric, and optional prediction intervals.

        Notes
        -----
        This method does not use `exec()`. The workflow is executed
        programmatically by calling skforecast functions directly with
        parameters derived from the recommended `ForecastPlan`.
        """
        if isinstance(data, (str, Path)):
            data = pd.read_csv(data, parse_dates=True)

        profile = create_data_profile(
            data=data,
            target=target,
            date_column=date_column,
            series_id_column=series_id_column,
        )
        plan = recommend_plan(profile=profile, steps=steps, data=data, **kwargs)
        code = generate_code(plan=plan, profile=profile, data_path="data.csv")

        run_warnings = validate_run_inputs(data=data, profile=profile, plan=plan)

        result = run_forecast(
            data=data, profile=profile, plan=plan, exog_future=exog_future
        )

        all_warnings = run_warnings + result.get("warnings", [])

        return RunResult(
            profile      = profile,
            plan         = plan,
            code         = code,
            metric_value = result["metric_value"],
            metric_name  = result["metric_name"],
            predictions  = result["predictions"],
            intervals    = result["intervals"],
            warnings     = all_warnings,
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
            If None, a compact default set is loaded. Pass ``'all'`` as
            a single-element list to load every available skill.
        include_reference : bool, default False
            Whether to include the skforecast API reference in the prompt.
            The reference is ~195 KB and may exceed the context window of
            smaller models. Enable only with large-context models.

        Returns
        -------
        result : AskResult
            Contains the agent's structured response with optional profile,
            plan, code, and explanation.

        Notes
        -----
        This method requires an LLM. If `llm=None` was passed at init,
        `LLMRequiredError` is raised.
        """
        if self.llm is None:
            raise LLMRequiredError("ask")

        try:
            model = self._resolve_model()
            from .llm.agent import create_forecasting_agent

            agent = create_forecasting_agent(
                model=model,
                skills=skills,
                include_reference=include_reference,
            )
            _patch_event_loop()
            result = agent.run_sync(
                question, model_settings=self._build_model_settings()
            )

            plan = result.output if isinstance(result.output, ForecastPlan) else None
            return AskResult(
                plan=plan,
                explanation=str(result.output),
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
                if isinstance(data, (str, Path)):
                    import pandas as _pd
                    _df = _pd.read_csv(data)
                else:
                    _df = data
                # Use first numeric column as fallback target
                _numeric = _df.select_dtypes(include="number").columns
                _target = _numeric[0] if len(_numeric) > 0 else _df.columns[-1]
                result = self.recommend(
                    data=data,
                    target=_target,
                    steps=10,
                )
                return AskResult(
                    plan=result.plan,
                    explanation=(
                        f"[LLM unavailable] {result.plan.rationale}"
                    ),
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
            Data profile providing context. If None, a minimal profile is
            constructed from the plan metadata.

        Returns
        -------
        explanation : str
            Human-readable explanation of the plan.

        Notes
        -----
        This method requires an LLM. If `llm=None` was passed at init,
        `LLMRequiredError` is raised.
        """
        if self.llm is None:
            raise LLMRequiredError("explain")

        try:
            model = self._resolve_model()
            from .llm.prompts import build_explain_prompt

            if profile is None:
                profile = DataProfile(
                    n_series=1,
                    n_observations=0,
                    index_type="datetime",
                    target="unknown",
                )

            from pydantic_ai import Agent

            explain_agent = Agent(
                model,
                output_type=str,
                system_prompt="You are a forecasting expert. Explain plans clearly.",
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
                f"LLM call failed ({exc}), using deterministic rationale.",
                UserWarning,
                stacklevel=2,
            )
            return f"[LLM unavailable] {plan.rationale}"

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

        For Ollama models, sets ``num_ctx`` to ensure the context window
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


def _patch_event_loop() -> None:
    """
    Apply ``nest_asyncio`` when an event loop is already running.

    This enables ``run_sync()`` to work inside Jupyter notebooks and
    other environments that already have an active asyncio event loop.
    The patch is applied at most once per process.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # No running loop — nothing to patch

    if not getattr(loop, "_nest_patched", False):
        import nest_asyncio

        nest_asyncio.apply()
