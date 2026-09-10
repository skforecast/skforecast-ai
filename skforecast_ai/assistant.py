################################################################################
#                          ForecastingAssistant                                #
#                                                                              #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import sys
import warnings
from pathlib import Path
from typing import Any
import pandas as pd

if sys.version_info >= (3, 12):
    from typing import Unpack
else:
    from typing_extensions import Unpack
from skforecast.model_selection import TimeSeriesFold
from ._constants import FORECASTER_TASK_TYPES, OLLAMA_MAX_CONTEXT_TOKENS
from .exceptions import (
    AllCandidatesFailedError,
    CandidateFailedWarning,
    DataSentToLLMWarning,
    LLMCallError,
    LLMRequiredError,
    UnrecommendedForecasterWarning,
)
from .execution import run_backtest, run_forecast
from .execution.backtesting_runner import render_backtesting_script
from .execution.comparison import (
    aggregate_metrics,
    build_comparison_explanation,
    build_comparison_table,
    compare_sort_key,
    resolve_compare_candidates,
)
from .execution.forecast_runner import render_forecast_script
from .rendering.backtesting import _emit_cv_configuration
from .llm import (
    build_ollama_settings,
    compute_skill_token_budget,
    create_model,
    ensure_ollama_reachable,
    estimate_context_tokens,
    estimate_prompt_tokens,
    select_skills,
)
from .llm.refinement import configure_cv_with_llm, refine_features_with_llm
from .llm.runtime import run_agent_sync
from .profiling import create_data_profile, resolve_end_train
from .recommendation import (
    _build_profile_explanation,
    build_plan_explanation,
    build_forecaster_kwargs,
    check_exog_usage,
    compute_series_pacf,
    derive_cv_defaults,
    derive_preprocessing_steps,
    finalize_lags,
    resolve_cv_config,
    select_calendar_encoding,
    select_calendar_features,
    select_dropna_from_series,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_metric,
    select_task_type_from_forecaster,
    select_transformer_exog,
    select_transformer_series,
    select_window_features,
)
from .schemas import (
    REFINE_PLAN_OVERRIDE_KEYS,
    AskResult,
    BacktestResult,
    CandidateConfig,
    CandidateFailure,
    CodeGenerationResult,
    ComparisonResult,
    CVResult,
    ExplainableResult,
    ForecastingProfile,
    ForecastPlan,
    ForecastResult,
    RefinePlanOverrides,
)
from ._utils import (
    _resolve_data_and_target,
    _resolve_inputs_with_profile,
    _strip_code_blocks,
    _unwrap_cv,
    _validate_forecast_mode,
    _validate_max_window_size,
    _validate_task_input,
    _validate_window_features,
    _warn_if_plan_overrides_ignored,
)


