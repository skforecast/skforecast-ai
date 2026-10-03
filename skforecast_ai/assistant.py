################################################################################
#                          ForecastingAssistant                                #
#                                                                              #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import json
import sys
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any
import pandas as pd

if sys.version_info >= (3, 12):
    from typing import Unpack
else:
    from typing_extensions import Unpack
from skforecast.exceptions import IgnoredArgumentWarning, LongTrainingWarning
from skforecast.model_selection import TimeSeriesFold
from ._constants import (
    AUTOREG_FORECASTERS,
    BASELINE_FORECASTERS,
    DIRECT_FORECASTERS,
    FORECASTER_TASK_TYPES,
    OLLAMA_MAX_CONTEXT_TOKENS,
    REQUIRES_DATETIME_FREQ,
)
from ._validation import (
    check_estimator_installed,
    validate_estimator,
    validate_estimator_kwargs,
    validate_interval,
    validate_metrics,
    validate_steps,
)
from .exceptions import (
    AllCandidatesFailedError,
    CandidateFailedWarning,
    DataSentToLLMWarning,
    InvalidInputError,
    InvalidInputTypeError,
    LLMCallError,
    LLMRequiredError,
    MissingBackendWarning,
    UnrecommendedForecasterWarning,
)
from .execution import run_backtest, run_forecast
from .execution.backtesting_runner import render_backtesting_script
from .execution.comparison import (
    add_baseline_candidate,
    aggregate_metrics,
    build_comparison_explanation,
    build_comparison_table,
    compare_sort_key,
    exclude_costly_candidates,
    missing_foundation_backend,
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
from .llm.diagnostics import check_llm_config
from .llm.refinement import configure_cv_with_llm, refine_features_with_llm
from .llm.runtime import run_agent_sync
from .profiling import (
    count_test_observations,
    create_data_profile,
    resolve_end_train,
)
from .profiling.data_profile import validate_target_numeric
from .recommendation import (
    _build_profile_explanation,
    baseline_missing_values_note,
    build_cv,
    build_foundation_explanation,
    build_plan_explanation,
    build_forecaster_kwargs,
    check_exog_usage,
    compute_series_pacf,
    count_estimator_fits,
    cv_as_executed,
    derive_cv_defaults,
    derive_preprocessing_steps,
    drop_colliding_calendar_features,
    finalize_lags,
    resolve_cv_config,
    select_baseline_config,
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
    CompareProgress,
    ComparisonResult,
    CVResult,
    DataProfile,
    ExplainableResult,
    ForecastingProfile,
    ForecastPlan,
    ForecastResult,
    LLMCheckResult,
    RefinePlanOverrides,
)
from ._foundation import foundation_exog_columns, validate_foundation_plan
from ._future_exog import as_exog_frame, validate_future_exog
from ._last_window import (
    validate_evaluation_partition,
    validate_infinite_target,
    validate_last_window,
    validate_series_lengths,
)
from ._utils import (
    _check_cv_matches_profile,
    _check_evaluated_target,
    _check_plan_matches_profile,
    _check_feature_name_collisions,
    _warn_window_without_refit,
    _resolve_data_and_target,
    _resolve_inputs_with_profile,
    _strip_code_blocks,
    _unwrap_cv,
    _with_data_path,
    _validate_forecast_mode,
    resolve_interval_method,
    _validate_lags,
    _validate_max_window_size,
    _validate_task_input,
    _validate_window_features,
    _apply_interval_to_plan,
    _check_plan_overrides,
    _data_path_of_run,
    _revalidate_plan,
    recorded_data_path,
    structure_differences,
    warn_long_training,
)


def _check_frequency_known(forecaster: str, data_profile: DataProfile) -> None:
    """
    Reject a datetime index without a frequency for a forecaster that needs
    one.

    Without a frequency the datetime index cannot be regularized, and every
    forecaster that needs one fails inside the script with a skforecast
    error that does not say why. Irregular timestamps are often day-first
    dates that pandas read month-first.
    """
    if data_profile.index_type == "datetime" and data_profile.frequency is None:
        raise InvalidInputError(
            f"The frequency of the datetime index could not be inferred "
            f"(the timestamps are irregular or too few), and '{forecaster}' "
            f"needs a regular DatetimeIndex. Check the dates: day-first "
            f"values such as '13/02/2023' are read month-first unless parsed "
            f"explicitly, for example with "
            f"pandas.to_datetime(..., dayfirst=True).",
            field = "profile",
            hint  = (
                "Write the dates in ISO 8601 (such as '2023-02-13'), so they "
                "are not read month-first."
            ),
        )


def _profile_values(data_profile: DataProfile) -> dict[str, str]:
    """
    Return the fields of a data profile that describe the values of the
    data, each as text, to tell whether two profiles describe the same data.

    `data_path` and `warnings` are left out: the path is set by the caller,
    and the warnings derive from the values (and hold the note of an earlier
    refresh). The column lists are sorted, as `structure_differences` reads
    them, and NaN statistics (the standard deviation of a target with an
    infinite value) compare equal through their text.

    Parameters
    ----------
    data_profile : DataProfile
        Data profile to read.

    Returns
    -------
    values : dict
        Text of each field, by field name.
    """

    values = data_profile.model_dump(exclude={"data_path", "warnings"})
    for name in ("exog_columns", "categorical_exog"):
        values[name] = sorted(values[name])
    if isinstance(values["target"], list):
        values["target"] = sorted(values["target"])

    return {
        name: json.dumps(value, sort_keys=True, default=str)
        for name, value in values.items()
    }


class ForecastingAssistant:
    """
    Time series forecasting assistant built on skforecast.

    Analyses a time series dataset, selects a forecaster and estimator,
    produces a ready-to-run Python script, and optionally executes it,
    returning predictions, metrics, and the exact code that generated them.

    All modeling decisions are deterministic and reproducible. An optional
    LLM explains them and answers questions. On request, it also proposes
    lags and window features (`refine_plan()`) or a cross-validation
    strategy (`create_cv()`), which are validated before they are used.

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
        Acknowledges that the values a result owns (its predictions and
        metrics) are sent to the LLM when the result is passed to
        `ask()` as `context`. When False, `ask()` still sends them but
        emits `DataSentToLLMWarning`; when True the warning is silenced.
        The input data is never sent in either mode: profiles carry
        summary statistics only, and a result holds the model's output,
        not the data it was fitted on.

    Attributes
    ----------
    llm : str, None
        LLM provider string or None for deterministic-only mode.
    base_url : str, None
        Custom base URL for the LLM provider.
    api_key : str, None
        Explicit API key or None (resolve from environment).
    send_data_to_llm : bool
        Whether sending result values to the LLM has been acknowledged.

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

    `check_llm()` reports how the LLM configuration resolves (provider,
    credentials, endpoint, installed extras) before any workflow runs.

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

        data_path = recorded_data_path(data)
        data, target = _resolve_data_and_target(data, target, date_column)

        data_profile = create_data_profile(
            data             = data,
            target           = target,
            date_column      = date_column,
            series_id_column = series_id_column,
            data_path        = data_path,
        )
        validate_target_numeric(data, data_profile.target)

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
            Forecast horizon (number of steps ahead to predict): an integer
            greater than or equal to 1. An integral float (`12.0`) is
            accepted and stored as an int.
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
            `'ForecasterEquivalentDate'` builds a seasonal naive baseline
            (single series only) without that warning: it is a reference
            to compare against, not a recommendation. Its offset is
            chosen from the frequency, and it takes no `estimator`,
            `estimator_kwargs`, `lags` or `window_features`.
        estimator : str, default None
            Explicit estimator class name to override the profile
            recommendation (e.g. `'HistGradientBoostingRegressor'`). For
            `ForecasterFoundation` it is the Hugging Face model ID of a
            foundation model supported by skforecast (e.g.
            `'google/timesfm-3.0-pytorch'`); the default is
            `'autogluon/chronos-2-small'`.
        estimator_kwargs : dict, default None
            Keyword arguments for the estimator constructor (e.g.
            `{'n_estimators': 200, 'learning_rate': 0.05}`). Merged
            on top of built-in defaults (`random_state`, silencing
            flags). User values take precedence. For
            `ForecasterFoundation` they are passed to `FoundationModel`
            (e.g. `{'context_length': 1024}`), and the model ID goes in
            `estimator`, not here.
        lags : int, list of int, default None
            Explicit lag configuration. If provided, bypasses the
            deterministic PACF-based lag selection. Only the ML forecasters
            take lags: passing them for `ForecasterStats`,
            `ForecasterFoundation` or `ForecasterEquivalentDate` raises
            `ValueError`.
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
            Like `lags`, raises `ValueError` for a forecaster without
            window features.

        Returns
        -------
        plan : ForecastPlan
            Detailed forecasting plan. Its `warnings` hold the text of the
            warnings this call emitted, in the order they were emitted.

        Raises
        ------
        ValueError
            If `steps` is not an integer greater than or equal to 1, if
            `forecaster` is not supported, if the input does not fit its
            task type, or if an argument does not apply to it: `lags` and
            `window_features` for `ForecasterStats`, `ForecasterFoundation`
            and `ForecasterEquivalentDate`, and also `estimator` and
            `estimator_kwargs` for `ForecasterEquivalentDate`. For
            `ForecasterFoundation`, also if `estimator` is not a model
            supported by skforecast, if `estimator_kwargs` contains
            `'model_id'`, or if the model cannot predict `interval`.
        """

        # Checked first, so an invalid horizon fails before anything is
        # derived from it (a bool or a string would otherwise be coerced).
        steps = validate_steps(steps)

        data_profile = profile.data_profile

        fc = profile.forecaster
        unrecommended = False
        if forecaster is not None:
            if (
                forecaster not in profile.forecaster_candidates
                and forecaster not in BASELINE_FORECASTERS
            ):
                if forecaster not in FORECASTER_TASK_TYPES:
                    raise InvalidInputError(
                        f"Forecaster '{forecaster}' is not compatible with this "
                        f"profile. Available candidates: "
                        f"{profile.forecaster_candidates}.",
                        field = "forecaster",
                    )
                unrecommended = True
            fc = forecaster

        task_type = select_task_type_from_forecaster(fc)

        # Reject inputs incompatible with the resolved task type
        # (single-series tasks with multi-series input; multivariate with
        # series of different lengths or on long-format data).
        _validate_task_input(data_profile, task_type)

        # Arguments the forecaster has no use for are rejected rather than
        # silently ignored, so the plan never differs from what was asked.
        if task_type in ("statistical", "foundation", "baseline"):
            inapplicable = [("lags", lags), ("window_features", window_features)]
            if task_type == "baseline":
                inapplicable = [
                    ("estimator", estimator),
                    ("estimator_kwargs", estimator_kwargs),
                    *inapplicable,
                ]
                reason = (
                    "is a baseline that repeats past values: it has no "
                    "estimator and no lag or window features"
                )
            else:
                reason = (
                    "models the past values itself: it takes no lag or "
                    "window features"
                )
            given = [name for name, value in inapplicable if value is not None]
            if given:
                raise InvalidInputError(
                    f"'{fc}' {reason}, so {given} cannot be applied. Omit them.",
                    field = given[0],
                )

        # The baseline needs a frequency too (its offset counts periods of
        # it); checked before its warning about missing values.
        if task_type == "baseline":
            _check_frequency_known(fc, data_profile)

        # Every warning this call emits is also kept in `plan.warnings`, with
        # the same text, so it travels with the plan where Python warnings
        # are not seen (a server, JSON output, a saved plan).
        plan_warnings: list[str] = []

        if task_type == "baseline":
            missing_note = baseline_missing_values_note(data_profile)
            if missing_note is not None:
                message = (
                    f"'{fc}' cannot handle missing values: {missing_note}. "
                    f"Impute the target before fitting, or the predictions "
                    f"and metrics will contain missing values."
                )
                warnings.warn(message, UserWarning, stacklevel=2)
                plan_warnings.append(message)

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

        # The estimator name and its keyword arguments are written into the
        # generated script, so they are checked before anything is derived.
        validate_estimator(
            estimator        = est,
            estimator_kwargs = estimator_kwargs,
            task_type        = task_type,
        )
        plan_warnings += validate_estimator_kwargs(est, estimator_kwargs)

        # The foundation model is validated before anything else is derived,
        # so an unsupported model ID or interval fails with its own message.
        foundation_model = None
        if task_type == "foundation":
            foundation_model = validate_foundation_plan(
                estimator        = est,
                estimator_kwargs = estimator_kwargs,
                interval         = interval,
            )
        else:
            validate_interval(
                interval   = interval,
                task_type  = task_type,
                forecaster = fc,
            )

        if fc in REQUIRES_DATETIME_FREQ:
            _check_frequency_known(fc, data_profile)

        # The baseline cannot take exogenous variables; the explanation says
        # they are left out. A foundation model uses the columns its backend
        # accepts, so a model without covariate support uses none.
        if task_type == "foundation":
            use_exog = bool(foundation_exog_columns(
                info             = foundation_model,
                exog_columns     = data_profile.exog_columns,
                categorical_exog = data_profile.categorical_exog,
            ))
        else:
            use_exog = (
                task_type != "baseline"
                and check_exog_usage(data_profile.exog_columns)
            )

        baseline_explanation = None
        skipped_calendar_features: list[str] = []
        if task_type in ("statistical", "foundation", "baseline"):
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
            if lags is not None:
                _validate_lags(lags)

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
                calendar_encoding = select_calendar_encoding(est, task_type)
                calendar_names = list(profile.calendar_features)
                if use_exog:
                    # A generated column named like an exogenous column makes
                    # skforecast fail with duplicated feature names; the
                    # user's column is kept and the calendar feature skipped.
                    calendar_names, skipped_calendar_features = (
                        drop_colliding_calendar_features(
                            features     = calendar_names,
                            encoding     = calendar_encoding,
                            exog_columns = data_profile.exog_columns,
                        )
                    )
                if calendar_names:
                    calendar_features = {
                        "features": calendar_names,
                        "encoding": calendar_encoding,
                    }
                else:
                    calendar_features = None
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
                has_gaps         = data_profile.has_gaps,
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

        if task_type == "baseline":
            forecaster_kwargs, baseline_explanation = select_baseline_config(
                data_profile
            )

        interval_method = resolve_interval_method(task_type, interval)

        preprocessing_steps = derive_preprocessing_steps(
            profile          = data_profile,
            forecaster       = fc,
            foundation_model = foundation_model,
        )

        metric, metric_explanation, metrics_to_compute = select_metric(
            data_profile = data_profile,
        )

        # `dropna_from_series=False` also means that no value is missing
        # (missing timestamps become missing values after `asfreq()`), and
        # then there is no NaN handling to explain: saying the rows are kept
        # because the estimator tolerates NaN would be wrong for Ridge.
        has_missing = (
            bool(data_profile.missing_target)
            or bool(data_profile.missing_exog)
            or data_profile.has_gaps
        )
        explanation = build_plan_explanation(
            forecaster                = fc,
            estimator                 = est,
            lags                      = final_lags,
            window_features           = final_window_features,
            interval_method           = interval_method,
            dropna_from_series        = dropna_from_series if has_missing else None,
            use_exog                  = use_exog,
            metric_explanation        = metric_explanation,
            calendar_features         = calendar_features,
            task_type                 = task_type,
            skipped_calendar_features = skipped_calendar_features,
        )
        if foundation_model is not None:
            foundation_explanation = build_foundation_explanation(
                foundation_model = foundation_model,
                exog_columns     = data_profile.exog_columns,
                context_length   = (estimator_kwargs or {}).get(
                    "context_length", foundation_model.default_context_length
                ),
                n_observations   = max(
                    info.length for info in data_profile.series_lengths.values()
                ),
                n_series         = data_profile.n_series,
            )
            explanation = f"{explanation} {foundation_explanation}"
        if baseline_explanation is not None:
            explanation = f"{explanation} {baseline_explanation}"
            if data_profile.exog_columns:
                explanation += (
                    f" Exogenous variables {data_profile.exog_columns} are "
                    f"not used: the baseline only repeats past target values."
                )

        unrecommended_message = None
        if unrecommended:
            unrecommended_message = (
                f"Forecaster '{forecaster}' is not among the recommended "
                f"candidates for this profile "
                f"({profile.forecaster_candidates}), but it is used as "
                f"requested. It may be slow or perform poorly on this data."
            )
            plan_warnings.append(unrecommended_message)

        plan = ForecastPlan(
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
            warnings            = plan_warnings,
            explanation         = explanation,
        )

        _check_feature_name_collisions(plan, data_profile)

        # Warned once the plan exists, so a forecaster that a later check
        # rejects (the shape of the data, an argument it has no use for, a
        # foundation model or an interval it cannot serve) is never said to
        # be "used as requested", and with warnings raised as errors the
        # warning never hides that error.
        if unrecommended_message is not None:
            warnings.warn(unrecommended_message, UnrecommendedForecasterWarning)

        return plan

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
        rather than re-running the PACF-based selection. A value the new
        forecaster cannot use is not carried over: switching to a
        forecaster without lags (`ForecasterStats`, `ForecasterFoundation`,
        `ForecasterEquivalentDate`) drops `lags` and `window_features`,
        switching to another forecaster family drops `estimator` and
        `estimator_kwargs`, which are then re-derived, and changing the
        `estimator` without passing `estimator_kwargs` drops the kwargs of
        the previous estimator. The
        `llm_refined_fields` marks of the original plan are kept for the
        fields whose value is carried over unchanged. The `end_train` split
        boundary is not kept: a refined plan starts in prediction mode, so
        pass `test_size` again to evaluate it.

        In LLM mode, explicit `lags`/`window_features` overrides take
        precedence over the LLM suggestion (a `UserWarning` is emitted for
        each shadowed field, and a note recording the overridden field(s) is
        appended to the explanation). When both are supplied explicitly, the
        LLM has nothing left to decide and is not called. LLM mode does not
        apply when the refined plan's `task_type` is `'statistical'`,
        `'foundation'` or `'baseline'`, which do not use lags or window
        features; the prompt is ignored with a `UserWarning` and the LLM is
        not called. When the agent omits a field, or the LLM call fails or
        its suggestion is invalid (non-positive, duplicated or empty lags,
        malformed window features) or cannot satisfy the data budget, that
        field keeps the plan's existing value (a `UserWarning` is emitted on
        failure).

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
            The plan is rebuilt with `plan()`, so its `warnings` are those of
            that call (the ones of `plan` are not carried over); the warnings
            about the `prompt` that this method emits are not added to them.
        """

        allowed_keys = REFINE_PLAN_OVERRIDE_KEYS
        invalid_keys = set(overrides) - allowed_keys
        if invalid_keys:
            raise InvalidInputError(
                f"Invalid override keys: {sorted(invalid_keys)}. "
                f"Allowed keys: {sorted(allowed_keys)}.",
                field = sorted(invalid_keys)[0],
            )
        # Snapshot taken before the LLM branch injects its suggestions into
        # `overrides`, so that an inherited LLM mark is dropped only for a
        # field the caller overrode explicitly.
        explicit_keys = set(overrides)

        # The forecaster of the refined plan, not the one of `plan`, decides
        # whether the LLM has lags and window features to refine and which
        # values of `plan` still apply.
        target_forecaster = (
            overrides.get("forecaster", plan.forecaster) or profile.forecaster
        )
        target_task_type = FORECASTER_TASK_TYPES.get(
            target_forecaster, plan.task_type
        )

        reasoning = None
        shadowed_fields: list[str] = []
        llm_applied_fields: list[str] = []
        if prompt is not None:
            if self.llm is None:
                raise LLMRequiredError("refine_plan")

            if target_task_type in ("statistical", "foundation", "baseline"):
                warnings.warn(
                    f"LLM plan refinement does not apply to task_type "
                    f"'{target_task_type}' (no lags/window_features to refine). "
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
                if explicit_lags is not None:
                    _validate_lags(explicit_lags)
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

        # A value of `plan` is carried over only when the new forecaster can
        # use it: lags and window features only by the autoregressive
        # forecasters, an estimator only within its own family (an ML
        # regressor is not an ARIMA order, and the baseline has none).
        # Explicit overrides always reach `self.plan()`, which validates them.
        inherits_features = target_forecaster in AUTOREG_FORECASTERS
        inherits_estimator = target_task_type == plan.task_type or (
            inherits_features and plan.forecaster in AUTOREG_FORECASTERS
        )
        inherited_estimator = plan.estimator if inherits_estimator else None
        inherited_estimator_kwargs = (
            (plan.estimator_kwargs or None) if inherits_estimator else None
        )
        inherited_lags = (
            plan.forecaster_kwargs.get("lags") if inherits_features else None
        )
        inherited_window_features = (
            plan.forecaster_kwargs.get("window_features")
            if inherits_features
            else None
        )

        steps = overrides.get("steps", plan.steps)
        forecaster = overrides.get("forecaster", plan.forecaster)
        estimator = overrides.get("estimator", inherited_estimator)
        # Keyword arguments belong to the estimator they were written for
        # (`alpha` of Ridge, `cross_learning` of Chronos-2), so a different
        # estimator starts from its own defaults unless new ones are passed.
        if estimator != inherited_estimator:
            inherited_estimator_kwargs = None
        estimator_kwargs = overrides.get("estimator_kwargs", inherited_estimator_kwargs)
        interval = overrides.get("interval", plan.interval)
        lags = overrides.get("lags", inherited_lags)
        window_features = overrides.get("window_features", inherited_window_features)

        plan_arguments = {
            "profile": profile,
            "steps": steps,
            "forecaster": forecaster,
            "estimator": estimator,
            "estimator_kwargs": estimator_kwargs,
            "interval": interval,
            "lags": lags,
            "window_features": window_features,
        }
        try:
            refined_plan = self.plan(**plan_arguments)
        except InvalidInputError as exc:
            if not llm_applied_fields:
                raise
            # A suggestion of the LLM that the plan rejects (lags named like
            # an exogenous column, too long for the data) falls back to the
            # values the plan had, which are valid on their own.
            warnings.warn(
                f"The LLM suggestion for {llm_applied_fields} was rejected "
                f"({exc}); the refined plan keeps the previous values.",
                UserWarning,
                stacklevel=2,
            )
            plan_arguments["lags"] = inherited_lags
            plan_arguments["window_features"] = inherited_window_features
            llm_applied_fields = []
            reasoning = None
            refined_plan = self.plan(**plan_arguments)

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
        exog: pd.DataFrame | pd.Series | None = None,
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
            A CSV path or URL is the file the generated script loads, also
            with a `profile` built from another file; with a DataFrame the
            script loads the path recorded in the profile.
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
        exog : pandas DataFrame, pandas Series, default None
            Future exogenous variables covering the forecast horizon.
            Mirrors `forecast()` for signature consistency. Because this
            method only generates code (the rendered prediction-mode
            script loads the future values from `'exog_future.csv'` at run
            time), `exog` is optional here and is used only to validate
            the inputs: it must not be combined with `test_size`, and it
            must not be supplied when the data has no exogenous columns.
            Unlike `forecast()`, its dates and values are not checked, nor
            are the last values of the target: the script reads them when
            it runs.
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` (e.g. `[0.1, 0.9]` for 80 % interval). When
            None, no prediction intervals are computed. With a pre-built
            `plan`, a value replaces `plan.interval` and None keeps the
            intervals of the plan.
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
            Raises `ValueError` for a forecaster without lags
            (`ForecasterStats`, `ForecasterFoundation`,
            `ForecasterEquivalentDate`).
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
            Pre-computed profile. If None, profiling is performed from
            `data`. When given, it is usually the profile the plan was
            built from. `data` is profiled again with its target, date and
            series id columns: data of another structure (frequency,
            series, target or exogenous columns) raise `ValueError`, and
            data with other values (new rows, for example) run with the
            new profile, which says so in `DataProfile.warnings`.
        plan : ForecastPlan, default None
            Pre-computed plan to skip planning. If None, a plan is
            generated from the profile. Requires `profile` to also be
            provided. `forecaster`, `estimator`, `estimator_kwargs`,
            `lags` and `window_features` are fixed by the plan: a value
            equal to the plan's is accepted and a different one raises
            `ValueError`, pointing to `refine_plan()`. The plan is validated
            again before the script is rendered, so one edited with
            `model_copy(update=...)` or by assignment raises
            `ValidationError` unless it is still a valid `ForecastPlan`.
            A plan built for data of another frequency or shape, or that
            uses exogenous variables the data does not have, raises
            `ValueError`.

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
        data_df = data
        if profile is not None and data is not None:
            data_df, *_ = _resolve_inputs_with_profile(
                data, target, date_column, series_id_column, profile
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
            require_exog     = False,
        )
        profile = _with_data_path(profile, data)

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
        exog: pd.DataFrame | pd.Series | None = None,
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
        computed against the held-out observations. Before running, a
        missing value of the training set that the predictions read
        follows the rule of the prediction mode below (its last dates are
        not final rows: `test_size` sets them), and with
        `ForecasterRecursiveMultiSeries` every series needs a value on the
        last training date and on the test dates.
        A plan that carries the `end_train` of an earlier evaluation
        raises `ValueError` when `test_size` is not passed, instead of
        evaluating the same dates again: pass `test_size` to evaluate.
        - Prediction mode (`test_size` is None, the default): the
        forecaster is trained on all available data and forecasts the
        future. No metrics are returned because there is no ground
        truth to compare against. When the data contains exogenous
        variables, future values must be supplied through `exog`.
        Before running, final rows without a target value raise
        `InvalidInputError` (`ForecasterRecursiveMultiSeries`, which
        ignores them, gives a warning), and so does a missing value of the
        target that the lags read when the estimator does not tolerate
        missing values (a warning when it does), or that
        `ForecasterEquivalentDate` or the inverse of the differentiation
        reads. A missing value that no lag reads for the `steps` asked, or
        that only the rolling statistics read (they skip it), is left to
        the warning of skforecast: the predictions do not use it.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path
            Input dataset, a single series, or path to a CSV file. When a
            pandas Series is passed, the target is derived from its name.
            A CSV path or URL is the file the generated script loads, also
            with a `profile` built from another file; with a DataFrame the
            script loads the path recorded in the profile.
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
        exog : pandas DataFrame, pandas Series, default None
            Future exogenous variables covering the forecast horizon: a
            row for each of the `steps` dates that follow the last date of
            the data (in long format, for each series, with the series id
            column), indexed or keyed by date as the data. A named pandas
            Series is one variable. Used only in prediction mode
            (`test_size=None`) and required there when the data contains
            exogenous variables. Must not be combined with `test_size`:
            in evaluation mode the test-set exogenous values are taken
            from the split. Its columns, dates and values are checked
            before running: a missing date raises `InvalidInputError`, and
            a new category or a missing value raises when the estimator
            does not tolerate missing values and gives a warning when it
            does.
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` (e.g. `[0.1, 0.9]` for 80 % interval). When
            None, no prediction intervals are computed. With a pre-built
            `plan`, a value replaces `plan.interval` and None keeps the
            intervals of the plan.
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
            Raises `ValueError` for a forecaster without lags
            (`ForecasterStats`, `ForecasterFoundation`,
            `ForecasterEquivalentDate`).
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
            Pre-computed profile. If None, profiling is performed from
            `data`. When given, it is usually the profile the plan was
            built from. `data` is profiled again with its target, date and
            series id columns: data of another structure (frequency,
            series, target or exogenous columns) raise `ValueError`, and
            data with other values (new rows, for example) run with the
            new profile, which says so in `DataProfile.warnings`.
        plan : ForecastPlan, default None
            Pre-computed plan to skip planning. If None, a plan is
            generated from the profile. Requires `profile` to also be
            provided. `forecaster`, `estimator`, `estimator_kwargs`,
            `lags` and `window_features` are fixed by the plan: a value
            equal to the plan's is accepted and a different one raises
            `ValueError`, pointing to `refine_plan()`. The plan is validated
            again before the script is rendered, so one edited with
            `model_copy(update=...)` or by assignment raises
            `ValidationError` unless it is still a valid `ForecastPlan`.
            A plan built for data of another frequency or shape, or that
            uses exogenous variables the data does not have, raises
            `ValueError`.

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

        exog = as_exog_frame(exog)
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
        profile = _with_data_path(profile, data)

        if plan.end_train is not None:
            _check_evaluated_target(
                data         = data_df,
                data_profile = profile.data_profile,
                end_train    = plan.end_train,
                steps        = plan.steps,
                # ForecasterDirectMultiVariate is scored on its level, the
                # first target column, as the script writes it.
                level        = (
                    profile.data_profile.target[0]
                    if plan.forecaster == "ForecasterDirectMultiVariate"
                    and isinstance(profile.data_profile.target, list)
                    else None
                ),
            )
        elif exog is not None:
            validate_future_exog(
                exog    = exog,
                data    = data_df,
                profile = profile.data_profile,
                plan    = plan,
            )
        validate_infinite_target(
            data       = data_df,
            profile    = profile.data_profile,
            plan       = plan,
            prediction = plan.end_train is None,
        )
        validate_series_lengths(
            data      = data_df,
            profile   = profile.data_profile,
            plan      = plan,
            end_train = plan.end_train,
        )
        # Last of the checks: it can warn, and a warning is not given for a
        # forecast that a later check rejects.
        validate_evaluation_partition(
            data    = data_df,
            profile = profile.data_profile,
            plan    = plan,
        )

        check_estimator_installed(plan.estimator, plan.task_type)

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
            - If a date string (ISO format, e.g. `'2023-03-01'`) or pandas 
            Timestamp, it is the last date included in the initial training set. 
            Requires a datetime index with a known frequency; a `ValueError` is 
            raised otherwise, or when the date cannot be parsed.
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

            - If `None`, the forecaster is trained once, in the first fold
            (`False`, the skforecast default). Refitting multiplies the
            training cost by the number of folds, which the explanation
            states.
            - If `True`, the forecaster is refitted in each fold.
            - If `False`, the forecaster is trained only in the first fold.
            - If an integer, the forecaster is trained in the first fold and then refitted
            every `refit` folds.
        fixed_train_size : bool, default None
            Whether the training size is fixed or increases in each fold.
            Only applies when the forecaster is refitted: with `refit=False`
            (explicit or by default) it has no effect and an
            `IgnoredArgumentWarning` says so, except for `ForecasterStats`,
            which is always refitted.
        gap : int, default None
            Number of observations between the end of the training set and the start of the
            test set.
        skip_folds : int, list, default None
            Number of folds to skip.

            - If an integer, every 'skip_folds'-th is returned.
            - If a list, the indexes of the folds to skip.

            For example, if `skip_folds=3` and there are 10 folds, the returned folds are
            0, 3, 6, and 9. If `skip_folds=[1, 2, 3]`, the returned folds are 0, 4, 5, 6, 7,
            8, and 9. A list with an index beyond the folds of the strategy
            raises `ValueError`.
        allow_incomplete_fold : bool, default None
            Whether to allow the last fold to include fewer observations than `steps`.
            If `False`, the last fold is excluded if it is incomplete.

        Returns
        -------
        result : CVResult
            Cross-validation strategy and the decisions behind it. Pass it
            as `cv` to `backtest()`, `backtest_code()` or `compare()`, or
            as `context` to `ask()`. Contains the following attributes:

            - profile: profile the strategy was derived from.
            - plan: plan the strategy was derived from.
            - cv: configured `TimeSeriesFold` fold splitter.
            - cv_config: resolved `TimeSeriesFold` parameters plus the
            resulting `n_folds`. For a `ForecasterStats` plan, the
            strategy skforecast runs: `refit=True` (it refits ARIMA in
            every fold) and, when `cv` does not refit,
            `fixed_train_size=True`.
            - code: Python snippet that builds the `TimeSeriesFold` of
            `cv_config`, the one the backtesting script embeds.
            - explanation: human-readable explanation of the chosen
            configuration (LLM reasoning first when a prompt was used).

        References
        ----------
        [1] Skforecast `TimeSeriesFold` API Reference:
            https://skforecast.org/latest/api/model_selection#skforecast.model_selection._split.TimeSeriesFold
        
        """

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
                           agent   = self._resolve_cv_agent(),
                           profile = profile,
                           plan    = plan,
                           prompt  = prompt,
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

        # The LLM narrative is not a TimeSeriesFold parameter: keep it out
        # of the splitter and prepend it to the explanation.
        reasoning = defaults.pop("_reasoning", None)

        # With the `refit` that runs, which the LLM may have chosen.
        _warn_window_without_refit(
            fixed_train_size = fixed_train_size,
            refit            = defaults.get("refit"),
            forecaster       = plan.forecaster,
        )

        # Same construction and validation path the LLM loop uses, so a
        # configuration that passed there cannot fail here. Resolves a
        # fractional or Timestamp initial_train_size, checks a date-based
        # one against the dataset index and requires at least 2 folds.
        cv = build_cv(cv_params=defaults, data_profile=profile.data_profile)
        cv_config, cv_explanation = resolve_cv_config(
            cv,
            profile.data_profile,
            trains     = plan.task_type != "foundation",
            forecaster = plan.forecaster,
        )

        if reasoning:
            cv_explanation = f"{reasoning} {cv_explanation}"

        # skforecast refits ForecasterStats in every fold whatever `refit`
        # says. The script, `cv_config` and the explanation say what runs;
        # an argument the user passed and that does not run is also warned
        # about, so it is not replaced without notice.
        executed = cv_as_executed(cv, plan.forecaster)
        ignored = [
            f"`{name}={value!r}`"
            for name, value, ran in (
                ("refit", refit, executed.refit),
                ("fixed_train_size", fixed_train_size, executed.fixed_train_size),
            )
            if value is not None and value != ran
        ]
        if ignored:
            warnings.warn(
                f"{' and '.join(ignored)} do not apply to ForecasterStats: "
                f"skforecast refits it in every fold, so its backtest runs "
                f"with `refit=True` and "
                f"`fixed_train_size={executed.fixed_train_size}`. Pass those "
                f"values to avoid this warning.",
                IgnoredArgumentWarning,
                stacklevel = 2,
            )

        # The same snippet the backtesting script embeds, so the strategy
        # can be inspected and reproduced on its own. For ForecasterStats it
        # is the strategy skforecast runs, while `cv` keeps the parameters
        # as given, so reusing it with another forecaster does not change
        # how that one is trained.
        code_lines = ["from skforecast.model_selection import TimeSeriesFold", ""]
        _emit_cv_configuration(code_lines, executed)

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
        data: pd.Series | pd.DataFrame | str | Path | None,
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
        data : pandas Series, pandas DataFrame, str, Path, None
            Input dataset, a single series, or path to a CSV file. When a
            pandas Series is passed, the target is derived from its name.
            A CSV path or URL is the file the generated script loads, also
            with a `profile` built from another file. None is accepted when
            `profile` and `plan` are given: the script is rendered from the
            profile and loads the data path recorded in it.
        cv : TimeSeriesFold, CVResult
            Time series cross-validation fold splitter (output of
            `create_cv()` or user-constructed) [1]_.
            The `CVResult` returned by `create_cv()` is accepted as well;
            its `cv` splitter is used.
            Without `plan`, `forecaster`, `estimator`, `estimator_kwargs`
            and `interval`, its plan is the one run. Its profile must
            describe data of the same structure (format, target, series,
            frequency, exogenous columns), or `ValueError` is raised.
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
            None, no prediction intervals are computed. With a pre-built
            `plan`, a value replaces `plan.interval` and None keeps the
            intervals of the plan.
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
            Pre-computed profile, usually the profile the plan was built
            from. `data` is profiled again with its target, date and
            series id columns: data of another structure (frequency,
            series, target or exogenous columns) raise `ValueError`, and
            data with other values (new rows, for example) run with the
            new profile, which says so in `DataProfile.warnings`.
        plan : ForecastPlan, default None
            Pre-computed plan to skip planning. `forecaster`, `estimator`
            and `estimator_kwargs` are fixed by the plan: a value equal
            to the plan's is accepted and a different one raises
            `ValueError`, pointing to `refine_plan()`. The plan is validated
            again before the script is rendered, so one edited with
            `model_copy(update=...)` or by assignment raises
            `ValidationError` unless it is still a valid `ForecastPlan`.

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

        cv_result = cv if isinstance(cv, CVResult) else None
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
            cv_result        = cv_result,
        )
        profile = _with_data_path(profile, data)

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
            A CSV path or URL is the file the generated script loads, also
            with a `profile` built from another file; with a DataFrame the
            script loads the path recorded in the profile.
        cv : TimeSeriesFold, CVResult
            Time series cross-validation fold splitter (output of `create_cv()`
            or user-constructed) [1]_.
            The `CVResult` returned by `create_cv()` is accepted as well;
            its `cv` splitter is used.
            Without `plan`, `forecaster`, `estimator`, `estimator_kwargs`
            and `interval`, its plan is the one run. Its profile must
            describe data of the same structure (format, target, series,
            frequency, exogenous columns), or `ValueError` is raised.
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
            None, no prediction intervals are computed. With a pre-built
            `plan`, a value replaces `plan.interval` and None keeps the
            intervals of the plan.
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
            Pre-computed profile, usually the profile the plan was built
            from. `data` is profiled again with its target, date and
            series id columns: data of another structure (frequency,
            series, target or exogenous columns) raise `ValueError`, and
            data with other values (new rows, for example) run with the
            new profile, which says so in `DataProfile.warnings`.
        plan : ForecastPlan, default None
            Pre-computed plan to skip planning. `forecaster`, `estimator`
            and `estimator_kwargs` are fixed by the plan: a value equal
            to the plan's is accepted and a different one raises
            `ValueError`, pointing to `refine_plan()`. The plan is validated
            again before the script is rendered, so one edited with
            `model_copy(update=...)` or by assignment raises
            `ValidationError` unless it is still a valid `ForecastPlan`.
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

        cv_result = cv if isinstance(cv, CVResult) else None
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
            cv_result        = cv_result,
        )
        profile = _with_data_path(profile, data)

        _check_evaluated_target(
            data         = data_df,
            data_profile = profile.data_profile,
            cv           = cv,
        )
        validate_infinite_target(
            data       = data_df,
            profile    = profile.data_profile,
            plan       = plan,
            prediction = False,
        )
        validate_series_lengths(
            data       = data_df,
            profile    = profile.data_profile,
            plan       = plan,
            whole_data = True,
        )
        # A direct forecaster predicts the `steps` it was built for, and a
        # fold with a gap asks it for `steps + gap`.
        if plan.forecaster in DIRECT_FORECASTERS and cv.gap > 0:
            raise InvalidInputError(
                f"{plan.forecaster} is trained to predict {plan.steps} steps, "
                f"and with `gap={cv.gap}` each fold needs steps + gap = "
                f"{plan.steps + cv.gap} steps ahead, so skforecast would "
                f"fail. Use a strategy without gap, or a recursive forecaster.",
                field = "cv",
            )

        # Resolved CV parameters (with the fold and training counts) and their
        # explanation, which states the cost of the backtest.
        cv_config, cv_explanation = resolve_cv_config(
            cv,
            profile.data_profile,
            trains     = plan.task_type != "foundation",
            forecaster = plan.forecaster,
        )
        warn_long_training(
            estimator_fits = count_estimator_fits(
                                 n_fits     = cv_config["n_fits"],
                                 forecaster = plan.forecaster,
                                 steps      = plan.steps,
                             ),
            n_fits         = cv_config["n_fits"],
            forecaster     = plan.forecaster,
            steps          = plan.steps,
        )

        check_estimator_installed(plan.estimator, plan.task_type)

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
        baseline: bool = True,
        progress_callback: Callable[[CompareProgress], None] | None = None,
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
            A CSV path or URL is the file the generated script loads, also
            with a `profile` built from another file; with a DataFrame the
            script loads the path recorded in the profile.
        cv : TimeSeriesFold, CVResult
            Cross-validation strategy applied identically to every
            candidate. The `steps` value is inferred from `cv.steps`.
            The `CVResult` returned by `create_cv()` is accepted as well;
            its `cv` splitter is used.
            Its profile must describe data of the same structure (format,
            target, series, frequency, exogenous columns), or `ValueError`
            is raised.
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
            unique, and every candidate must belong to the same forecaster
            family: a multivariate forecaster is scored on the single series
            it predicts, a multi-series forecaster on the average across all
            series, so the two are never ranked together.
            `ForecasterFoundation` belongs to the family of the data: it
            is ranked with the single-series forecasters on one series and
            with `ForecasterRecursiveMultiSeries` on several. When None,
            the set is built from the profile's forecaster candidates of
            the same family as the recommended forecaster (with several
            series, `ForecasterRecursiveMultiSeries` and
            `ForecasterFoundation`); when that leaves a single forecaster,
            its estimator candidates are compared instead.
        metric : str, list of str, default None
            Metric(s) computed per candidate. When a list is passed, the
            first metric is used to rank the table. When None, the plan
            default metric (and its metric panel) is used.
        interval : list of float, default None
            Prediction interval quantiles as a two-element list
            `[lower, upper]` computed for every candidate. When None, no
            prediction intervals are computed.
        profile : ForecastingProfile, default None
            Pre-computed profile, shared by every candidate. `data` is
            profiled again with its target, date and series id columns:
            data of another structure (frequency, series, target or
            exogenous columns) raise `ValueError`, and data with other
            values (new rows, for example) run with the new profile,
            which says so in `DataProfile.warnings`.
        show_progress : bool, default True
            Whether to display a progress bar across candidates.
        baseline : bool, default True
            Whether to add a `ForecasterEquivalentDate` baseline (seasonal
            naive, or naive when no seasonal period applies) as one more
            row, ranked like the other candidates. The explanation states
            whether the best configuration beats it and by how much. It is
            not added for multi-series data, which it cannot forecast, nor
            when the target has missing values or missing timestamps, which
            it would repeat as missing predictions (the explanation says
            why), nor with an asymmetric `interval`, which it cannot
            predict, nor when `candidates` already contains a
            `ForecasterEquivalentDate` (that candidate is then the
            baseline).
        progress_callback : Callable, default None
            Function called with a `CompareProgress` when each candidate
            starts and when it ends, for example to report progress
            outside a notebook. An exception it raises is not recorded as
            a candidate failure: it stops the comparison and propagates
            to the caller, so raising from it cancels the remaining
            candidates. When None, no events are sent.

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
            - baseline_name: name of the baseline candidate, or None.
            - best_name: name of the top-ranked candidate.
            - best_candidate: top-ranked candidate as a `BacktestResult`.

        Raises
        ------
        AllCandidatesFailedError
            If every candidate fails to run. The individual failures are
            available on the `failures` attribute of the raised error.
        TypeError
            If `progress_callback` is not callable.
        ValueError
            If `metric` is an empty list, or if `candidates` is empty,
            contains a malformed entry, repeats a name, mixes forecaster
            families whose metrics are not comparable (multi-series with
            multivariate), or uses the name reserved for the baseline, or
            if `data` does not have the structure of `profile`.

        Warns
        -----
        CandidateFailedWarning
            Once per failed candidate.
        MissingBackendWarning
            When `candidates` is None and the backend of the default
            foundation model is not installed, so `ForecasterFoundation`
            is left out of the comparison.

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

        if progress_callback is not None and not callable(progress_callback):
            raise InvalidInputTypeError(
                f"`progress_callback` must be callable or None, got "
                f"{type(progress_callback).__name__}.",
                field = "progress_callback",
            )

        cv_result = cv if isinstance(cv, CVResult) else None
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
        else:
            profile = self._refresh_profile(data_df, profile)
        if cv_result is not None:
            _check_cv_matches_profile(cv_result, profile.data_profile)
        # Every candidate script loads the file the comparison read.
        profile = _with_data_path(profile, data)
        run_data_path = (
            profile.data_profile.data_path if isinstance(data, (str, Path)) else None
        )

        # Automatic candidates leave out a foundation model whose backend
        # is not installed, rather than fail on every call; the warning and
        # the explanation say which package to install.
        excluded: frozenset[str] = frozenset()
        backend_note = None
        if candidates is None:
            excluded, backend_note = missing_foundation_backend(profile)
            if backend_note is not None:
                warnings.warn(backend_note, MissingBackendWarning, stacklevel=2)
        candidate_configs = resolve_compare_candidates(
            candidates, profile, exclude=excluded
        )

        # Checked once here: an invalid interval would make every candidate
        # fail. Whether a method needs a symmetric interval is checked per
        # candidate by `plan()`.
        validate_interval(interval)

        # Checked once here: every candidate would fail on the same dates.
        _check_evaluated_target(
            data         = data_df,
            data_profile = profile.data_profile,
            cv           = cv,
        )

        baseline_name = None
        baseline_note = None
        if baseline:
            candidate_configs, baseline_name, baseline_note = (
                add_baseline_candidate(candidate_configs, profile, interval)
            )

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
                raise InvalidInputError(
                    "`metric` must not be an empty list.",
                    field = "metric",
                )
            validate_metrics(metric_override)
            ranking_metric = metric_override[0]
            metric_columns = metric_override

        steps = cv.steps

        # Shared CV parameters (with the fold and training counts) and their
        # explanation. The folds are counted before any candidate runs, on
        # the untouched `cv`.
        cv_config, cv_explanation = resolve_cv_config(cv, profile.data_profile)
        n_fits = cv_config["n_fits"]

        # Automatic candidates are also kept within a fit budget: with a
        # strategy that refits in every fold a direct forecaster can take
        # hours. Explicit candidates always run; they only get the warning.
        budget_note = None
        if candidates is None:
            candidate_configs, budget_note = exclude_costly_candidates(
                candidate_configs = candidate_configs,
                preferred         = profile.forecaster,
                n_fits            = n_fits,
                steps             = steps,
                n_folds           = cv_config["n_folds"],
            )
            if budget_note is not None:
                warnings.warn(budget_note, LongTrainingWarning, stacklevel=2)

        # Warned once per costly candidate here; the warning of each
        # backtest() call is silenced in the loop so it is not repeated.
        for _, config in candidate_configs:
            forecaster = config.get("forecaster") or profile.forecaster
            warn_long_training(
                estimator_fits = count_estimator_fits(
                                     n_fits     = n_fits,
                                     forecaster = forecaster,
                                     steps      = steps,
                                     n_folds    = cv_config["n_folds"],
                                 ),
                n_fits         = n_fits,
                forecaster     = forecaster,
                steps          = steps,
            )

        iterator: Any = candidate_configs
        if show_progress:
            from tqdm.auto import tqdm

            iterator = tqdm(candidate_configs, desc="Comparing forecasters")

        rows: list[tuple[dict, float]] = []
        ranked: list[tuple[str, BacktestResult, float]] = []
        failures: dict[str, CandidateFailure] = {}
        n_candidates = len(candidate_configs)

        def notify(event: CompareProgress) -> None:
            # A callback that cancels leaves the loop early, so the progress
            # bar would stay open on a partial count.
            try:
                progress_callback(event)
            except BaseException:
                if show_progress:
                    iterator.close()
                raise

        for position, (name, config) in enumerate(iterator):
            # Called outside the `try` below: an exception raised by the
            # callback cancels the comparison instead of failing a candidate.
            if progress_callback is not None:
                notify(
                    CompareProgress(
                        candidate = name,
                        status    = "started",
                        completed = position,
                        total     = n_candidates,
                    )
                )

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

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=LongTrainingWarning)
                    # The candidate runs on the DataFrame already read;
                    # its script loads the file the comparison read.
                    with _data_path_of_run(run_data_path):
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

            if progress_callback is not None:
                notify(
                    CompareProgress(
                        candidate = name,
                        status    = "failed" if name in failures else "succeeded",
                        completed = position + 1,
                        total     = n_candidates,
                        error     = row["error"],
                    )
                )

        results = build_comparison_table(
            rows           = rows,
            metric_columns = metric_columns,
            any_error      = bool(failures),
            baseline_name  = baseline_name,
        )

        # Order the successful candidates using the same
        # ascending-with-NaN-last, stable ordering as the results table
        # (the baseline wins ties), so the mapping iterates best to worst
        # and its first entry is the winner reported by `best_name` /
        # `best_candidate`.
        ranked_sorted = sorted(
            ranked, key=lambda item: compare_sort_key(item, baseline_name)
        )
        if not ranked_sorted:
            raise AllCandidatesFailedError(failures)
        candidate_results = {name: bt for name, bt, _ in ranked_sorted}

        explanation = build_comparison_explanation(
            n_candidates   = len(candidate_configs),
            ranked         = ranked_sorted,
            ranking_metric = ranking_metric,
            any_error      = bool(failures),
            cv_explanation = cv_explanation,
            baseline_name  = baseline_name,
            baseline_note  = baseline_note,
            backend_note   = backend_note,
            budget_note    = budget_note,
        )

        return ComparisonResult(
            profile        = profile,
            cv_config      = cv_config,
            results        = results,
            candidates     = candidate_results,
            failures       = failures,
            ranking_metric = ranking_metric,
            explanation    = explanation,
            baseline_name  = baseline_name,
        )

    def ask(
        self,
        prompt: str,
        context: ExplainableResult | None = None,
        *,
        plan: ForecastPlan | None = None,
        skills: list[str] | None = None,
        include_reference: bool = False,
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
            The plan is validated again before the script is rendered, so
            one edited with `model_copy(update=...)` or by assignment
            raises `ValidationError` unless it is still a valid
            `ForecastPlan`.
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
            not: pass `context=profile, plan=plan`), or if `plan`
            accompanies a context other than a `ForecastingProfile`.
        pydantic.ValidationError
            If `plan` does not pass the validators of `ForecastPlan` (a
            subclass of `ValueError`).

        Warns
        -----
        DataSentToLLMWarning
            If `context` carries values of its own (predictions, metrics)
            while `send_data_to_llm` is False.

        Notes
        -----
        An LLM must be configured at init time. When `llm` is None,
        this method cannot operate and raises `LLMRequiredError`.
        """

        if self.llm is None:
            raise LLMRequiredError("ask")

        if isinstance(context, ForecastPlan):
            raise InvalidInputTypeError(
                "A `ForecastPlan` cannot be explained on its own: it does not "
                "carry the dataset it was derived from. Pass "
                "`context=profile, plan=plan`.",
                field = "context",
            )
        if context is not None and not isinstance(context, ExplainableResult):
            raise InvalidInputTypeError(
                f"`context` must be a `ForecastingProfile` or a workflow "
                f"result (for example `ForecastResult`, `BacktestResult`, "
                f"`ComparisonResult`, `CodeGenerationResult`, or `CVResult`), "
                f"got {type(context).__name__}.",
                field = "context",
            )
        if plan is not None and not isinstance(context, ForecastingProfile):
            raise InvalidInputTypeError(
                "`plan` only accompanies a `ForecastingProfile` passed as "
                "`context`; any other context already carries its own plan.",
                field = "plan",
            )

        # A profile with a plan is explained through the script the two
        # produce together, exactly as `forecast_code()` would render it,
        # after validating the plan again as `forecast_code()` does.
        if isinstance(context, ForecastingProfile) and plan is not None:
            plan = _revalidate_plan(plan)
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
            # The profile gives the data's task type, the plan the one of
            # the forecaster actually used (a statistical model or the
            # baseline chosen over the recommendation). A comparison also
            # ranks its baseline, which the winner's plan does not show.
            task_types: list[str] = []
            if profile is not None:
                task_types.append(profile.task_type)
            if plan is not None and plan.task_type not in task_types:
                task_types.append(plan.task_type)
            if (
                isinstance(context, ComparisonResult)
                and context.baseline_name is not None
                and "baseline" not in task_types
            ):
                task_types.append("baseline")
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
                task_type    = task_types,
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

    def check_llm(self, test_call: bool = False) -> LLMCheckResult:
        """
        Check whether the configured LLM can be used, and report why not.

        Runs the static checks of `check_llm_config()` on the assistant's
        `llm`, `base_url` and `api_key`: the provider string is parsed,
        the credential source is identified (explicit `api_key`, the
        provider environment variable read by pydantic-ai, the AWS
        credential chain, or none for Ollama) and whether the variable is
        set, `base_url` is interpreted as the provider does (endpoint,
        Ollama server, AWS region, or ignored), the required modules are
        probed and, for Ollama, the server is contacted. With
        `test_call=True` and every static check passed, a one-line
        prompt is sent to the model through the same agent `ask()` uses,
        without skills, reference or data. Nothing is raised on a failed
        check: the result reports it. Credential values never appear in
        the result.

        Parameters
        ----------
        test_call : bool, default False
            Whether to send a minimal prompt to the model once the static
            checks pass. Costs one small request.

        Returns
        -------
        result : LLMCheckResult
            Outcome of every check. Contains the following attributes:

            - llm: provider string as given.
            - provider: provider prefix, None when the string is invalid.
            - model_name: model name, None when the string is invalid.
            - credential_source: `'api_key'`, `'env_var'`,
            `'aws_credential_chain'`, `'none'` or `'unknown'`.
            - env_var: environment variable the provider reads, if any.
            - env_var_set: whether it is set, None when not consulted.
            - credential_note: description of the credential resolution.
            - base_url: effective endpoint after provider defaults.
            - base_url_note: what `base_url` means for the provider.
            - dependencies_ok: whether the required modules are installed.
            - missing_dependencies: modules not installed, with the extra
            that installs them.
            - reachable: for Ollama, whether the server answered.
            - call_ok: whether the test call succeeded, None if skipped.
            - error: first failure found, None when all checks passed.
            - ok: True when no check failed.

        Raises
        ------
        LLMRequiredError
            If no LLM was configured at init time.
        """

        if self.llm is None:
            raise LLMRequiredError("check_llm")

        result = check_llm_config(
            llm      = self.llm,
            base_url = self.base_url,
            api_key  = self.api_key,
        )

        if not test_call or not result.ok:
            return result

        message = "Reply with the single word OK."
        try:
            from .llm import AskDeps

            agent = self._resolve_agent()
            deps = AskDeps(
                profile           = None,
                plan              = None,
                skills            = [],
                include_reference = False,
            )
            model_settings = build_ollama_settings(
                self.llm, estimate_prompt_tokens([], False), message
            )
            run_agent_sync(agent, message, deps=deps, model_settings=model_settings)
        except Exception as exc:
            return result.model_copy(
                update={"call_ok": False, "error": str(LLMCallError(self.llm, exc))}
            )

        return result.model_copy(update={"call_ok": True})

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
        `forecast()`. Rejects plan-shaping overrides that contradict a
        supplied plan, profiles the data when no profile is given,
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
            exogenous columns, after the last values of the target are
            checked (`validate_last_window`). True when the workflow executes
            the script, False when it only renders it. When True, a `plan`
            with `end_train` also needs `test_size` (`forecast()` does not
            evaluate a split it was not asked for).

        Returns
        -------
        profile : ForecastingProfile
            Resolved profile.
        plan : ForecastPlan
            Resolved plan, carrying `end_train` when `test_size` is set.

        Raises
        ------
        ValueError
            When `data` does not have the structure of a given `profile`
            (`_refresh_profile`), when a `plan` is given for data of
            another frequency or shape (`_check_plan_matches_profile`), or
            carries `end_train` without `test_size` and `require_exog` is
            True.
        """

        plan = _revalidate_plan(plan)
        _check_plan_overrides(
            plan             = plan,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
            lags             = lags,
            window_features  = window_features,
        )

        received_profile = profile is not None
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
                raise InvalidInputError(
                    f"`steps` ({steps}) does not match `plan.steps` "
                    f"({plan.steps}). Omit `steps` to use the plan's horizon, "
                    f"or refine the plan with `refine_plan(steps=...)`.",
                    field = "steps",
                )
            steps = plan.steps
        elif steps is None:
            raise InvalidInputError(
                "`steps` is required when `plan` is not provided.",
                field = "steps",
            )

        if received_profile and data is not None:
            profile = self._refresh_profile(data, profile)
        if plan is not None:
            _check_plan_matches_profile(plan, profile.data_profile)
            # The split of an earlier evaluation is not reused without
            # saying so: forecast() would evaluate old dates again when the
            # future was asked for.
            if require_exog and test_size is None and plan.end_train is not None:
                raise InvalidInputError(
                    f"The plan carries the split of an evaluation "
                    f"(`end_train='{plan.end_train}'`) and `test_size` was not "
                    f"passed. Pass `test_size` to evaluate again, or a plan "
                    f"without it, `plan.model_copy(update={{'end_train': None}})`, "
                    f"to forecast the future.",
                    field = "plan",
                )

        has_exog = bool(profile.data_profile.exog_columns)
        # Evaluation mode is driven by `test_size`, or by a pre-built plan
        # that already carries an `end_train` split boundary. Everything
        # else is prediction mode (forecast the future).
        evaluate = test_size is not None or (
            plan is not None and plan.end_train is not None
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
        elif interval is not None:
            plan = _apply_interval_to_plan(plan, interval)

        if require_exog and not evaluate:
            # Before `exog` is required: final rows without a target value
            # are the usual reason it is missing (future rows appended to
            # carry the exogenous variables).
            validate_last_window(
                data    = data,
                profile = profile.data_profile,
                plan    = plan,
            )

        # Validated once the plan is known: whether future `exog` is needed
        # depends on the plan using it, not only on the data having it.
        _validate_forecast_mode(
            evaluate     = evaluate,
            exog         = exog,
            has_exog     = has_exog,
            steps        = steps,
            require_exog = require_exog,
            uses_exog    = plan.use_exog,
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
            plan = plan.model_copy(update={"end_train": end_train}, deep=True)

        # One forecast of `steps` observations is evaluated, so a longer test
        # set would be scored on its first `steps` rows only (without saying
        # so) and a shorter one cannot hold the forecast.
        if evaluate and plan.end_train is not None:
            n_test = count_test_observations(
                start_date     = profile.data_profile.start_date,
                frequency      = profile.data_profile.frequency,
                n_observations = profile.data_profile.span_index_length,
                end_train      = plan.end_train,
            )
            if n_test is not None and n_test != plan.steps:
                raise InvalidInputError(
                    f"The test set has {n_test} observations but `steps` is "
                    f"{plan.steps}. forecast() evaluates one forecast of "
                    f"`steps` observations, so the test set must have the "
                    f"same length: pass test_size={plan.steps}. To evaluate "
                    f"over a longer period, use backtest() (create_cv() "
                    f"builds the folds).",
                    field = "test_size",
                )

        # A plan received (saved, or built for other data) is checked
        # against the exogenous columns of this profile, as `plan()` does.
        _check_feature_name_collisions(plan, profile.data_profile)

        return profile, plan

    def _prepare_backtest(
        self,
        data: pd.Series | pd.DataFrame | str | Path | None,
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
        cv_result: CVResult | None = None,
    ) -> tuple[ForecastingProfile, ForecastPlan]:
        """
        Resolve profile and plan for backtesting workflows.

        Shared preparation logic used by both `backtest_code()` and
        `backtest()`. Coerces data, auto-generates profile/plan when
        not provided, and validates that `cv.steps` matches `plan.steps`
        when a plan is explicitly passed.

        Parameters
        ----------
        data : pandas Series, pandas DataFrame, str, Path, None
            Input dataset, a single series, or path to a CSV file. None
            only when `profile` is given, for rendering without data.
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
        cv_result : CVResult, default None
            The `CVResult` passed as `cv`, when it was one. Without `plan`
            and without model arguments (`forecaster`, `estimator`,
            `estimator_kwargs`, `interval`), its plan is the one run. Its
            profile must describe data of the same structure.

        Returns
        -------
        profile : ForecastingProfile
            Resolved profile.
        plan : ForecastPlan
            Resolved plan.
        """

        plan = _revalidate_plan(plan)
        _check_plan_overrides(
            plan             = plan,
            forecaster       = forecaster,
            estimator        = estimator,
            estimator_kwargs = estimator_kwargs,
        )
        # A CVResult carries the plan its strategy was created for: without
        # a plan or model arguments, that plan runs instead of a new default
        # one (another estimator, no interval).
        if (
            plan is None
            and cv_result is not None
            and forecaster is None
            and estimator is None
            and estimator_kwargs is None
            and interval is None
        ):
            plan = _revalidate_plan(cv_result.plan)
        received_plan = plan is not None

        if data is None and profile is None:
            raise InvalidInputError(
                "`data` is required when `profile` is not provided.",
                field = "data",
            )
        if data is not None:
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
        elif data is not None:
            profile = self._refresh_profile(data_df, profile)
        # Before a plan is built: the strategy must fit these data first.
        if cv_result is not None:
            _check_cv_matches_profile(cv_result, profile.data_profile)

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
                raise InvalidInputError(
                    f"cv.steps ({cv.steps}) does not match plan.steps "
                    f"({plan.steps}). These must be equal: "
                    f"ForecasterDirect and ForecasterDirectMultiVariate "
                    f"model architectures depend on steps.",
                    field = "cv",
                )
            if interval is not None:
                plan = _apply_interval_to_plan(plan, interval)

        if received_plan:
            _check_plan_matches_profile(plan, profile.data_profile)
        # A plan received (saved, or built for other data) is checked
        # against the exogenous columns of this profile, as `plan()` does.
        _check_feature_name_collisions(plan, profile.data_profile)

        return profile, plan

    def _refresh_profile(
        self,
        data: pd.DataFrame,
        profile: ForecastingProfile,
    ) -> ForecastingProfile:
        """
        Profile again the data passed with a saved profile.

        The profile is what the plan, the strategy and the script are built
        on, so it must describe the data that run: daily data run with a
        monthly profile were resampled without an error, and `end_train`,
        `cv_config` and the explanation described the old data. The data
        profile is built with the target, date and series id columns of
        `profile`, and compared with the saved one (`_profile_values`):

        - same structure and values: `profile` is returned unchanged, and the
          warnings of profiling them again are not shown;
        - another structure (`structure_differences`: frequency, series,
          target or exogenous columns): `InvalidInputError`;
        - same structure, other values (new rows, a changed value): the data
          are profiled with `profile()`, whose warnings are shown, and the
          new profile is returned with a note in `DataProfile.warnings`
          naming the fields that changed.

        Parameters
        ----------
        data : pandas DataFrame
            Data the workflow runs on, as read by the caller.
        profile : ForecastingProfile
            Profile passed by the caller.

        Returns
        -------
        profile : ForecastingProfile
            Profile of `data`.
        """

        saved = profile.data_profile
        frame, target = _resolve_data_and_target(
            data, saved.target, saved.date_column
        )
        # Not shown: the caller saw them when the saved profile was built,
        # and `profile()` shows them below when the values differ.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fresh = create_data_profile(
                data             = frame,
                target           = target,
                date_column      = saved.date_column,
                series_id_column = saved.series_id_column,
            )

        differences = structure_differences(saved, fresh)
        if differences:
            raise InvalidInputError(
                f"The data do not have the structure of the profile passed "
                f"({'; '.join(differences)}): profile these data and build "
                f"the plan from that profile.",
                field = "profile",
                hint  = (
                    "Profile these data again and build the plan from that "
                    "profile."
                ),
            )

        saved_values = _profile_values(saved)
        fresh_values = _profile_values(fresh)
        changed = [
            name for name in saved_values
            if saved_values[name] != fresh_values[name]
        ]
        if not changed:
            return profile

        refreshed = self.profile(
            data             = data,
            target           = saved.target,
            date_column      = saved.date_column,
            series_id_column = saved.series_id_column,
        )
        note = (
            f"The data differ in their values from the profile passed "
            f"(changed: {', '.join(changed)}): the profile was computed again "
            f"from these data."
        )
        data_profile = refreshed.data_profile

        return refreshed.model_copy(update={
            "data_profile": data_profile.model_copy(
                update={"warnings": [*data_profile.warnings, note]}
            )
        })

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
