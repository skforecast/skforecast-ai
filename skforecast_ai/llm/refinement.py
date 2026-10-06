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
from ..exceptions import InvalidInputError
from .._constants import DIRECT_FORECASTERS
from ..recommendation.backtesting import (
    _compute_min_train_size,
    build_cv,
    default_initial_train_size,
    derive_cv_defaults,
    first_window_issue,
)
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

def llm_min_train_size(profile: ForecastingProfile, plan: ForecastPlan) -> int:
    """
    Minimum `initial_train_size` given to the LLM that configures a
    strategy.

    It is the minimum the rules reserve for the forecaster (its window plus
    the steps, or twice the steps: `_compute_min_train_size`), lowered to
    the largest size that leaves two folds when the data are short, so the
    minimum never exceeds the maximum the LLM is given. It is never below
    what the forecaster needs to run with two training rows (one more than
    `first_window_issue` asks of a forecaster that is not direct: an
    estimator such as LightGBM does not fit a single row).

    Parameters
    ----------
    profile : ForecastingProfile
        Profiled dataset.
    plan : ForecastPlan
        Forecast plan.

    Returns
    -------
    minimum : int
        Minimum number of observations of the first training window.
    """

    default = default_initial_train_size(profile, plan)
    minimum = _compute_min_train_size(plan)
    max_train_size = default["n_observations"] - 2 * plan.steps
    if max_train_size > 0:
        minimum = min(minimum, max_train_size)
    needed = default["needed"]
    if needed is not None:
        if plan.forecaster not in DIRECT_FORECASTERS:
            needed += 1
        minimum = max(minimum, needed)

    return minimum


def configure_cv_with_llm(
    agent,
    profile: ForecastingProfile,
    plan: ForecastPlan,
    prompt: str,
    explicit: frozenset[str] = frozenset(),
) -> dict:
    """
    Use the LLM to derive CV parameters from a natural-language prompt.

    Every suggestion is built and validated with `build_cv`, the same path
    `create_cv` uses afterwards, so a date-based `initial_train_size` that
    cannot be parsed or located on the dataset index, or a configuration
    with fewer than 2 folds, is retried with the concrete error. So is one
    whose first training window is too short for the forecaster of the
    plan (`first_window_issue`), which skforecast would only reject when
    the plan is backtested, unless the caller passed `initial_train_size`
    explicitly: that value replaces the one of the LLM, so the suggestion
    is not retried (nor its other parameters lost) for a size that never
    runs. Retries up to 2 times on validation failure, then falls back to
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
    explicit : frozenset of str, default frozenset()
        Names of the parameters the caller of `create_cv()` passed, which
        replace the suggestion of the LLM afterwards.

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
    if dp.frequency is not None and dp.span_start_date is not None:
        end_dates = [info.end for info in dp.series_lengths.values() if info.end]
        if end_dates:
            start_date = dp.span_start_date
            end_date = max(end_dates)

    deps = CVDeps(
               n_observations = n_observations,
               frequency      = dp.frequency,
               steps          = plan.steps,
               task_type      = plan.task_type,
               lags           = lags,
               start_date     = start_date,
               end_date       = end_date,
               min_train_size = llm_min_train_size(profile, plan),
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
            cv = build_cv(cv_params=defaults, data_profile=dp)
            # A first window too short for the forecaster is valid for
            # `TimeSeriesFold` and fails when the plan is backtested: it
            # is retried like any other invalid configuration, instead of
            # reaching `create_cv()` as a warning.
            issue = (
                None if "initial_train_size" in explicit
                else first_window_issue(plan, cv, dp)
            )
            if issue is not None:
                raise InvalidInputError(
                    f"{issue}. The minimum viable initial_train_size of "
                    f"the dataset context is {deps.min_train_size} "
                    f"observations: use at least that",
                    field = "initial_train_size",
                )

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