class ForecastingAssistant:
    """
    AI-powered forecasting assistant built on skforecast.

    Analyses a time series dataset, selects a forecaster and estimator,
    produces a ready-to-run Python script, and optionally executes it,
    returning predictions, metrics, and the exact code that generated them.

    All modeling decisions are deterministic and reproducible. An optional
    LLM adds natural-language explanations and Q&A without influencing
    any recommendation.

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
        Whether raw values from the dataset supplied to a method (for
        example via `data`) may be sent to the LLM. When False, only
        metadata (schema, summary stats) is shared with the LLM. This
        governs input data only: a result passed to `ask()` carries its
        own predictions, which are always included so the LLM can
        discuss specific forecast values.

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

    Notes
    -----
    Four workflows are available:

    Fast path: call a single method that handles everything internally:

    - `forecast_code()` profiles the data, builds a plan, and returns a
    ready-to-run Python script.
    - `forecast()` does the same and also executes the forecast,
    returning predictions and metrics.

    Step-by-step path: for full control over each stage:

    - `profile()` inspects the dataset and selects the recommended
    forecaster and estimator (with alternative candidates).
    - `plan()` takes the profile and derives the detailed configuration
    (lags, metric, preprocessing, intervals, NaN handling).
    - `refine_plan()` adjusts an existing plan with user overrides, or with
    LLM guidance when a `prompt` is provided (if desired).
    - `forecast_code()` generates a Python script (accepts pre-computed
    `profile` and `plan` for full control).
    - `forecast()` executes the workflow from a pre-computed profile and
    plan, returning predictions and metrics.

    Backtesting path: evaluate model performance with time series
    cross-validation:

    - `create_cv()` produces a `TimeSeriesFold` with smart defaults
    (optionally guided by an LLM prompt). Requires a profile and plan.
    - `backtest_code()` generates a backtesting script without executing
    it (accepts pre-computed `profile` and `plan`).
    - `backtest()` runs backtesting using the CV strategy and returns
    metrics, predictions, and reproducible code.

    Comparison path: evaluate several configurations side by side:

    - `compare()` backtests a set of candidate configurations with the
    same cross-validation strategy and returns a metric-ranked
    leaderboard plus the winning configuration as a reusable
    `BacktestResult`.

    `ask()` is an LLM-powered method (requires `llm` to be configured)
    available in any workflow. Pass it the object to explain as `context`
    (a profile, a generated script, a cross-validation strategy, or a
    result), or nothing to ask a general forecasting question.

    """

    def __init__(
        self,
        llm: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        send_data_to_llm: bool = False,
    ) -> None:
        
        self.llm              = llm
        self.base_url         = base_url
        self.api_key          = api_key
        self.send_data_to_llm = send_data_to_llm
        self._model           = None
        self._agent           = None
        self._cv_agent        = None
        self._plan_refinement_agent = None

    def profile(
        self,
        data: pd.Series | pd.DataFrame | str | Path,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
    ) -> ForecastingProfile:
        """
        Profile a dataset and select the recommended forecaster and estimator.

        Assembles the data profile and selects the recommended forecaster,
        estimator, and their compatible candidates. The returned
        `ForecastingProfile` carries the `DataProfile` plus the coarse
        modeling decisions.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path
            Input dataset, a single series, or path to a CSV file. When a
            pandas Series is passed, the target is derived from its name.
        target : str, list of str, default None
            Name of the column to forecast. For wide-format multi-series,
            pass a list of column names where each column is a series.
            Optional only when `data` is a pandas Series, in which case the
            Series name is used (or `'y'` when the Series has no name).
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
        data, target = _resolve_data_and_target(data, target)

        data_profile = create_data_profile(
            data             = data,
            target           = target,
            date_column      = date_column,
            series_id_column = series_id_column,
            data_path        = data_path,
        )

        forecaster, forecaster_candidates = select_forecaster_and_candidates(data_profile)
        task_type = select_task_type_from_forecaster(forecaster)

        series_pacf = compute_series_pacf(data=data, profile=data_profile)
        window_features = select_window_features(
                              task_type      = task_type,
                              n_observations = data_profile.span_index_length,
                              frequency      = data_profile.frequency,
                          )

        calendar_features = select_calendar_features(
                                task_type      = task_type,
                                frequency      = data_profile.frequency,
                                n_observations = data_profile.span_index_length,
                            )

        estimator, estimator_candidates = select_estimator_and_candidates(
            task_type=task_type, n_observations=data_profile.n_total_observations
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
            series_pacf           = series_pacf,
            window_features       = window_features,
            calendar_features     = calendar_features,
            explanation           = explanation,
        )

    def plan(
        self,
        profile: ForecastingProfile,
        steps: int,
        interval: list[float] | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        lags: int | list[int] | None = None,
        window_features: list[dict[str, list[str] | int]] | None = None,
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
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` (e.g. `[0.1, 0.9]` for 80 % interval). If
            None, no prediction intervals are computed.
        forecaster : str, default None
            Explicit forecaster class name to override the profile
            recommendation. When it is not in
            `profile.forecaster_candidates` but is a supported
            forecaster, it is used anyway and an
            `UnrecommendedForecasterWarning` is issued.
        estimator : str, default None
            Explicit estimator class name to override the profile
            recommendation (e.g. `'HistGradientBoostingRegressor'`).
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200, 'learning_rate': 0.05}`). Merged
            on top of built-in defaults (`random_state`, silencing
            flags). User values take precedence.
        lags : int, list of int, default None
            Explicit lag configuration. If provided, bypasses the
            deterministic PACF-based lag selection.
        window_features : list of dict, default None
            Explicit window (rolling) features configuration. Each dict
            must contain the keys `'stats'` (a list of rolling statistics)
            and `'window_size'` (a scalar int applied to every stat in
            that same dict), for example `[{'stats': ['mean', 'std'],
            'window_size': 3}, {'stats': ['mean'], 'window_size': 24},
            {'stats': ['mean'], 'window_size': 168}]`. To combine several
            window sizes, add one dict per size. Allowed stats are
            `'mean'`, `'std'`, `'min'`, `'max'`, `'sum'`, `'median'`,
            `'ratio_min_max'`, `'coef_variation'`, and `'ewm'`. If
            provided, bypasses the deterministic window feature selection.
            deterministic window feature selection.

        Returns
        -------
        plan : ForecastPlan
            Detailed forecasting plan.
        """

        data_profile = profile.data_profile

        fc = profile.forecaster
        if forecaster is not None:
            if forecaster not in profile.forecaster_candidates:
                if forecaster not in FORECASTER_TASK_TYPES:
                    raise ValueError(
                        f"Forecaster '{forecaster}' is not compatible with this "
                        f"profile. Available candidates: "
                        f"{profile.forecaster_candidates}."
                    )
                warnings.warn(
                    f"Forecaster '{forecaster}' is not among the recommended "
                    f"candidates for this profile "
                    f"({profile.forecaster_candidates}), but it is used as "
                    f"requested. It may be slow or perform poorly on this data.",
                    UnrecommendedForecasterWarning,
                )
            fc = forecaster

        task_type = select_task_type_from_forecaster(fc)

        # Reject inputs incompatible with the resolved task type
        # (single-series tasks with multi-series input; multivariate with
        # series of different lengths).
        _validate_task_input(data_profile, task_type)

        n_obs_total = data_profile.n_total_observations

        # Recompute the estimator only when the task type changed.
        if task_type != profile.task_type:
            est, _ = select_estimator_and_candidates(
                task_type      = task_type,
                n_observations = n_obs_total,
            )
        else:
            est = profile.estimator

        if estimator is not None:
            est = estimator

        if task_type in ("statistical", "foundation"):
            final_lags = None
            final_window_features = None
            transformer_series = None
            transformer_exog = None
            dropna_from_series = None
            calendar_features = None
        else:
            # Explicit lag/window overrides (manual or LLM-supplied) bypass the
            # deterministic PACF selection and its budget guard, so validate
            # them against the data budget before building the forecaster.
            if window_features is not None:
                _validate_window_features(window_features)

            if lags is not None or window_features is not None:
                _validate_max_window_size(
                    lags              = lags,
                    window_features   = window_features,
                    span_index_length = data_profile.span_index_length
                )

            if lags is not None:
                final_lags = lags
            else:
                # Direct forecasters lose `steps - 1` extra rows beyond the
                # `window_size` (the last-step regressor needs the target at
                # t + steps), so reserve them from the lag budget. Recursive
                # forecasters reserve nothing.
                n_reserved_rows = steps - 1 if "Direct" in fc else 0
                final_lags = finalize_lags(
                    series_pacf     = profile.series_pacf,
                    task_type       = task_type,
                    n_observations  = data_profile.span_index_length,
                    frequency       = data_profile.frequency,
                    n_reserved_rows = n_reserved_rows,
                )

            if window_features is not None:
                final_window_features = window_features
            else:
                final_window_features = profile.window_features

            if profile.calendar_features:
                calendar_features = {
                    "features": profile.calendar_features,
                    "encoding": select_calendar_encoding(est, task_type),
                }
            else:
                calendar_features = None

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
            lags               = final_lags,
            window_features    = final_window_features,
            calendar_features  = calendar_features,
            transformer_series = transformer_series,
            transformer_exog   = transformer_exog,
            dropna_from_series = dropna_from_series
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
            lags               = final_lags,
            window_features    = final_window_features,
            interval_method    = interval_method,
            dropna_from_series = dropna_from_series,
            use_exog           = use_exog,
            metric_explanation = metric_explanation,
            calendar_features  = calendar_features,
            task_type          = task_type,
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
        prompt: str | None = None,
        **overrides: Unpack[RefinePlanOverrides],
    ) -> ForecastPlan:
        """
        Re-derive a forecast plan applying user overrides or LLM guidance.

        Operates in two modes:

        - Deterministic mode (`prompt=None`): takes an existing plan and a
          set of overrides, then calls `plan()` with the merged parameters.
          Only the overridden fields change; everything else is re-derived
          deterministically from the original profile.
        - LLM mode (`prompt` provided): a specialized agent interprets the
          natural-language domain knowledge and suggests `lags` and
          `window_features`, which are merged on top of the deterministic
          plan. The agent's reasoning is appended to the returned plan's
          `explanation`.

        Supported overrides: `forecaster`, `estimator`, `estimator_kwargs`,
        `steps`, `interval`, `lags`, `window_features` (see
        `RefinePlanOverrides`). What matters is whether a key is passed:
        an omitted key keeps the value of `plan`, while a key passed as
        None asks for the deterministic default (`interval=None` removes
        the prediction intervals, `lags=None` re-runs the PACF-based
        selection, `estimator_kwargs=None` resets the hyperparameters).

        Note that `lags` and `window_features` default to the values
        already stored in `plan.forecaster_kwargs`, so refining an
        unrelated field (e.g. `steps`) preserves the existing features
        rather than re-running the PACF-based selection. The
        `llm_refined_fields` marks of the original plan are kept for the
        fields whose value is carried over unchanged. The `end_train` split
        boundary is not kept: a refined plan starts in prediction mode, so
        pass `test_size` again to evaluate it.

        In LLM mode, explicit `lags`/`window_features` overrides take
        precedence over the LLM suggestion (a `UserWarning` is emitted for
        each shadowed field, and a note recording the overridden field(s) is
        appended to the explanation). When both are supplied explicitly, the
        LLM has nothing left to decide and is not called. LLM mode does not
        apply to `task_type` in `('statistical', 'foundation')`, which do not
        use lags or window features; the prompt is ignored with a
        `UserWarning`. When the agent omits a field, or the LLM call fails or
        its suggestion cannot satisfy the data budget, that field keeps the
        plan's existing value (a `UserWarning` is emitted on failure).

        Parameters
        ----------
        profile : ForecastingProfile
            Original profile that produced the plan.
        plan : ForecastPlan
            Existing plan to refine.
        prompt : str, default None
            Natural-language domain knowledge used to guide LLM refinement of
            `lags` and `window_features`. When None, only the explicit
            overrides are applied. Requires an LLM to be configured.
        **overrides : Unpack[RefinePlanOverrides]
            Keyword arguments to override. Accepted keys:
            `forecaster`, `estimator`, `estimator_kwargs`, `steps`,
            `interval`, `lags`, `window_features`. Typed through
            `RefinePlanOverrides`, so editors autocomplete them and type
            checkers reject unknown names; unknown keys also raise
            `ValueError` at run time.

        Returns
        -------
        plan : ForecastPlan
            Updated plan with overrides (and any LLM refinement) applied. In
            LLM mode, the agent's reasoning is appended to `plan.explanation`.
        """

        allowed_keys = REFINE_PLAN_OVERRIDE_KEYS
        invalid_keys = set(overrides) - allowed_keys
        if invalid_keys:
            raise ValueError(
                f"Invalid override keys: {sorted(invalid_keys)}. "
                f"Allowed keys: {sorted(allowed_keys)}."
            )
        # Snapshot taken before the LLM branch injects its suggestions into
        # `overrides`, so that an inherited LLM mark is dropped only for a
        # field the caller overrode explicitly.
        explicit_keys = set(overrides)

        reasoning = None
        shadowed_fields: list[str] = []
        llm_applied_fields: list[str] = []
        if prompt is not None:
            if self.llm is None:
                raise LLMRequiredError("refine_plan")

            if plan.task_type in ("statistical", "foundation"):
                warnings.warn(
                    f"LLM plan refinement does not apply to task_type "
                    f"'{plan.task_type}' (no lags/window_features to refine). "
                    f"Ignoring prompt.",
                    UserWarning,
                    stacklevel=2,
                )
            elif "lags" in overrides and "window_features" in overrides:
                warnings.warn(
                    "Prompt ignored: both lags and window_features were set "
                    "explicitly, leaving nothing for the LLM to decide.",
                    UserWarning,
                    stacklevel=2,
                )
            else:
                # Fail fast when an explicit lags/window_features override
                # already exceeds the data budget, so an LLM call is not spent
                # only for self.plan() to reject the explicit value afterwards.
                explicit_lags = overrides.get("lags")
                explicit_window_features = overrides.get("window_features")
                if explicit_window_features is not None:
                    _validate_window_features(explicit_window_features)
                if explicit_lags is not None or explicit_window_features is not None:
                    _validate_max_window_size(
                        lags              = explicit_lags,
                        window_features   = explicit_window_features,
                        span_index_length = profile.data_profile.span_index_length,
                    )

                llm_lags, llm_window_features, reasoning = (
                    refine_features_with_llm(
                        agent   = self._resolve_plan_refinement_agent(),
                        profile = profile,
                        plan    = plan,
                        prompt  = prompt,
                    )
                )
                # Category-A precedence: an explicit lags/window_features
                # override wins over the LLM suggestion (warn and record each
                # shadowed field). Otherwise inject the LLM value only when the
                # agent actually suggested one; a field the agent omitted
                # (None), or a failed call (reasoning=None), preserves the
                # plan's existing value rather than re-running the
                # deterministic selection.
                if reasoning is not None:
                    llm_features = {
                        "lags": llm_lags,
                        "window_features": llm_window_features,
                    }
                    for field, value in llm_features.items():
                        if value is None:
                            continue
                        if field in overrides:
                            shadowed_fields.append(field)
                            warnings.warn(
                                f"Explicit {field} override shadowed the LLM "
                                f"suggestion.",
                                UserWarning,
                                stacklevel=2,
                            )
                        else:
                            overrides[field] = value
                            llm_applied_fields.append(field)

        steps = overrides.get("steps", plan.steps)
        forecaster = overrides.get("forecaster", plan.forecaster)
        estimator = overrides.get("estimator", plan.estimator)
        estimator_kwargs = overrides.get("estimator_kwargs", plan.estimator_kwargs or None)
        interval = overrides.get("interval", plan.interval)
        lags = overrides.get("lags", plan.forecaster_kwargs.get("lags"))
        window_features = overrides.get("window_features", plan.forecaster_kwargs.get("window_features"))

        refined_plan = self.plan(
            profile          = profile,
            steps            = steps,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            interval         = interval,
            lags             = lags,
            window_features  = window_features,
        )

        # `self.plan()` returns a fresh plan that knows nothing about the
        # original one, so its LLM marks would otherwise be lost. A mark is
        # inherited only when the marked value itself was carried over: the
        # field was neither overridden explicitly nor re-suggested by the
        # LLM, and the refined plan still holds the same value. Switching to
        # a forecaster family without lags drops the value and the mark.
        inherited_fields = [
            field
            for field in plan.llm_refined_fields
            if field not in explicit_keys
            and field not in llm_applied_fields
            and plan.forecaster_kwargs.get(field) is not None
            and refined_plan.forecaster_kwargs.get(field)
            == plan.forecaster_kwargs.get(field)
        ]
        refined_plan.llm_refined_fields = inherited_fields + llm_applied_fields

        if reasoning is not None:
            refined_plan.explanation += (
                f"\n\nLLM Refinement Reasoning:\n{reasoning}"
            )
            if shadowed_fields:
                # The LLM's narrative may describe a field that an explicit
                # override replaced. Record which fields actually took
                # precedence so the persisted explanation is not misleading.
                refined_plan.explanation += (
                    f"\n\nNote: explicit override(s) took precedence over the "
                    f"LLM suggestion for: {', '.join(shadowed_fields)}."
                )
            if llm_applied_fields:
                # LLM-suggested features are hypotheses, not measured
                # improvements. Make the lack of validation explicit so the
                # user does not read the plan as a proven accuracy gain.
                refined_plan.explanation += (
                    "\n\nNote: the LLM-suggested "
                    f"{' and '.join(llm_applied_fields)} are hypotheses, not "
                    "validated improvements. Confirm any expected accuracy "
                    "gain before relying on them."
                )

        return refined_plan

    def forecast_code(
        self,
        data: pd.Series | pd.DataFrame | str | Path | None = None,
        steps: int | None = None,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        exog: pd.DataFrame | None = None,
        interval: list[float] | None = None,
        test_size: int | float | str | pd.Timestamp | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        lags: int | list[int] | None = None,
        window_features: list[dict[str, list[str] | int]] | None = None,
        profile: ForecastingProfile | None = None,
        plan: ForecastPlan | None = None,
    ) -> CodeGenerationResult:
        """
        Profile, plan, and generate a complete forecasting script.

        Convenience wrapper that chains `profile()`, `plan()`,
        and code generation in a single call. Pre-computed `profile`
        and/or `plan` can be passed to skip those stages (e.g. after
        modifying the plan with `refine_plan()`).

        The method operates in one of two modes depending on `test_size`:

        - Evaluation mode (`test_size` is set): the data is split into
        train and test sets, the forecaster is trained on the training
        set, predictions are made for the test set and metrics are
        computed against the held-out observations.
        - Prediction mode (`test_size` is None, the default): the
        forecaster is trained on all available data and forecasts the
        future. No metrics are returned because there is no ground
        truth to compare against. When the data contains exogenous
        variables, future values must be supplied through `exog`.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path, default None
            Input dataset, a single series, or path to a CSV file. Required
            when `profile` is not provided. When a pandas Series is passed,
            the target is derived from its name.
        steps : int, default None
            Forecast horizon (number of steps ahead to predict). Required
            when `plan` is not provided. When a `plan` is given it defaults
            to `plan.steps` and must match it if given.
        target : str, list of str, default None
            Name of the column to forecast. Required when `profile`
            is not provided, unless `data` is a pandas Series (the Series
            name is used instead). For wide-format multi-series, pass a
            list of column names where each column is a series.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        date_column : str, default None
            Name of the column containing timestamps. When None, the
            index of `data` is assumed to be a DatetimeIndex.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        series_id_column : str, default None
            Name of the column identifying individual series (long-format
            multi-series input). When None, the data is treated as
            single-series or wide-format multi-series.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        exog : pandas DataFrame, default None
            Future exogenous variables covering the forecast horizon.
            Mirrors `forecast()` for signature consistency. Because this
            method only generates code (the rendered prediction-mode
            script loads the future values from `'exog_future.csv'` at run
            time), `exog` is optional here and is used only to validate
            the inputs: it must not be combined with `test_size`, and it
            must not be supplied when the data has no exogenous columns.
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` (e.g. `[0.1, 0.9]` for 80 % interval). When
            None, no prediction intervals are computed.
        test_size : int, float, str, pandas Timestamp, default None
            Size or start of the test set, selecting the evaluation or
            prediction mode described above.

            - int: the last `test_size` observations form the test set.
            - float in `(0, 1)`: the last fraction `test_size` of the
            observations form the test set.
            - str or pandas Timestamp: the first timestamp of the test
            set (the split boundary).

            When None (default), the method runs in prediction mode.
        forecaster : str, default None
            Explicit forecaster class name to use instead of the
            recommended one (e.g. `'ForecasterRecursive'`,
            `'ForecasterDirect'`, `'ForecasterRecursiveMultiSeries'`).
            When None, the most suitable forecaster is selected
            automatically from the characteristics of the data.
        estimator : str, default None
            Explicit regressor class name to use instead of the
            recommended one (e.g. `'HistGradientBoostingRegressor'`,
            `'LGBMRegressor'`). When None, a suitable estimator is
            selected automatically based on the dataset size.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200, 'learning_rate': 0.05}`). Merged on
            top of built-in defaults (`random_state` and silencing
            flags), with user values taking precedence. When None, only
            the built-in defaults are used.
        lags : int, list of int, default None
            Explicit lag configuration. An integer uses lags 1 to `lags`;
            a list uses the specified lags. When None, lags are selected
            automatically from the partial autocorrelation of the series.
        window_features : list of dict, default None
            Explicit window (rolling) features configuration. Each dict
            must contain the keys `'stats'` (a list of rolling statistics)
            and `'window_size'` (a scalar int applied to every stat in
            that same dict), for example `[{'stats': ['mean', 'std'],
            'window_size': 3}, {'stats': ['mean'], 'window_size': 24},
            {'stats': ['mean'], 'window_size': 168}]`. To combine several
            window sizes, add one dict per size. Allowed stats are
            `'mean'`, `'std'`, `'min'`, `'max'`, `'sum'`, `'median'`,
            `'ratio_min_max'`, `'coef_variation'`, and `'ewm'`. When None,
            window features are selected automatically from the
            characteristics of the data.
        profile : ForecastingProfile, default None
            Pre-computed profile to skip profiling. If None, profiling
            is performed from `data`.
        plan : ForecastPlan, default None
            Pre-computed plan to skip planning. If None, a plan is
            generated from the profile. Requires `profile` to also be
            provided.

        Returns
        -------
        result : CodeGenerationResult
            Generated forecasting script and the decisions behind it.
            Contains the following attributes:

            - profile: profile of the input dataset and high-level
            modeling decisions.
            - plan: detailed forecasting plan.
            - code: generated Python script.
        """

        # A supplied profile is what the script is rendered from. When data
        # is supplied as well, check it is the dataset the profile describes.
        if profile is not None and data is not None:
            _resolve_inputs_with_profile(
                data, target, date_column, series_id_column, profile
            )

        profile, plan = self._prepare_forecast(
            data             = data,
            target           = target,
            date_column      = date_column,
            series_id_column = series_id_column,
            steps            = steps,
            exog             = exog,
            interval         = interval,
            test_size        = test_size,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            lags             = lags,
            window_features  = window_features,
            profile          = profile,
            plan             = plan,
            require_exog     = False,
        )

        code = render_forecast_script(
            profile=profile.data_profile, plan=plan
        ).full_script

        return CodeGenerationResult(
            profile = profile,
            plan    = plan,
            code    = code,
        )

    def forecast(
        self,
        data: pd.Series | pd.DataFrame | str | Path,
        steps: int | None = None,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        exog: pd.DataFrame | None = None,
        interval: list[float] | None = None,
        test_size: int | float | str | pd.Timestamp | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        lags: int | list[int] | None = None,
        window_features: list[dict[str, list[str] | int]] | None = None,
        profile: ForecastingProfile | None = None,
        plan: ForecastPlan | None = None,
    ) -> ForecastResult:
        """
        Execute a full forecasting workflow end-to-end.

        Convenience wrapper that chains `profile()`, `plan()`,
        validation and programmatic execution. Pre-computed `profile`
        and/or `plan` can be passed to skip those stages (e.g. after
        modifying the plan with `refine_plan()`).

        The method operates in one of two modes depending on `test_size`:

        - Evaluation mode (`test_size` is set): the data is split into
        train and test sets, the forecaster is trained on the training
        set, predictions are made for the test set and metrics are
        computed against the held-out observations.
        - Prediction mode (`test_size` is None, the default): the
        forecaster is trained on all available data and forecasts the
        future. No metrics are returned because there is no ground
        truth to compare against. When the data contains exogenous
        variables, future values must be supplied through `exog`.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path
            Input dataset, a single series, or path to a CSV file. When a
            pandas Series is passed, the target is derived from its name.
        steps : int, default None
            Forecast horizon (number of steps ahead to predict). Required
            when `plan` is not provided. When a `plan` is given it defaults
            to `plan.steps` and must match it if given.
        target : str, list of str, default None
            Name of the column to forecast. Optional only when `data` is a
            pandas Series (the Series name is used instead). For
            wide-format multi-series, pass a list of column names where
            each column is a series.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        date_column : str, default None
            Name of the column containing timestamps. When None, the
            index of `data` is assumed to be a DatetimeIndex.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        series_id_column : str, default None
            Name of the column identifying individual series (long-format
            multi-series input). When None, the data is treated as
            single-series or wide-format multi-series.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        exog : pandas DataFrame, default None
            Future exogenous variables covering the forecast horizon
            (at least `steps` rows). Used only in prediction mode
            (`test_size=None`) and required there when the data contains
            exogenous variables. Must not be combined with `test_size`:
            in evaluation mode the test-set exogenous values are taken
            from the split.
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` (e.g. `[0.1, 0.9]` for 80 % interval). When
            None, no prediction intervals are computed.
        test_size : int, float, str, pandas Timestamp, default None
            Size or start of the test set, selecting the evaluation or
            prediction mode described above.

            - int: the last `test_size` observations form the test set.
            - float in `(0, 1)`: the last fraction `test_size` of the
            observations form the test set.
            - str or pandas Timestamp: the first timestamp of the test
            set (the split boundary).

            When None (default), the method runs in prediction mode.
        forecaster : str, default None
            Explicit forecaster class name to use instead of the
            recommended one (e.g. `'ForecasterRecursive'`,
            `'ForecasterDirect'`, `'ForecasterRecursiveMultiSeries'`).
            When None, the most suitable forecaster is selected
            automatically from the characteristics of the data.
        estimator : str, default None
            Explicit regressor class name to use instead of the
            recommended one (e.g. `'HistGradientBoostingRegressor'`,
            `'LGBMRegressor'`). When None, a suitable estimator is
            selected automatically based on the dataset size.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200, 'learning_rate': 0.05}`). Merged on
            top of built-in defaults (`random_state` and silencing
            flags), with user values taking precedence. When None, only
            the built-in defaults are used.
        lags : int, list of int, default None
            Explicit lag configuration. An integer uses lags 1 to `lags`;
            a list uses the specified lags. When None, lags are selected
            automatically from the partial autocorrelation of the series.
        window_features : list of dict, default None
            Explicit window (rolling) features configuration. Each dict
            must contain the keys `'stats'` (a list of rolling statistics)
            and `'window_size'` (a scalar int applied to every stat in
            that same dict), for example `[{'stats': ['mean', 'std'],
            'window_size': 3}, {'stats': ['mean'], 'window_size': 24},
            {'stats': ['mean'], 'window_size': 168}]`. To combine several
            window sizes, add one dict per size. Allowed stats are
            `'mean'`, `'std'`, `'min'`, `'max'`, `'sum'`, `'median'`,
            `'ratio_min_max'`, `'coef_variation'`, and `'ewm'`. When None,
            window features are selected automatically from the
            characteristics of the data.
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
            Executed forecast and the decisions behind it. Contains the
            following attributes:

            - profile: profile of the input dataset and high-level
            modeling decisions.
            - plan: detailed forecasting plan that was executed.
            - code: generated Python script equivalent to the execution.
            - predictions: forecasted values for the requested steps,
            including the interval columns when `interval` is set.
            - metrics: evaluation metrics, one row per series. None in
            prediction mode (`test_size=None`), where there is no ground
            truth to evaluate against.

        Notes
        -----
        This method executes the same code that `forecast_code()`
        produces, ensuring perfect fidelity between the inspectable
        script (`ForecastResult.code`) and the actual execution.
        """

        data_df, target, date_column, series_id_column = (
            _resolve_inputs_with_profile(
                data, target, date_column, series_id_column, profile
            )
        )

        profile, plan = self._prepare_forecast(
            data             = data_df,
            target           = target,
            date_column      = date_column,
            series_id_column = series_id_column,
            steps            = steps,
            exog             = exog,
            interval         = interval,
            test_size        = test_size,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            lags             = lags,
            window_features  = window_features,
            profile          = profile,
            plan             = plan,
            require_exog     = True,
        )

        result = run_forecast(
            data    = data_df,
            profile = profile.data_profile,
            plan    = plan,
            exog    = exog,
        )

        return ForecastResult(
            profile     = profile,
            plan        = plan,
            code        = result["rendered_code"].full_script,
            metrics     = result["metrics"],
            predictions = result["predictions"],
        )

    def create_cv(
        self,
        profile: ForecastingProfile,
        plan: ForecastPlan,
        prompt: str | None = None,
        initial_train_size: int | str | pd.Timestamp | None = None,
        fold_stride: int | None = None,
        refit: bool | int | None = None,
        fixed_train_size: bool | None = None,
        gap: int | None = None,
        skip_folds: int | list[int] | None = None,
        allow_incomplete_fold: bool | None = None,
    ) -> CVResult:
        """
        Generate a time series cross-validation strategy for backtesting.

        Produces a `TimeSeriesFold` [1]_ configured with smart defaults
        derived from the profile and plan. 
        
        Explicit keyword arguments override defaults. If None, they are 
        automatically determined based on the profile and plan characteristics.

        Parameters
        ----------
        profile : ForecastingProfile
            Output of `profile()`.
        plan : ForecastPlan
            Output of `plan()`.
        prompt : str, default None
            Natural language description of the evaluation scenario.
            Requires an LLM to be configured. If None or no LLM is
            available, deterministic defaults are used.
        initial_train_size : int, str, pandas Timestamp, default None
            Number of observations used for initial training. 
            
            - If `None`, initial training size is automatically determined based 
            on the profile and plan.
            - If an integer, the number of observations used for initial training.
            - If a date string or pandas Timestamp, it is the last date included in 
            the initial training set.
        fold_stride : int, default None
            Number of observations that the start of the test set advances between
            consecutive folds.

            - If `None`, it defaults to the same value as `steps`, meaning that folds
            are placed back-to-back without overlap.
            - If `fold_stride < steps`, test sets overlap and multiple forecasts will
            be generated for the same observations.
            - If `fold_stride > steps`, gaps are left between consecutive test sets.
            **New in version 0.18.0**
        refit : bool, int, default None
            Whether to refit the forecaster in each fold.

            - If `None`, refit behavior is automatically determined based on the 
            profile and plan.
            - If `True`, the forecaster is refitted in each fold.
            - If `False`, the forecaster is trained only in the first fold.
            - If an integer, the forecaster is trained in the first fold and then refitted
            every `refit` folds.
        fixed_train_size : bool, default None
            Whether the training size is fixed or increases in each fold.
        gap : int, default None
            Number of observations between the end of the training set and the start of the
            test set.
        skip_folds : int, list, default None
            Number of folds to skip.

            - If an integer, every 'skip_folds'-th is returned.
            - If a list, the indexes of the folds to skip.

            For example, if `skip_folds=3` and there are 10 folds, the returned folds are
            0, 3, 6, and 9. If `skip_folds=[1, 2, 3]`, the returned folds are 0, 4, 5, 6, 7,
            8, and 9.
        allow_incomplete_fold : bool, default None
            Whether to allow the last fold to include fewer observations than `steps`.
            If `False`, the last fold is excluded if it is incomplete.

        Returns
        -------
        result : CVResult
            Cross-validation strategy and the decisions behind it. Pass it
            as `cv` to `backtest()`, `backtest_code()` or `compare()`, or
            as `result` to `ask()`. Contains the following attributes:

            - profile: profile the strategy was derived from.
            - plan: plan the strategy was derived from.
            - cv: configured `TimeSeriesFold` fold splitter.
            - cv_config: resolved `TimeSeriesFold` parameters plus the
            resulting `n_folds`.
            - code: Python snippet that builds the same `TimeSeriesFold`.
            - explanation: human-readable explanation of the chosen
            configuration (LLM reasoning first when a prompt was used).

        References
        ----------
        [1] Skforecast `TimeSeriesFold` API Reference:
            https://skforecast.org/latest/api/model_selection#skforecast.model_selection._split.TimeSeriesFold
        
        """

        span_index_length = profile.data_profile.span_index_length

        # -----------------------------------------------------------------
        # LLM path: when prompt is provided, use LLM for CV configuration
        # -----------------------------------------------------------------
        if prompt is not None and self.llm is None:
            raise LLMRequiredError("create_cv")

        # All CV parameters the LLM would otherwise decide. When every one is
        # set explicitly, the LLM has nothing left to decide, so skip the call.
        llm_decidable = (
            initial_train_size,
            refit,
            fixed_train_size,
            gap,
            fold_stride,
            skip_folds,
            allow_incomplete_fold,
        )
        use_llm = prompt is not None
        if use_llm and all(param is not None for param in llm_decidable):
            warnings.warn(
                "Prompt ignored: all CV parameters were set explicitly, "
                "leaving nothing for the LLM to decide.",
                UserWarning,
                stacklevel=2,
            )
            use_llm = False

        if use_llm:
            defaults = configure_cv_with_llm(
                           agent          = self._resolve_cv_agent(),
                           profile        = profile,
                           plan           = plan,
                           prompt         = prompt,
                           n_observations = span_index_length,
                       )
        else:
            # Compute deterministic defaults
            defaults = derive_cv_defaults(profile=profile, plan=plan)

        # Apply explicit overrides
        overrides = {
            "initial_train_size": initial_train_size,
            "refit": refit,
            "fixed_train_size": fixed_train_size,
            "gap": gap,
            "fold_stride": fold_stride,
            "skip_folds": skip_folds,
            "allow_incomplete_fold": allow_incomplete_fold,
        }
        for key, value in overrides.items():
            if value is not None:
                defaults[key] = value

        # Handle initial_train_size type conversion
        its = defaults["initial_train_size"]
        if isinstance(its, float):
            if not (0 < its < 1):
                raise ValueError(
                    f"initial_train_size as float must satisfy "
                    f"0 < value < 1, got {its}."
                )
            defaults["initial_train_size"] = int(its * span_index_length)

        # Instantiate TimeSeriesFold
        cv = TimeSeriesFold(
            steps                 = defaults["steps"],
            initial_train_size    = defaults["initial_train_size"],
            refit                 = defaults["refit"],
            fixed_train_size      = defaults["fixed_train_size"],
            gap                   = defaults["gap"],
            fold_stride           = defaults["fold_stride"],
            skip_folds            = defaults["skip_folds"],
            allow_incomplete_fold = defaults["allow_incomplete_fold"],
            differentiation       = defaults.get("differentiation"),
            verbose               = False,
        )

        # The LLM narrative is not a TimeSeriesFold parameter: keep it out
        # of the error message below and prepend it to the explanation.
        reasoning = defaults.pop("_reasoning", None)

        # Validate fold count. A date-based initial_train_size needs a
        # DatetimeIndex so `cv.split` can locate the split date; integer or
        # fractional sizes are validated against a plain RangeIndex.
        cv_config, cv_explanation = resolve_cv_config(cv, profile.data_profile)
        n_folds = cv_config["n_folds"]
        if n_folds < 2:
            raise ValueError(
                f"The resolved CV configuration produces only "
                f"{n_folds} fold(s). At least 2 are required. "
                f"Resolved parameters: {defaults}."
            )

        if reasoning:
            cv_explanation = f"{reasoning} {cv_explanation}"

        # The same snippet the backtesting script embeds, so the strategy
        # can be inspected and reproduced on its own.
        code_lines = ["from skforecast.model_selection import TimeSeriesFold", ""]
        _emit_cv_configuration(code_lines, cv)

        return CVResult(
            profile     = profile,
            plan        = plan,
            cv          = cv,
            cv_config   = cv_config,
            code        = "\n".join(code_lines).rstrip("\n") + "\n",
            explanation = cv_explanation,
        )

    def backtest_code(
        self,
        data: pd.Series | pd.DataFrame | str | Path,
        cv: TimeSeriesFold | CVResult,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        interval: list[float] | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        profile: ForecastingProfile | None = None,
        plan: ForecastPlan | None = None,
    ) -> CodeGenerationResult:
        """
        Profile, plan, and generate a complete backtesting script.

        Convenience wrapper that chains `profile()`, `plan()`, and
        backtesting code generation in a single call. Pre-computed
        `profile` and/or `plan` can be passed to skip those stages.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path
            Input dataset, a single series, or path to a CSV file. When a
            pandas Series is passed, the target is derived from its name.
        cv : TimeSeriesFold, CVResult
            Time series cross-validation fold splitter (output of
            `create_cv()` or user-constructed) [1]_.
            The `CVResult` returned by `create_cv()` is accepted as well;
            its `cv` splitter is used.
        target : str, list of str, default None
            Name of the column(s) to forecast. Optional only when `data`
            is a pandas Series (the Series name is used instead). For
            wide-format multi-series, pass a list of column names where
            each column is a series.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        date_column : str, default None
            Name of the column containing timestamps. When None, the
            index of `data` is assumed to be a DatetimeIndex.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        series_id_column : str, default None
            Name of the column identifying individual series (long-format
            multi-series input). When None, the data is treated as
            single-series or wide-format multi-series.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` (e.g. `[0.1, 0.9]` for 80 % interval). When
            None, no prediction intervals are computed.
        forecaster : str, default None
            Explicit forecaster class name to use instead of the
            recommended one (e.g. `'ForecasterRecursive'`,
            `'ForecasterDirect'`, `'ForecasterRecursiveMultiSeries'`).
            When None, the most suitable forecaster is selected
            automatically from the characteristics of the data.
        estimator : str, default None
            Explicit regressor class name to use instead of the
            recommended one (e.g. `'HistGradientBoostingRegressor'`,
            `'LGBMRegressor'`). When None, a suitable estimator is
            selected automatically based on the dataset size.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200, 'learning_rate': 0.05}`). Merged on
            top of built-in defaults (`random_state` and silencing
            flags), with user values taking precedence. When None, only
            the built-in defaults are used.
        profile : ForecastingProfile, default None
            Pre-computed profile to skip profiling.
        plan : ForecastPlan, default None
            Pre-computed plan to skip planning.

        Returns
        -------
        result : CodeGenerationResult
            Generated backtesting script and the decisions behind it.
            Contains the following attributes:

            - profile: profile of the input dataset and high-level
            modeling decisions.
            - plan: detailed forecasting plan.
            - code: generated Python backtesting script.

        Notes
        -----
        To customize `lags` or `window_features`, build the plan with
        `plan()` (or `refine_plan()`) and pass it via `plan`, then build a
        matching `cv` with `create_cv()`. This keeps the plan and the
        cross-validation configuration consistent.

        References
        ----------
        [1] Skforecast `TimeSeriesFold` API Reference:
            https://skforecast.org/latest/api/model_selection#skforecast.model_selection._split.TimeSeriesFold

        """

        cv = _unwrap_cv(cv)

        profile, plan = self._prepare_backtest(
            data             = data,
            target           = target,
            cv               = cv,
            date_column      = date_column,
            series_id_column = series_id_column,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            interval         = interval,
            profile          = profile,
            plan             = plan,
        )

        code = render_backtesting_script(
            profile=profile.data_profile, plan=plan, cv=cv
        ).full_script

        return CodeGenerationResult(
            profile = profile,
            plan    = plan,
            code    = code,
        )

    def backtest(
        self,
        data: pd.Series | pd.DataFrame | str | Path,
        cv: TimeSeriesFold | CVResult,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        interval: list[float] | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        profile: ForecastingProfile | None = None,
        plan: ForecastPlan | None = None,
        show_progress: bool = True,
    ) -> BacktestResult:
        """
        Execute backtesting with a pre-configured time series cross-validation 
        strategy (`TimeSeriesFold` [1]_).

        Chains `profile()`, `plan()`, and backtesting execution
        using the provided `TimeSeriesFold`. The `steps` parameter is
        inferred from `cv.steps`.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path
            Input dataset, a single series, or path to a CSV file. When a
            pandas Series is passed, the target is derived from its name.
        cv : TimeSeriesFold, CVResult
            Time series cross-validation fold splitter (output of `create_cv()`
            or user-constructed) [1]_.
            The `CVResult` returned by `create_cv()` is accepted as well;
            its `cv` splitter is used.
        target : str, list of str, default None
            Name of the column(s) to forecast. Optional only when `data`
            is a pandas Series (the Series name is used instead). For
            wide-format multi-series, pass a list of column names where
            each column is a series.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        date_column : str, default None
            Name of the column containing timestamps. When None, the
            index of `data` is assumed to be a DatetimeIndex.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        series_id_column : str, default None
            Name of the column identifying individual series (long-format
            multi-series input). When None, the data is treated as
            single-series or wide-format multi-series.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` (e.g. `[0.1, 0.9]` for 80 % interval). When
            None, no prediction intervals are computed.
        forecaster : str, default None
            Explicit forecaster class name to use instead of the
            recommended one (e.g. `'ForecasterRecursive'`,
            `'ForecasterDirect'`, `'ForecasterRecursiveMultiSeries'`).
            When None, the most suitable forecaster is selected
            automatically from the characteristics of the data.
        estimator : str, default None
            Explicit regressor class name to use instead of the
            recommended one (e.g. `'HistGradientBoostingRegressor'`,
            `'LGBMRegressor'`). When None, a suitable estimator is
            selected automatically based on the dataset size.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200, 'learning_rate': 0.05}`). Merged on
            top of built-in defaults (`random_state` and silencing
            flags), with user values taking precedence. When None, only
            the built-in defaults are used.
        profile : ForecastingProfile, default None
            Pre-computed profile to skip profiling.
        plan : ForecastPlan, default None
            Pre-computed plan to skip planning.
        show_progress : bool, default True
            Whether to display a progress bar during backtesting.

        Returns
        -------
        result : BacktestResult
            Backtesting outcome and the decisions behind it. Contains the
            following attributes:

            - profile: profile of the input dataset and high-level
            modeling decisions.
            - plan: detailed forecasting plan that was executed.
            - cv_config: resolved `TimeSeriesFold` parameters plus the
            resulting `n_folds`.
            - metrics: backtesting metric values returned by skforecast.
            - predictions: full backtest predictions across all folds.
            - code: generated Python script reproducing the workflow.
            - explanation: human-readable summary of the configuration
            and results.

        Notes
        -----
        The `data` DataFrame must include exogenous columns if the plan
        uses them. Exogenous variables are extracted automatically from
        `profile.data_profile.exog_columns`.

        To customize `lags` or `window_features`, build the plan with
        `plan()` (or `refine_plan()`) and pass it via `plan`, then build a
        matching `cv` with `create_cv()`. This keeps the plan and the
        cross-validation configuration consistent.

        References
        ----------
        [1] Skforecast `TimeSeriesFold` API Reference:
            https://skforecast.org/latest/api/model_selection#skforecast.model_selection._split.TimeSeriesFold
        
        """

        cv = _unwrap_cv(cv)

        data_df, target, date_column, series_id_column = (
            _resolve_inputs_with_profile(
                data, target, date_column, series_id_column, profile
            )
        )

        profile, plan = self._prepare_backtest(
            data             = data_df,
            target           = target,
            cv               = cv,
            date_column      = date_column,
            series_id_column = series_id_column,
            interval         = interval,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            profile          = profile,
            plan             = plan,
        )

        # Resolved CV parameters (with the fold count) and their explanation.
        cv_config, cv_explanation = resolve_cv_config(cv, profile.data_profile)

        result = run_backtest(
            data           = data_df,
            profile        = profile.data_profile,
            plan           = plan,
            cv             = cv,
            cv_explanation = cv_explanation,
            show_progress  = show_progress,
        )

        return BacktestResult(
            profile     = profile,
            plan        = plan,
            cv_config   = cv_config,
            metrics     = result["metrics"],
            predictions = result["predictions"],
            code        = result["rendered_code"].full_script,
            explanation = result["explanation"],
        )

    def compare(
        self,
        data: pd.Series | pd.DataFrame | str | Path,
        cv: TimeSeriesFold | CVResult,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        candidates: list[tuple[str, CandidateConfig]] | None = None,
        metric: str | list[str] | None = None,
        interval: list[float] | None = None,
        profile: ForecastingProfile | None = None,
        show_progress: bool = True,
    ) -> ComparisonResult:
        """
        Compare several forecaster configurations on the same data.

        Backtests each candidate configuration with the **same**
        cross-validation strategy and returns a metric-ranked leaderboard
        plus the winning configuration as a reusable `BacktestResult`.

        The dataset is profiled once and the profile is shared across all
        candidates; only the plan varies per candidate. Each candidate is
        evaluated through the same `plan()` + `backtest()` path, so every
        row carries a reproducible `code`. Ranking is a pure ascending sort
        of the metric column (all default metrics are error metrics where
        lower is better); the LLM never influences the outcome.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path
            Input dataset, a single series, or path to a CSV file. When a
            pandas Series is passed, the target is derived from its name.
        cv : TimeSeriesFold, CVResult
            Cross-validation strategy applied identically to every
            candidate. The `steps` value is inferred from `cv.steps`.
            The `CVResult` returned by `create_cv()` is accepted as well;
            its `cv` splitter is used.
        target : str, list of str, default None
            Name of the column(s) to forecast. Optional only when `data`
            is a pandas Series (the Series name is used instead). For
            wide-format multi-series, pass a list of column names.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        date_column : str, default None
            Name of the column containing timestamps. When None, the index
            of `data` is assumed to be a DatetimeIndex.
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        series_id_column : str, default None
            Name of the column identifying individual series (long-format
            multi-series input).
            When `profile` is provided, defaults to the value recorded in
            the profile and must match it if given.
        candidates : list of tuple of (str, CandidateConfig), default None
            Configurations to compare. Each entry is a `(name, config)`
            tuple, where `name` labels the row in the results table and
            `config` holds the forecaster/estimator settings. The `config`
            dict accepts the same override keys understood by `plan()`:
            `'forecaster'`, `'estimator'`, `'estimator_kwargs'`, `'lags'`,
            and `'window_features'` (see `CandidateConfig`). Names must be
            unique. When None, the set is built automatically from
            `profile.forecaster_candidates`.
        metric : str, list of str, default None
            Metric(s) computed per candidate. When a list is passed, the
            first metric is used to rank the table. When None, the plan
            default metric (and its metric panel) is used.
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` computed for every candidate. When None, no
            prediction intervals are computed.
        profile : ForecastingProfile, default None
            Pre-computed profile to skip profiling and guarantee a shared
            profile across candidates.
        show_progress : bool, default True
            Whether to display a progress bar across candidates.

        Returns
        -------
        result : ComparisonResult
            Ranked comparison of the candidate configurations. Contains
            the following attributes:

            - profile: shared profile used for every candidate.
            - cv_config: resolved `TimeSeriesFold` parameters plus the
            resulting `n_folds`, applied
            identically to every candidate.
            - results: ranked comparison table, one row per candidate
            sorted best to worst by `ranking_metric`.
            - candidates: mapping of candidate name to the full
            `BacktestResult` of every candidate that ran successfully,
            ordered best to worst.
            - failures: mapping of candidate name to a `CandidateFailure`
            describing why it failed. Empty when all candidates succeed.
            - ranking_metric: name of the metric used to sort `results`.
            - explanation: human-readable summary of the comparison.
            - best_name: name of the top-ranked candidate.
            - best_candidate: top-ranked candidate as a `BacktestResult`.

        Raises
        ------
        AllCandidatesFailedError
            If every candidate fails to run. The individual failures are
            available on the `failures` attribute of the raised error.
        ValueError
            If `metric` is an empty list, or if `candidates` is empty,
            contains a malformed entry, or repeats a name.

        Warns
        -----
        CandidateFailedWarning
            Once per failed candidate.

        Notes
        -----
        If a candidate fails to run, a `CandidateFailedWarning` is issued,
        its row records the error and is sorted last, and a
        `CandidateFailure` carrying the full traceback and the generated
        code is kept in `failures`. One bad configuration therefore never
        aborts the whole comparison. Ties keep input order, so the table
        is deterministic.

        The winning configuration, `best_candidate`, is a full
        `BacktestResult` carrying both a `profile` and a `plan`, which can
        be fed directly into `forecast()`, `backtest()`, or
        `forecast_code()`.
        """

        cv = _unwrap_cv(cv)

        data_df, target, date_column, series_id_column = (
            _resolve_inputs_with_profile(
                data, target, date_column, series_id_column, profile
            )
        )

        if profile is None:
            profile = self.profile(
                data             = data_df,
                target           = target,
                date_column      = date_column,
                series_id_column = series_id_column,
            )

        candidate_configs = resolve_compare_candidates(candidates, profile)

        # Resolve the ranking metric and the metric columns once, so the
        # table is consistent across candidates regardless of which ones
        # succeed. When `metric` is None the deterministic plan default is
        # used; otherwise the requested metrics override the plan panel.
        if metric is None:
            metric_override = None
            ranking_metric, _, metric_columns = select_metric(
                profile.data_profile
            )
        else:
            metric_override = [metric] if isinstance(metric, str) else list(metric)
            if not metric_override:
                raise ValueError("`metric` must not be an empty list.")
            ranking_metric = metric_override[0]
            metric_columns = metric_override

        steps = cv.steps

        # Shared CV parameters (with the fold count) and their explanation.
        # The folds are counted before any candidate runs, on the untouched
        # `cv`.
        cv_config, cv_explanation = resolve_cv_config(cv, profile.data_profile)

        iterator: Any = candidate_configs
        if show_progress:
            from tqdm.auto import tqdm

            iterator = tqdm(candidate_configs, desc="Comparing forecasters")

        rows: list[tuple[dict, float]] = []
        ranked: list[tuple[str, BacktestResult, float]] = []
        failures: dict[str, CandidateFailure] = {}

        for name, config in iterator:
            row: dict[str, Any] = {
                "name": name,
                "forecaster": config.get("forecaster") or profile.forecaster,
                "estimator": config.get("estimator"),
                "error": None,
            }
            for col in metric_columns:
                row[col] = float("nan")
            ranking_value = float("nan")

            try:
                cand_plan = self.plan(
                    profile          = profile,
                    steps            = steps,
                    forecaster       = config.get("forecaster"),
                    estimator        = config.get("estimator"),
                    estimator_kwargs = config.get("estimator_kwargs"),
                    lags             = config.get("lags"),
                    window_features  = config.get("window_features"),
                    interval         = interval,
                )
                if metric_override is not None:
                    cand_plan.metrics_to_compute = list(metric_override)
                    cand_plan.metric = metric_override[0]

                row["forecaster"] = cand_plan.forecaster
                row["estimator"] = cand_plan.estimator

                bt = self.backtest(
                    data             = data_df,
                    cv               = cv,
                    target           = target,
                    date_column      = date_column,
                    series_id_column = series_id_column,
                    profile          = profile,
                    plan             = cand_plan,
                    show_progress    = False,
                )
                agg = aggregate_metrics(bt.metrics)
                for col in metric_columns:
                    row[col] = agg.get(col, float("nan"))
                ranking_value = agg.get(ranking_metric, float("nan"))
                ranked.append((name, bt, ranking_value))
            except Exception as exc:
                failure = CandidateFailure.from_exception(exc)
                failures[name] = failure
                row["error"] = failure.summary()
                warnings.warn(
                    f"Candidate '{name}' failed and is ranked last: "
                    f"{failure.summary()}. The full traceback is available in "
                    f"`ComparisonResult.failures['{name}'].traceback`.",
                    CandidateFailedWarning,
                    stacklevel=2,
                )

            rows.append((row, ranking_value))

        results = build_comparison_table(
            rows           = rows,
            metric_columns = metric_columns,
            any_error      = bool(failures),
        )

        # Order the successful candidates using the same
        # ascending-with-NaN-last, stable ordering as the results table, so
        # the mapping iterates best to worst and its first entry is the
        # winner reported by `best_name` / `best_candidate`.
        ranked_sorted = sorted(ranked, key=compare_sort_key)
        if not ranked_sorted:
            raise AllCandidatesFailedError(failures)
        candidate_results = {name: bt for name, bt, _ in ranked_sorted}

        explanation = build_comparison_explanation(
            n_candidates   = len(candidate_configs),
            ranked         = ranked_sorted,
            ranking_metric = ranking_metric,
            any_error      = bool(failures),
            cv_explanation = cv_explanation,
        )

        return ComparisonResult(
            profile        = profile,
            cv_config      = cv_config,
            results        = results,
            candidates     = candidate_results,
            failures       = failures,
            ranking_metric = ranking_metric,
            explanation    = explanation,
        )

    def ask(
        self,
        prompt: str,
        context: ExplainableResult | None = None,
        *,
        plan: ForecastPlan | None = None,
        skills: list[str] | None = None,
        include_reference: bool = False,
        result: ExplainableResult | None = None,
    ) -> AskResult:
        """
        Ask a forecasting question, optionally about an object to explain.

        Without `context` the LLM answers a general forecasting or
        skforecast question using its skills. With `context`, the object
        renders its own context block (dataset, plan, cross-validation
        strategy, metrics, predictions, or leaderboard, whatever it holds)
        and the LLM explains it. `ask()` never computes anything: profile,
        plan and results are produced by the other methods and handed
        over here.

        Parameters
        ----------
        prompt : str
            Natural-language question or instruction.
        context : ExplainableResult, default None
            Object to explain. Accepts a `ForecastingProfile` (from
            `profile()`), a `CodeGenerationResult` (from `forecast_code()`
            or `backtest_code()`), a `CVResult` (from `create_cv()`), or a
            `ForecastResult`, `BacktestResult` or `ComparisonResult`. The
            returned `profile`, `plan`, and `code` are the context's own;
            for a `ComparisonResult` these are the shared profile and the
            winning candidate's plan and code. The values a result owns
            (its predictions and metrics) are always sent to the LLM,
            regardless of `send_data_to_llm`, since a question about a
            result cannot be answered from summary statistics alone. The
            input data is never sent: a result holds only the model's
            output, and a profile holds summary statistics only.
        plan : ForecastPlan, default None
            Plan to explain together with the profile passed as
            `context`. The two are rendered into the same script
            `forecast_code()` would produce, so the LLM sees the plan and
            the returned `code` is that script. Not accepted with any
            other kind of context, which already carries its own plan.
        skills : list of str, default None
            List of skill names to include in the agent system prompt.
            If None, skills are selected automatically based on the
            task type and question content. See `skforecast_ai.ALL_SKILLS`
            for valid names.
        include_reference : bool, default False
            Whether to include the skforecast API reference in the
            prompt.
        result : ExplainableResult, default None
            Deprecated alias of `context`, removed in 0.4.0. Passing it
            emits a `DeprecationWarning`.

        Returns
        -------
        result : AskResult
            LLM response and the artifacts of the explained context.
            Contains the following attributes:

            - profile: profile of the explained context, when there is
            one.
            - plan: forecasting plan of the explained context, when there
            is one.
            - code: generated Python script of the explained context, when
            there is one.
            - explanation: LLM-generated explanation or response.
            - skills: names of the skill documents sent to the model,
            after trimming to fit the context budget.

        Raises
        ------
        LLMRequiredError
            If no LLM was configured at init time.
        LLMCallError
            If the call to the LLM fails (network, credentials, provider
            error, or a local model that is not reachable). The original
            exception is available as `original_error`. Unlike
            `refine_plan()` and `create_cv()`, `ask()` has no deterministic
            answer to fall back on.
        TypeError
            If `context` is not explainable (a bare `ForecastPlan` is
            not: pass `context=profile, plan=plan`), if `plan` accompanies
            a context other than a `ForecastingProfile`, or if `context`
            and the deprecated `result` are both given.

        Warns
        -----
        DataSentToLLMWarning
            If `context` carries values of its own (predictions, metrics)
            while `send_data_to_llm` is False.
        DeprecationWarning
            If the deprecated `result` alias is used.

        Notes
        -----
        An LLM must be configured at init time. When `llm` is None,
        this method cannot operate and raises `LLMRequiredError`.
        """

        if self.llm is None:
            raise LLMRequiredError("ask")

        if result is not None:
            warnings.warn(
                "`result` is deprecated and will be removed in 0.4.0. Pass "
                "the object to explain as `context` instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            if context is not None:
                raise TypeError(
                    "Pass the object to explain as `context`; `result` is a "
                    "deprecated alias of it and cannot be combined with it."
                )
            context = result

        if isinstance(context, ForecastPlan):
            raise TypeError(
                "A `ForecastPlan` cannot be explained on its own: it does not "
                "carry the dataset it was derived from. Pass "
                "`context=profile, plan=plan`."
            )
        if context is not None and not isinstance(context, ExplainableResult):
            raise TypeError(
                f"`context` must be a `ForecastingProfile` or a workflow "
                f"result (for example `ForecastResult`, `BacktestResult`, "
                f"`ComparisonResult`, `CodeGenerationResult`, or `CVResult`), "
                f"got {type(context).__name__}."
            )
        if plan is not None and not isinstance(context, ForecastingProfile):
            raise TypeError(
                "`plan` only accompanies a `ForecastingProfile` passed as "
                "`context`; any other context already carries its own plan."
            )

        # A profile with a plan is explained through the script the two
        # produce together, exactly as `forecast_code()` would render it.
        if isinstance(context, ForecastingProfile) and plan is not None:
            context = CodeGenerationResult(
                profile = context,
                plan    = plan,
                code    = render_forecast_script(
                              profile=context.data_profile, plan=plan
                          ).full_script,
            )

        # --- Deterministic stage: the context describes itself ---
        if context is None:
            profile        = None
            plan           = None
            generated_code = None
            text           = ""
        else:
            # The values a result owns are always sent, so the LLM can
            # discuss specific numbers. This overrides `send_data_to_llm`,
            # so say so: a user who set it to False for privacy reasons
            # would otherwise ship predicted values without being told.
            # The context itself reports whether it ships any such values.
            llm_context = context.to_llm_context(send_data=True)
            if not self.send_data_to_llm and llm_context.sends_result_values:
                warnings.warn(
                    "`send_data_to_llm=False` does not apply to `context`: the "
                    "predicted values it carries are sent to the LLM, because "
                    "a question about a result cannot be answered from "
                    "summary statistics alone. Your input data is not sent: a "
                    "result holds only the model's output, never the data it "
                    "was fitted on. To keep predictions local, ask without "
                    "`context`.",
                    DataSentToLLMWarning,
                    stacklevel=2,
                )
            profile        = llm_context.profile
            plan           = llm_context.plan
            generated_code = llm_context.code
            text           = llm_context.text

        # --- Pre-flight check for Ollama ---
        if self.llm.startswith("ollama:"):
            try:
                ensure_ollama_reachable(self.base_url)
            except ConnectionError as exc:
                raise LLMCallError(self.llm, exc) from exc

        # --- Build user message with context ---
        # The question is delimited so it cannot be mistaken for part of
        # the deterministic context block that precedes it.
        user_message = (
            f"{text}\n\n<question>\n{prompt}\n</question>"
            if text
            else prompt
        )

        # --- Dynamic skill selection when not explicitly provided ---
        resolved_skills = skills
        if resolved_skills is None:
            task_type = (
                profile.task_type
                if profile is not None
                else None
            )
            # Budget the skills against the space the context block has
            # already taken. Only local models expose a context window
            # known up front; hosted windows are provider specific and
            # generally far larger, so no budget is imposed for them and
            # the full selection is sent.
            token_budget = None
            if self.llm.startswith("ollama:"):
                token_budget = compute_skill_token_budget(
                    max_context_tokens = OLLAMA_MAX_CONTEXT_TOKENS,
                    context_tokens     = estimate_context_tokens(user_message),
                    include_reference  = include_reference,
                )
            resolved_skills = select_skills(
                task_type    = task_type,
                question     = prompt,
                token_budget = token_budget,
            )

        # --- LLM call ---
        from .llm import AskDeps

        agent = self._resolve_agent()
        deps = AskDeps(
            profile           = profile,
            plan              = plan,
            skills            = resolved_skills,
            include_reference = include_reference,
        )

        estimated_tokens = estimate_prompt_tokens(
            resolved_skills, include_reference
        )
        model_settings = build_ollama_settings(
            self.llm, estimated_tokens, user_message
        )

        # Unlike `refine_plan()` and `create_cv()`, which fall back to a
        # valid deterministic output, `ask()` has no answer without the
        # LLM, so a failed call is an error rather than a degraded result.
        try:
            agent_result = run_agent_sync(
                agent,
                user_message,
                deps=deps,
                model_settings=model_settings,
            )
        except Exception as exc:
            raise LLMCallError(self.llm, exc) from exc
        explanation = agent_result.output

        # Strip code blocks when a validated script exists.
        if generated_code is not None:
            explanation = _strip_code_blocks(explanation)

        return AskResult(
            profile     = profile,
            plan        = plan,
            code        = generated_code,
            explanation = explanation,
            skills      = list(resolved_skills),
        )

    # --------------------------------------------------------------- private
    def _prepare_forecast(
        self,
        data: pd.Series | pd.DataFrame | str | Path | None,
        target: str | list[str] | None,
        date_column: str | None,
        series_id_column: str | None,
        steps: int | None,
        exog: pd.DataFrame | None,
        interval: list[float] | None,
        test_size: int | float | str | pd.Timestamp | None,
        forecaster: str | None,
        estimator: str | None,
        estimator_kwargs: dict | None,
        lags: int | list[int] | None,
        window_features: list[dict[str, list[str] | int]] | None,
        profile: ForecastingProfile | None,
        plan: ForecastPlan | None,
        require_exog: bool,
    ) -> tuple[ForecastingProfile, ForecastPlan]:
        """
        Resolve profile and plan for the forecasting workflows.

        Shared preparation logic used by both `forecast_code()` and
        `forecast()`. Warns about plan overrides ignored because a plan
        was supplied, profiles the data when no profile is given,
        validates the evaluation or prediction mode, builds the plan when
        none is given, and stamps the `end_train` split boundary derived
        from `test_size` onto the plan.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path, None
            Input passed to `profile()` when `profile` is None. Handed over
            as received: a CSV path is recorded in the profile so the
            generated script loads it from that path.
        target : str, list of str, None
            Name of the column(s) to forecast.
        date_column : str, None
            Name of the column containing timestamps.
        series_id_column : str, None
            Name of the column identifying individual series.
        steps : int, None
            Forecast horizon. Required when `plan` is None; otherwise it
            defaults to `plan.steps` and must match it if given.
        exog : pandas DataFrame, None
            Future exogenous variables (prediction mode only).
        interval : list of float, None
            Prediction interval quantiles.
        test_size : int, float, str, pandas Timestamp, None
            Size or start of the test set. When set, the workflow runs in
            evaluation mode.
        forecaster : str, None
            Explicit forecaster class name override.
        estimator : str, None
            Explicit estimator class name override.
        estimator_kwargs : dict, None
            Keyword arguments for the estimator constructor.
        lags : int, list of int, None
            Explicit lag configuration.
        window_features : list of dict, None
            Explicit window features configuration.
        profile : ForecastingProfile, None
            Pre-computed profile.
        plan : ForecastPlan, None
            Pre-computed plan.
        require_exog : bool
            Whether prediction mode must be given `exog` when the data has
            exogenous columns. True when the workflow executes the script,
            False when it only renders it.

        Returns
        -------
        profile : ForecastingProfile
            Resolved profile.
        plan : ForecastPlan
            Resolved plan, carrying `end_train` when `test_size` is set.
        """

        _warn_if_plan_overrides_ignored(
            plan             = plan,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            interval         = interval,
            lags             = lags,
            window_features  = window_features,
        )

        if profile is None:
            profile = self.profile(
                data             = data,
                target           = target,
                date_column      = date_column,
                series_id_column = series_id_column,
            )

        # A supplied plan fixes the horizon: the script predicts
        # `plan.steps`, so a different `steps` would be silently ignored.
        # Mirror `_prepare_backtest`, which rejects `cv.steps != plan.steps`.
        if plan is not None:
            if steps is not None and steps != plan.steps:
                raise ValueError(
                    f"`steps` ({steps}) does not match `plan.steps` "
                    f"({plan.steps}). Omit `steps` to use the plan's horizon, "
                    f"or refine the plan with `refine_plan(steps=...)`."
                )
            steps = plan.steps
        elif steps is None:
            raise ValueError("`steps` is required when `plan` is not provided.")

        has_exog = bool(profile.data_profile.exog_columns)
        # Evaluation mode is driven by `test_size`, or by a pre-built plan
        # that already carries an `end_train` split boundary. Everything
        # else is prediction mode (forecast the future).
        evaluate = test_size is not None or (
            plan is not None and plan.end_train is not None
        )
        _validate_forecast_mode(
            evaluate     = evaluate,
            exog         = exog,
            has_exog     = has_exog,
            steps        = steps,
            require_exog = require_exog,
        )

        if plan is None:
            plan = self.plan(
                profile          = profile,
                steps            = steps,
                forecaster       = forecaster,
                estimator        = estimator,
                estimator_kwargs = estimator_kwargs,
                interval         = interval,
                lags             = lags,
                window_features  = window_features,
            )

        # `test_size` is a forecast-only concept, so the split boundary is
        # resolved here rather than in the shared `plan()` method. It is
        # stamped onto the plan whether it was freshly built or supplied.
        if test_size is not None:
            end_train = resolve_end_train(
                start_date     = profile.data_profile.start_date,
                frequency      = profile.data_profile.frequency,
                n_observations = profile.data_profile.span_index_length,
                test_size      = test_size,
            )
            plan = plan.model_copy(update={"end_train": end_train})

        return profile, plan

    def _prepare_backtest(
        self,
        data: pd.Series | pd.DataFrame | str | Path,
        cv: TimeSeriesFold,
        target: str | list[str] | None,
        date_column: str | None,
        series_id_column: str | None,
        interval: list[float] | None,
        forecaster: str | None,
        estimator: str | None,
        estimator_kwargs: dict | None,
        profile: ForecastingProfile | None,
        plan: ForecastPlan | None,
    ) -> tuple[ForecastingProfile, ForecastPlan]:
        """
        Resolve profile and plan for backtesting workflows.

        Shared preparation logic used by both `backtest_code()` and
        `backtest()`. Coerces data, auto-generates profile/plan when
        not provided, and validates that `cv.steps` matches `plan.steps`
        when a plan is explicitly passed.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path
            Input dataset, a single series, or path to a CSV file.
        cv : TimeSeriesFold
            Cross-validation fold splitter.
        target : str, list of str, None
            Name of the column(s) to forecast. Optional only when `data`
            is a pandas Series (the Series name is used instead).
        date_column : str, None
            Name of the column containing timestamps.
        series_id_column : str, None
            Name of the column identifying individual series.
        interval : list of float, None
            Prediction interval quantiles.
        forecaster : str, None
            Explicit forecaster class name override.
        estimator : str, None
            Explicit estimator class name override.
        estimator_kwargs : dict, None
            Keyword arguments for the estimator constructor.
        profile : ForecastingProfile, None
            Pre-computed profile.
        plan : ForecastPlan, None
            Pre-computed plan.

        Returns
        -------
        profile : ForecastingProfile
            Resolved profile.
        plan : ForecastPlan
            Resolved plan.
        """

        _warn_if_plan_overrides_ignored(
            plan             = plan,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            interval         = interval,
        )

        data_df, target, date_column, series_id_column = (
            _resolve_inputs_with_profile(
                data, target, date_column, series_id_column, profile
            )
        )
        steps = cv.steps

        if profile is None:
            # Profile the input as received: a CSV path is recorded in the
            # profile so the generated script loads it from that path, as
            # `forecast_code()` does.
            profile = self.profile(
                data             = data,
                target           = target,
                date_column      = date_column,
                series_id_column = series_id_column,
            )

        if plan is None:
            plan = self.plan(
                profile          = profile,
                steps            = steps,
                forecaster       = forecaster,
                estimator        = estimator,
                estimator_kwargs = estimator_kwargs,
                interval         = interval,
            )
        else:
            if cv.steps != plan.steps:
                raise ValueError(
                    f"cv.steps ({cv.steps}) does not match plan.steps "
                    f"({plan.steps}). These must be equal: "
                    f"ForecasterDirect and ForecasterDirectMultiVariate "
                    f"model architectures depend on steps."
                )

        return profile, plan

    def _resolve_model(self):
        """
        Resolve the LLM model from the provider string.

        The model is created on the first call and cached for
        subsequent invocations.

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
        Create and cache the pydantic-ai Agent instance.

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

    def _resolve_cv_agent(self):
        """
        Create and cache the CV configuration agent.

        Returns
        -------
        agent : Agent[CVDeps, CVParams]
            Cached CV configuration agent instance.
        """
        if self._cv_agent is None:
            from .llm.agent import create_cv_agent

            model = self._resolve_model()
            self._cv_agent = create_cv_agent(model)

        return self._cv_agent

    def _resolve_plan_refinement_agent(self):
        """
        Create and cache the plan refinement agent.

        Returns
        -------
        agent : Agent[PlanRefinementDeps, PlanOverrides]
            Cached plan refinement agent instance.
        """
        if self._plan_refinement_agent is None:
            from .llm.agent import create_plan_refinement_agent

            model = self._resolve_model()
            self._plan_refinement_agent = create_plan_refinement_agent(model)

        return self._plan_refinement_agent
