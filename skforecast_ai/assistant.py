################################################################################
#                          ForecastingAssistant                                #
#                                                                              #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import warnings
from pathlib import Path
import pandas as pd
from skforecast.model_selection import TimeSeriesFold
from skforecast.exceptions import IgnoredArgumentWarning
from .exceptions import LLMRequiredError
from .execution import run_backtest, run_forecast
from .execution.backtesting_runner import render_backtesting_script
from .execution.forecast_runner import render_forecast_script
from .llm import (
    build_context_message,
    create_model,
    ensure_ollama_reachable,
    estimate_prompt_tokens,
    select_skills,
)
from .profiling import create_data_profile
from .recommendation import (
    _build_profile_explanation,
    build_cv_explanation,
    build_plan_explanation,
    build_forecaster_kwargs,
    check_exog_usage,
    compute_series_pacf,
    derive_cv_defaults,
    derive_preprocessing_steps,
    finalize_lags,
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
    AskResult,
    BacktestResult,
    CodeGenerationResult,
    ForecastingProfile,
    ForecastPlan,
    ForecastResult,
)
from ._utils import (
    _resolve_data_and_target,
    _run_agent_sync,
    _strip_code_blocks,
    _validate_task_input,
)


class ForecastingAssistant:
    """
    AI-powered forecasting assistant built on skforecast.

    Analyses a time series dataset, selects a forecaster and estimator,
    produces a ready-to-run Python script, and optionally executes it —
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

    Notes
    -----
    Three workflows are available:

    Fast path — call a single method that handles everything internally:

    - `forecast_code()` profiles the data, builds a plan, and returns a
    ready-to-run Python script.
    - `forecast()` does the same and also executes the forecast,
    returning predictions and metrics.

    Step-by-step path — for full control over each stage:

    - `profile()` inspects the dataset and selects the recommended
    forecaster and estimator (with alternative candidates).
    - `plan()` takes the profile and derives the detailed configuration
    (lags, metric, preprocessing, intervals, NaN handling).
    - `refine_plan()` adjusts an existing plan with user overrides (if desired).
    - `forecast_code()` generates a Python script (accepts pre-computed
    `profile` and `plan` for full control).
    - `forecast()` executes the workflow from a pre-computed profile and
    plan, returning predictions and metrics.

    Backtesting path — evaluate model performance with time series
    cross-validation:

    - `create_cv()` produces a `TimeSeriesFold` with smart defaults
    (optionally guided by an LLM prompt). Requires a profile and plan.
    - `backtest_code()` generates a backtesting script without executing
    it (accepts pre-computed `profile` and `plan`).
    - `backtest()` runs backtesting using the CV strategy and returns
    metrics, predictions, and reproducible code.

    `ask()` is an LLM-powered method available in any workflow to
    explain results, answer forecasting questions, or interpret metrics.

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
                              series_pacf    = series_pacf,
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
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[float] | None = None,
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
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` (e.g. `[0.1, 0.9]` for 80 % interval). If
            None, no prediction intervals are computed.

        Returns
        -------
        plan : ForecastPlan
            Detailed forecasting plan.
        """

        data_profile = profile.data_profile

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
            lags = None
            window_features = None
            transformer_series = None
            transformer_exog = None
            dropna_from_series = None
            calendar_features = None
        else:
            lags = finalize_lags(
                series_pacf     = profile.series_pacf,
                task_type       = task_type,
                n_observations  = data_profile.span_index_length,
                frequency       = data_profile.frequency,
            )
            window_features = profile.window_features

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
            lags               = lags,
            window_features    = window_features,
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
            lags               = lags,
            window_features    = window_features,
            interval_method    = interval_method,
            dropna_from_series = dropna_from_series,
            use_exog           = use_exog,
            metric_explanation = metric_explanation,
            calendar_features  = calendar_features,
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
        `plan()` with the merged parameters. Only the
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

        return self.plan(
            profile          = profile,
            steps            = steps,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            interval         = interval,
        )

    def forecast_code(
        self,
        data: pd.Series | pd.DataFrame | str | Path | None = None,
        steps: int | None = None,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[float] | None = None,
        profile: ForecastingProfile | None = None,
        plan: ForecastPlan | None = None,
    ) -> CodeGenerationResult:
        """
        Profile, plan, and generate a complete forecasting script.

        Convenience wrapper that chains `profile()`, `plan()`,
        and code generation in a single call. Pre-computed `profile`
        and/or `plan` can be passed to skip those stages (e.g. after
        modifying the plan with `refine_plan()`).

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path, default None
            Input dataset, a single series, or path to a CSV file. Required
            when `profile` is not provided. When a pandas Series is passed,
            the target is derived from its name.
        steps : int, default None
            Forecast horizon (number of steps ahead to predict).
            Required when `plan` is not provided.
        target : str, list of str, default None
            Name of the column to forecast. Required when `profile`
            is not provided, unless `data` is a pandas Series (the Series
            name is used instead).
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
            `{'n_estimators': 200}`). See `plan()`.
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` (e.g. `[0.1, 0.9]` for 80 % interval). If
            None, no prediction intervals are computed.
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
            Forecasting profile, plan, and generated code.
        """

        if profile is None:
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
        steps: int,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[float] | None = None,
        exog_future: pd.DataFrame | None = None,
        profile: ForecastingProfile | None = None,
        plan: ForecastPlan | None = None,
    ) -> ForecastResult:
        """
        Execute a full forecasting workflow end-to-end.

        Convenience wrapper that chains `profile()`, `plan()`,
        validation and programmatic execution.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path
            Input dataset, a single series, or path to a CSV file. When a
            pandas Series is passed, the target is derived from its name.
        steps : int
            Forecast horizon (number of steps ahead to predict).
        target : str, list of str, default None
            Name of the column to forecast. Optional only when `data` is a
            pandas Series (the Series name is used instead).
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
            `{'n_estimators': 200}`). See `plan()`.
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` (e.g. `[0.1, 0.9]` for 80 % interval). If
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
        This method executes the same code that `forecast_code()`
        produces, ensuring perfect fidelity between the inspectable
        script (`ForecastResult.code`) and the actual execution.
        """

        data_df, target = _resolve_data_and_target(data, target)

        if profile is None:
            profile = self.profile(
                data             = data_df,
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

        result = run_forecast(
            data        = data_df,
            profile     = profile.data_profile,
            plan        = plan,
            exog_future = exog_future,
        )

        return ForecastResult(
            profile     = profile,
            plan        = plan,
            code        = result["rendered_code"].full_script,
            metrics     = result["metrics"],
            predictions = result["predictions"],
            intervals   = result["intervals"],
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
    ) -> tuple[TimeSeriesFold, str]:
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
        cv : TimeSeriesFold
            Configured cross-validation fold splitter.
        explanation : str
            Human-readable explanation of the chosen configuration.

        References
        ----------
        [1] Skforecast `TimeSeriesFold` API Reference:
            https://skforecast.org/latest/api/model_selection#skforecast.model_selection._split.TimeSeriesFold
        
        """

        span_index_length = profile.data_profile.span_index_length

        # -----------------------------------------------------------------
        # LLM path: when prompt is provided, use LLM for CV configuration
        # -----------------------------------------------------------------
        if prompt is not None:
            if self.llm is None:
                raise LLMRequiredError("create_cv")

            defaults = self._configure_cv_with_llm(
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
        skip_validation = False
        if isinstance(its, float):
            if not (0 < its < 1):
                raise ValueError(
                    f"initial_train_size as float must satisfy "
                    f"0 < value < 1, got {its}."
                )
            defaults["initial_train_size"] = int(its * span_index_length)
        elif isinstance(its, str):
            skip_validation = True

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

        # Validate fold count (unless initial_train_size is a date string)
        if not skip_validation:
            # `window_size` is unset here (no forecaster attached yet), so
            # skforecast emits an IgnoredArgumentWarning about the last
            # window. It is irrelevant for the fold-count check below.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=IgnoredArgumentWarning)
                folds = cv.split(
                    X=pd.RangeIndex(span_index_length), as_pandas=False
                )
            n_folds = len(folds)
            if n_folds < 2:
                raise ValueError(
                    f"The resolved CV configuration produces only "
                    f"{n_folds} fold(s). At least 2 are required. "
                    f"Resolved parameters: {defaults}."
                )
        else:
            n_folds = None

        # Build explanation
        reasoning = defaults.pop("_reasoning", None)
        explanation = build_cv_explanation(
                          cv_params      = defaults,
                          n_observations = span_index_length,
                          n_folds        = n_folds if n_folds is not None else 0,
                      )
        if reasoning:
            explanation = f"{reasoning} {explanation}"

        return cv, explanation

    def backtest_code(
        self,
        data: pd.Series | pd.DataFrame | str | Path,
        cv: TimeSeriesFold,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[float] | None = None,
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
        cv : TimeSeriesFold
            Time series cross-validation fold splitter (output of
            `create_cv()` or user-constructed) [1]_.
        target : str, list of str, default None
            Name of the column(s) to forecast. Optional only when `data`
            is a pandas Series (the Series name is used instead).
        date_column : str, default None
            Name of the column containing timestamps.
        series_id_column : str, default None
            Name of the column identifying individual series.
        forecaster : str, default None
            Explicit forecaster class name. See `profile()`.
        estimator : str, default None
            Explicit estimator class name. See `profile()`.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor.
        interval : list of float, default None
            Prediction interval quantiles as `[lower, upper]`.
        profile : ForecastingProfile, default None
            Pre-computed profile to skip profiling.
        plan : ForecastPlan, default None
            Pre-computed plan to skip planning.

        Returns
        -------
        result : CodeGenerationResult
            Forecasting profile, plan, and generated backtesting code.

        References
        ----------
        [1] Skforecast `TimeSeriesFold` API Reference:
            https://skforecast.org/latest/api/model_selection#skforecast.model_selection._split.TimeSeriesFold

        """

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
        cv: TimeSeriesFold,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        forecaster: str | None = None,
        estimator: str | None = None,
        estimator_kwargs: dict | None = None,
        interval: list[float] | None = None,
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
        cv : TimeSeriesFold
            Time series cross-validation fold splitter (output of `create_cv()`
            or user-constructed) [1]_.
        target : str, list of str, default None
            Name of the column(s) to forecast. Optional only when `data`
            is a pandas Series (the Series name is used instead).
        date_column : str, default None
            Name of the column containing timestamps.
        series_id_column : str, default None
            Name of the column identifying individual series.
        forecaster : str, default None
            Explicit forecaster class name. See `profile()`.
        estimator : str, default None
            Explicit estimator class name. See `profile()`.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor.
        interval : list of float, default None
            Prediction interval quantiles as `[lower, upper]`.
        profile : ForecastingProfile, default None
            Pre-computed profile to skip profiling.
        plan : ForecastPlan, default None
            Pre-computed plan to skip planning.
        show_progress : bool, default True
            Whether to display a progress bar during backtesting.

        Returns
        -------
        result : BacktestResult
            Backtesting profile, plan, metrics, predictions, code, and
            explanation.

        Notes
        -----
        The `data` DataFrame must include exogenous columns if the plan
        uses them. Exogenous variables are extracted automatically from
        `profile.data_profile.exog_columns`.

        References
        ----------
        [1] Skforecast `TimeSeriesFold` API Reference:
            https://skforecast.org/latest/api/model_selection#skforecast.model_selection._split.TimeSeriesFold
        
        """

        data_df, target = _resolve_data_and_target(data, target)

        profile, plan = self._prepare_backtest(
            data             = data_df,
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

        # Build human-readable CV explanation
        span_index_length = profile.data_profile.span_index_length
        # `window_size` is unset here (no forecaster attached yet), so
        # skforecast emits an IgnoredArgumentWarning about the last
        # window. It is irrelevant for building the explanation below.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=IgnoredArgumentWarning)
            if isinstance(cv.initial_train_size, str):
                # Date-based initial_train_size requires a DatetimeIndex.
                index = pd.date_range(
                            start   = profile.data_profile.start_date,
                            periods = span_index_length,
                            freq    = profile.data_profile.frequency,
                        )
                folds = cv.split(X=index, as_pandas=False)
            else:
                folds = cv.split(
                    X=pd.RangeIndex(span_index_length), as_pandas=False
                )

        # Extract cv_config after split
        cv_config = {
            "steps": cv.steps,
            "initial_train_size": cv.initial_train_size,
            "refit": cv.refit,
            "fixed_train_size": cv.fixed_train_size,
            "gap": cv.gap,
            "fold_stride": cv.fold_stride,
            "differentiation": cv.differentiation,
        }
        cv_explanation = build_cv_explanation(
                             cv_params      = cv_config,
                             n_observations = span_index_length,
                             n_folds        = len(folds),
                         )

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

    def ask(
        self,
        prompt: str,
        data: pd.Series | pd.DataFrame | str | Path | None = None,
        target: str | list[str] | None = None,
        date_column: str | None = None,
        series_id_column: str | None = None,
        profile: ForecastingProfile | None = None,
        plan: ForecastPlan | None = None,
        forecast_result: ForecastResult | None = None,
        backtest_result: BacktestResult | None = None,
        steps: int | None = None,
        skills: list[str] | None = None,
        include_reference: bool = False,
    ) -> AskResult:
        """
        Ask a forecasting question or explain a pre-computed plan.

        Operates in four modes:

        - Q&A mode (no data, no profile, no forecast_result, no
          backtest_result): the LLM answers general forecasting or
          skforecast questions using its skills.
        - Explain mode (data or profile provided): deterministic
          profiling runs first, then the LLM explains the result.
        - Results mode (forecast_result provided): the LLM explains
          forecast predictions, metrics, and intervals from a
          completed `forecast()` run.
        - Backtest mode (backtest_result provided): the LLM explains
          backtesting metrics, predictions, and CV configuration from a
          completed `backtest()` run.

        Parameters
        ----------
        prompt : str
            Natural-language question or instruction.
        data : pandas Series, pandas DataFrame, str, Path, default None
            Optional dataset, a single series, or path to a CSV file. When
            provided (without a pre-computed profile), triggers
            deterministic profiling + plan generation before the LLM call.
            When a pandas Series is passed, the target is derived from its
            name.
        target : str, list of str, default None
            Name of the target column(s). Required when `data` is
            provided and `profile` is None, unless `data` is a pandas
            Series (the Series name is used instead).
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
        backtest_result : BacktestResult, default None
            Result from a previous `backtest()` call. When provided,
            the LLM receives backtesting metrics, predictions, and
            CV configuration in context. Mutually exclusive with
            `forecast_result`.
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
        An LLM must be configured at init time. When `llm` is None,
        this method cannot operate and raises `LLMRequiredError`.
        """

        if self.llm is None:
            raise LLMRequiredError("ask")

        if forecast_result is not None and backtest_result is not None:
            raise ValueError(
                "`forecast_result` and `backtest_result` are mutually "
                "exclusive — provide one or the other, not both."
            )

        # --- Extract from forecast_result if provided ---
        predictions = None
        metrics = None
        intervals = None
        cv_config = None
        if forecast_result is not None:
            profile = profile or forecast_result.profile
            plan = plan or forecast_result.plan
            predictions = forecast_result.predictions
            metrics = forecast_result.metrics
            intervals = forecast_result.intervals
        elif backtest_result is not None:
            profile = profile or backtest_result.profile
            plan = plan or backtest_result.plan
            predictions = backtest_result.predictions
            metrics = backtest_result.metrics
            cv_config = backtest_result.cv_config

        # --- Deterministic stage: compute profile/plan if needed ---
        if data is not None and profile is None:
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
            plan = self.plan(profile, steps=steps)

        # --- Generate deterministic code from plan ---
        if forecast_result is not None:
            generated_code = forecast_result.code
        elif backtest_result is not None:
            generated_code = backtest_result.code
        elif plan is not None and profile is not None:
            generated_code = render_forecast_script(
                profile=profile.data_profile, plan=plan
            ).full_script
        else:
            generated_code = None

        # --- Pre-flight check for Ollama ---
        if self.llm is not None and self.llm.startswith("ollama:"):
            ensure_ollama_reachable(self.base_url)

        # --- Build user message with context ---
        # In results mode, always send prediction data so the LLM can
        # discuss specific values. Otherwise respect the user setting.
        send_data = (
            True
            if forecast_result is not None or backtest_result is not None
            else self.send_data_to_llm
        )
        context = build_context_message(
            profile, plan,
            predictions=predictions,
            metrics=metrics,
            intervals=intervals,
            cv_config=cv_config,
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

        try:
            result = _run_agent_sync(
                agent,
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
    def _prepare_backtest(
        self,
        data: pd.Series | pd.DataFrame | str | Path,
        cv: TimeSeriesFold,
        target: str | list[str] | None,
        date_column: str | None,
        series_id_column: str | None,
        forecaster: str | None,
        estimator: str | None,
        estimator_kwargs: dict | None,
        interval: list[float] | None,
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
        forecaster : str, None
            Explicit forecaster class name override.
        estimator : str, None
            Explicit estimator class name override.
        estimator_kwargs : dict, None
            Keyword arguments for the estimator constructor.
        interval : list of float, None
            Prediction interval quantiles.
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

        data_df, target = _resolve_data_and_target(data, target)
        steps = cv.steps

        if profile is None:
            profile = self.profile(
                data             = data_df,
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
                    f"({plan.steps}). These must be equal — "
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

    def _configure_cv_with_llm(
        self,
        profile: ForecastingProfile,
        plan: ForecastPlan,
        prompt: str,
        n_observations: int,
    ) -> dict:
        """
        Use the LLM to derive CV parameters from a natural-language prompt.

        Retries up to 2 times on validation failure, then falls back to
        deterministic defaults with a warning.

        Parameters
        ----------
        profile : ForecastingProfile
            Profiled dataset.
        plan : ForecastPlan
            Forecast plan.
        prompt : str
            User's deployment scenario description.
        n_observations : int
            Total number of observations.

        Returns
        -------
        defaults : dict
            Resolved CV parameters dict (same format as
            `derive_cv_defaults`).
        """
        from .llm.agent import CVDeps

        agent = self._resolve_cv_agent()
        lags = plan.forecaster_kwargs.get("lags")

        deps = CVDeps(
                   n_observations = n_observations,
                   frequency      = profile.data_profile.frequency,
                   steps          = plan.steps,
                   task_type      = plan.task_type,
                   lags           = lags,
               )

        max_retries = 2
        last_error = None

        for attempt in range(1 + max_retries):
            try:
                if attempt == 0:
                    user_message = prompt
                else:
                    user_message = (
                        f"{prompt}\n\n"
                        f"[RETRY {attempt}/{max_retries}] Your previous "
                        f"configuration failed validation: {last_error}. "
                        f"The dataset has {n_observations} observations "
                        f"and steps={plan.steps}. Fix the parameters."
                    )

                result = _run_agent_sync(agent, user_message, deps=deps)
                cv_params = result.output

                # Convert CVParams to defaults dict
                defaults = {
                    "steps": plan.steps,
                    "initial_train_size": cv_params.initial_train_size,
                    "refit": cv_params.refit,
                    "fixed_train_size": cv_params.fixed_train_size,
                    "gap": cv_params.gap,
                    "fold_stride": cv_params.fold_stride,
                    "skip_folds": cv_params.skip_folds,
                    "allow_incomplete_fold": cv_params.allow_incomplete_fold,
                    "differentiation": plan.forecaster_kwargs.get(
                        "differentiation"
                    ),
                    "_reasoning": cv_params.reasoning,
                }

                # Validate: check that we can produce ≥2 folds
                self._validate_cv_defaults(defaults, n_observations)

                return defaults

            except Exception as exc:
                last_error = str(exc)
                if attempt < max_retries:
                    continue
                # All retries exhausted — fall back to deterministic
                warnings.warn(
                    f"LLM CV configuration failed after "
                    f"{1 + max_retries} attempts "
                    f"(last error: {last_error}). "
                    f"Falling back to deterministic defaults.",
                    UserWarning,
                    stacklevel=3,
                )
                defaults = derive_cv_defaults(profile=profile, plan=plan)
                return defaults

        # Should never reach here, but satisfy type checker
        return derive_cv_defaults(profile=profile, plan=plan)  # pragma: no cover

    @staticmethod
    def _validate_cv_defaults(defaults: dict, n_observations: int) -> None:
        """
        Validate that CV defaults can produce at least 2 folds.

        A `ValueError` is raised when the configuration cannot produce
        at least 2 folds.

        Parameters
        ----------
        defaults : dict
            Resolved CV parameters dict with keys `'steps'`,
            `'initial_train_size'`, `'refit'`, `'fixed_train_size'`,
            `'gap'`, `'fold_stride'`, `'skip_folds'`,
            `'allow_incomplete_fold'`, and `'differentiation'`.
        n_observations : int
            Total number of observations in the dataset.

        Returns
        -------
        None
        """

        its = defaults["initial_train_size"]
        if isinstance(its, str):
            # Cannot validate date-based initial_train_size without data
            return

        if isinstance(its, float):
            if not (0 < its < 1):
                raise ValueError(
                    f"initial_train_size as float must be in (0, 1), got {its}."
                )
            its = int(its * n_observations)
            defaults["initial_train_size"] = its

        cv = TimeSeriesFold(
            steps=defaults["steps"],
            initial_train_size=its,
            refit=defaults["refit"],
            fixed_train_size=defaults["fixed_train_size"],
            gap=defaults["gap"],
            fold_stride=defaults.get("fold_stride"),
            skip_folds=defaults.get("skip_folds"),
            allow_incomplete_fold=defaults.get("allow_incomplete_fold", True),
            differentiation=defaults.get("differentiation"),
            verbose=False,
        )
        
        # `window_size` is unset here (no forecaster attached yet), so
        # skforecast emits an IgnoredArgumentWarning about the last
        # window. It is irrelevant for the fold-count check below.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=IgnoredArgumentWarning)
            folds = cv.split(X=pd.RangeIndex(n_observations), as_pandas=False)
        
        if len(folds) < 2:
            raise ValueError(
                f"Configuration produces only {len(folds)} fold(s). "
                f"At least 2 required. Parameters: {defaults}."
            )

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
