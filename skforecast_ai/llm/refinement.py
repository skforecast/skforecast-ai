################################################################################
#                               llm: refinement                                #
#                                                                              #
# LLM-guided plan refinement and cross-validation configuration                #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import warnings
from .._utils import (
    _validate_lags,
    _validate_max_window_size,
    _validate_window_features,
)
from ..recommendation.backtesting import build_cv, derive_cv_defaults
from ..schemas import ForecastingProfile, ForecastPlan
from .runtime import run_agent_sync


def refine_features_with_llm(
    agent,
    profile: ForecastingProfile,
    plan: ForecastPlan,
    prompt: str,
) -> tuple[int | list[int] | None, list[dict] | None, str | None]:
    """
    Use the LLM to suggest lags and window features from domain knowledge.

    Every suggestion goes through the same checks `plan()` applies to
    explicit overrides (`_validate_lags`, `_validate_window_features` and
    the data budget of `_validate_max_window_size`), so a value accepted
    here cannot be rejected downstream. Retries up to 2 times when a
    suggestion fails, feeding the concrete violation back each time. On a
    transient/model failure, or after retries are exhausted, a
    `UserWarning` is emitted and `(None, None, None)` is returned so the
    caller falls back to the deterministic plan.

    Parameters
    ----------
    agent : Agent[PlanRefinementDeps, PlanOverrides]
        Plan refinement agent, see `create_plan_refinement_agent`.
    profile : ForecastingProfile
        The profiled dataset and modeling decisions.
    plan : ForecastPlan
        The current forecasting plan.
    prompt : str
        The user's domain knowledge description.

    Returns
    -------
    lags : int, list of int, None
        The LLM-suggested lags, or None on failure.
    window_features : list of dict, None
        The LLM-suggested window features as plain dicts, or None on
        failure. Each dict contains the keys `'stats'` (a list of
        rolling statistics) and `'window_size'` (a scalar int applied
        to every stat in that same dict), for example `[{'stats':
        ['mean', 'std'], 'window_size': 3}, {'stats': ['mean'],
        'window_size': 24}]`. Allowed stats are `'mean'`, `'std'`,
        `'min'`, `'max'`, `'sum'`, `'median'`, `'ratio_min_max'`,
        `'coef_variation'`, and `'ewm'`.
    reasoning : str, None
        The LLM's explanation on success, or None on failure.
    """
    from .agent import PlanRefinementDeps

    deps = PlanRefinementDeps(
        profile=profile,
        plan=plan,
        prompt=prompt,
    )

    span_index_length = profile.data_profile.span_index_length

    max_retries = 2
    last_error = None

    for attempt in range(1 + max_retries):
        if attempt == 0:
            user_message = prompt
        else:
            # The validation message already states the violated rule with
            # its concrete numbers (span, maximum, offending values).
            user_message = (
                f"{prompt}\n\n"
                f"[RETRY {attempt}/{max_retries}] Your previous "
                f"lags/window_features were rejected: {last_error} "
                f"Fix them and try again."
            )

        # A transient/model failure (network, or malformed structured
        # output after pydantic-ai's own internal retries) is terminal
        # here: a budget hint would not fix it, so it is not retried.
        try:
            result = run_agent_sync(agent, user_message, deps=deps)
        except Exception as exc:
            warnings.warn(
                f"LLM plan refinement failed ({exc}). Returning "
                f"deterministic plan.",
                UserWarning,
                stacklevel=3,
            )
            return None, None, None

        llm_overrides = result.output

        # Materialise the typed WindowFeature models back into plain dicts,
        # the format the deterministic plan pipeline stores and renders.
        window_features = (
            [wf.model_dump() for wf in llm_overrides.window_features]
            if llm_overrides.window_features is not None
            else None
        )

        # Pre-validate with the same checks `plan()` applies to explicit
        # overrides, so a malformed or infeasible suggestion drives a retry
        # with concrete feedback instead of crashing `refine_plan()` (which
        # has no fallback around `plan()`) or silently degrading.
        try:
            _validate_lags(llm_overrides.lags)
            _validate_window_features(window_features)
            _validate_max_window_size(
                lags              = llm_overrides.lags,
                window_features   = window_features,
                span_index_length = span_index_length,
            )
        except ValueError as exc:
            last_error = str(exc)
            if attempt < max_retries:
                continue
            warnings.warn(
                f"LLM plan refinement failed after {1 + max_retries} "
                f"attempts (last error: {last_error}). Returning "
                f"deterministic plan.",
                UserWarning,
                stacklevel=3,
            )
            return None, None, None

        return llm_overrides.lags, window_features, llm_overrides.reasoning

    # Unreachable: the loop above always returns on its last iteration.
    return None, None, None  # pragma: no cover

def configure_cv_with_llm(
    agent,
    profile: ForecastingProfile,
    plan: ForecastPlan,
    prompt: str,
) -> dict:
    """
    Use the LLM to derive CV parameters from a natural-language prompt.

    Every suggestion is built and validated with `build_cv`, the same path
    `create_cv` uses afterwards, so a date-based `initial_train_size` that
    cannot be parsed or located on the dataset index, or a configuration
    with fewer than 2 folds, is retried with the concrete error. Retries up
    to 2 times on validation failure, then falls back to deterministic
    defaults with a warning.

    Parameters
    ----------
    agent : Agent[CVDeps, CVParams]
        CV configuration agent, see `create_cv_agent`.
    profile : ForecastingProfile
        Profiled dataset.
    plan : ForecastPlan
        Forecast plan.
    prompt : str
        User's deployment scenario description.

    Returns
    -------
    defaults : dict
        Resolved CV parameters dict (same format as
        `derive_cv_defaults`).
    """
    from .agent import CVDeps

    lags = plan.forecaster_kwargs.get("lags")
    dp = profile.data_profile
    n_observations = dp.span_index_length

    # Only a datetime index with a known frequency lets `count_cv_folds`
    # locate a date-based initial_train_size, so only then is the date
    # range offered to the model.
    start_date = end_date = None
    if dp.frequency is not None and dp.start_date is not None:
        end_dates = [info.end for info in dp.series_lengths.values() if info.end]
        if end_dates:
            start_date = dp.start_date
            end_date = max(end_dates)

    deps = CVDeps(
               n_observations = n_observations,
               frequency      = dp.frequency,
               steps          = plan.steps,
               task_type      = plan.task_type,
               lags           = lags,
               start_date     = start_date,
               end_date       = end_date,
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

            result = run_agent_sync(agent, user_message, deps=deps)
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

            # Build and validate through the same path create_cv() uses;
            # the splitter itself is rebuilt there from the returned dict.
            build_cv(cv_params=defaults, data_profile=dp)

            return defaults

        except Exception as exc:
            last_error = str(exc)
            if attempt < max_retries:
                continue
            # All retries exhausted, fall back to deterministic
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
