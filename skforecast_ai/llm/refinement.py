################################################################################
#                               llm: refinement                                #
#                                                                              #
# LLM-guided plan refinement and cross-validation configuration                #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import warnings
from skforecast.model_selection import TimeSeriesFold
from .._constants import MAX_FEATURE_FRACTION
from .._utils import _max_window_size
from ..recommendation.backtesting import count_cv_folds, derive_cv_defaults
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

    Retries up to 2 times when the suggested lags/window_features exceed
    the data budget enforced by `plan()`, feeding the concrete violation
    back each time. On a transient/model failure, or after retries are
    exhausted, a `UserWarning` is emitted and `(None, None, None)` is
    returned so the caller falls back to the deterministic plan.

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
    max_allowed = int(span_index_length * MAX_FEATURE_FRACTION)

    max_retries = 2
    last_error = None

    for attempt in range(1 + max_retries):
        if attempt == 0:
            user_message = prompt
        else:
            user_message = (
                f"{prompt}\n\n"
                f"[RETRY {attempt}/{max_retries}] Your previous "
                f"lags/window_features were infeasible: {last_error} "
                f"The dataset has {span_index_length} observations, so "
                f"the largest lag or window size must not exceed "
                f"{max_allowed} ({int(MAX_FEATURE_FRACTION * 100)}%). "
                f"Shrink the largest value and try again."
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

        # Pre-validate against the same data budget `plan()` enforces, so
        # an infeasible suggestion drives a retry with concrete feedback
        # instead of silently falling back to the deterministic plan.
        max_span = _max_window_size(llm_overrides.lags, window_features)
        if max_span > max_allowed:
            last_error = (
                f"lags/window_features span up to {max_span} "
                f"observations, exceeding the maximum of {max_allowed}."
            )
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
    n_observations: int,
) -> dict:
    """
    Use the LLM to derive CV parameters from a natural-language prompt.

    Retries up to 2 times on validation failure, then falls back to
    deterministic defaults with a warning.

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
    n_observations : int
        Total number of observations.

    Returns
    -------
    defaults : dict
        Resolved CV parameters dict (same format as
        `derive_cv_defaults`).
    """
    from .agent import CVDeps

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

            # Validate: check that we can produce ≥2 folds
            _validate_cv_defaults(defaults, n_observations)

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

    n_folds = count_cv_folds(cv=cv, n_observations=n_observations)
    if n_folds < 2:
        raise ValueError(
            f"Configuration produces only {n_folds} fold(s). "
            f"At least 2 required. Parameters: {defaults}."
        )
