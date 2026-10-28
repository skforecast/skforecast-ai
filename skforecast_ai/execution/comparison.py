################################################################################
#                              Comparison helpers                              #
#                                                                              #
# Candidate resolution, ranking and explanation for ForecastingAssistant.compare()#
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from collections.abc import Callable
from typing import Any, NamedTuple
import numpy as np
import pandas as pd
from .._constants import (
    BASELINE_FORECASTERS,
    COMPARE_FIT_BUDGET,
    DEFAULT_FOUNDATION_MODEL_ID,
    FORECASTER_TASK_TYPES,
    FOUNDATION_FORECASTERS,
)
from .._foundation import foundation_backend_installed, resolve_foundation_model
from .._utils import discarded_plan_edits, long_training_message, plan_override_value
from .._validation import is_symmetric_interval
from ..exceptions import InvalidInputError, InvalidInputTypeError
from .interval_coverage import interval_label
from ..recommendation import (
    baseline_missing_values_note,
    count_estimator_fits,
    count_inference_windows,
    count_trainings,
    select_baseline_config,
)
from ..schemas import (
    CANDIDATE_CONFIG_KEYS,
    BacktestResult,
    CandidateConfig,
    CandidateCost,
    ComparisonCost,
    ForecastingProfile,
    ForecastPlan,
)


# Name of the row that runs the plan a strategy of `create_cv()` was created
# for, when `compare()` without `candidates` adds it to the candidates of the
# profile (see `add_strategy_candidate()`). The automatic candidates are
# named after their forecaster, so the name never collides with them.
STRATEGY_PLAN_NAME = "Strategy plan"


# Forecasters whose backtest metrics measure the same thing can be ranked
# together. Every single-target family scores one series. A multi-series
# forecaster is scored on the average across all the series it predicts.
# A multivariate forecaster predicts one series only (skforecast:
# `ForecasterDirectMultiVariate.level`, "Name of the time series to be
# predicted"), so its metrics describe a different quantity and it is never
# ranked against the other two families. A foundation model forecasts every
# series it receives, so its family follows the data: single-target with one
# series, multi-series (average across series) with several.
_COMPARISON_FAMILY: dict[str, str] = {
    "single_series": "single-target",
    "statistical": "single-target",
    "baseline": "single-target",
    "multi_series": "multi-series",
    "multivariate": "multivariate",
}


def _comparison_family(forecaster: str, n_series: int) -> str | None:
    """
    Family a forecaster's metrics belong to; None for an unknown forecaster.

    Parameters
    ----------
    forecaster : str
        Forecaster class name.
    n_series : int
        Number of series in the data, which decides the family of
        `ForecasterFoundation`.

    Returns
    -------
    family : str, None
        `'single-target'`, `'multi-series'` or `'multivariate'`, or None
        when `forecaster` is not a known forecaster.
    """
    task_type = FORECASTER_TASK_TYPES.get(forecaster)
    if task_type == "foundation":
        return "multi-series" if n_series > 1 else "single-target"
    return _COMPARISON_FAMILY.get(task_type) if task_type else None


def missing_foundation_backend(
    profile: ForecastingProfile,
) -> tuple[frozenset[str], str | None]:
    """
    Find the foundation candidate whose backend is not installed.

    `compare()` without `candidates` includes `ForecasterFoundation` with
    its default model. skforecast-ai does not install that model's backend
    by default, so without this check the candidate would fail on every
    call; it is left out instead, and the note says which package to
    install.

    Parameters
    ----------
    profile : ForecastingProfile
        Profile whose forecaster candidates feed the automatic comparison.

    Returns
    -------
    excluded : frozenset of str
        Forecasters to leave out of the automatic candidates: the
        foundation forecaster when its backend is missing, else empty.
    note : str, None
        Sentence explaining the exclusion, or None when nothing is left out.
    """

    foundation = [
        fc for fc in profile.forecaster_candidates if fc in FOUNDATION_FORECASTERS
    ]
    if not foundation:
        return frozenset(), None
    info = resolve_foundation_model(DEFAULT_FOUNDATION_MODEL_ID)
    if foundation_backend_installed(info):
        return frozenset(), None
    note = (
        f"ForecasterFoundation left out: its default model "
        f"'{info.model_id}' needs the '{info.backend_package}' package, "
        f"which is not installed (pip install skforecast-ai[foundation])."
    )
    return frozenset(foundation), note


def stats_skip_folds_exclusion(
    profile: ForecastingProfile,
    skip_folds: object,
) -> tuple[frozenset[str], str | None]:
    """
    Find the `ForecasterStats` candidate that a strategy with `skip_folds`
    cannot run.

    skforecast refits `ForecasterStats` in every fold and rejects any
    `skip_folds` for it, so `compare()` without `candidates` would run it
    only for it to fail, after counting its cost. It is left out instead,
    and the note says why.

    Parameters
    ----------
    profile : ForecastingProfile
        Profile whose forecaster candidates feed the automatic comparison.
    skip_folds : int, list, None
        `skip_folds` of the shared strategy.

    Returns
    -------
    excluded : frozenset of str
        `ForecasterStats` when the strategy skips folds and the profile
        recommends it as a candidate, else empty.
    note : str, None
        Sentence explaining the exclusion, or None when nothing is left out.
    """

    if skip_folds is None or "ForecasterStats" not in profile.forecaster_candidates:
        return frozenset(), None
    note = (
        f"ForecasterStats left out: the strategy has `skip_folds={skip_folds!r}`, "
        f"which skforecast does not allow for it (it refits ForecasterStats "
        f"in every fold)."
    )
    return frozenset({"ForecasterStats"}), note


def resolve_compare_candidates(
    candidates: list[tuple[str, CandidateConfig]] | None,
    profile: ForecastingProfile,
    exclude: frozenset[str] = frozenset(),
) -> list[tuple[str, CandidateConfig]]:
    """
    Resolve the candidate configurations for `ForecastingAssistant.compare()`.

    When `candidates` is None, the candidates are derived from the
    forecaster candidates of the profile that belong to the same family as
    the recommended forecaster, each labelled by its class name (with
    several series, `ForecasterRecursiveMultiSeries` and
    `ForecasterFoundation`; the multivariate alternative is not
    comparable). When that leaves a single forecaster, its estimator
    candidates are compared instead, labelled
    `'<forecaster>+<estimator>'`. Otherwise the
    user-supplied `(name, config)` tuples are validated: keys, unique
    names, and a single forecaster family, since a multivariate forecaster
    scores one series while a multi-series one scores the average across
    all of them.

    Parameters
    ----------
    candidates : list of tuple of (str, dict), None
        User-supplied configurations, or None to auto-build.
    profile : ForecastingProfile
        Shared profile used to derive the auto candidates.
    exclude : frozenset of str, default frozenset()
        Forecasters left out of the auto candidates, for example the
        foundation forecaster when its backend is not installed (see
        `missing_foundation_backend()`). Ignored for explicit `candidates`.

    Returns
    -------
    resolved : list of tuple of (str, dict)
        Validated `(name, config)` tuples.
    """

    allowed_keys = CANDIDATE_CONFIG_KEYS

    n_series = profile.data_profile.n_series
    resolved: list[tuple[str, CandidateConfig]] = []
    if candidates is None:
        family = _comparison_family(profile.forecaster, n_series)
        forecasters = [
            fc for fc in profile.forecaster_candidates
            if _comparison_family(fc, n_series) == family and fc not in exclude
        ]
        if not forecasters:
            raise InvalidInputError(
                "Profile has no forecaster candidates to compare. "
                "Pass an explicit `candidates` list.",
                field = "candidates",
            )
        if len(forecasters) == 1 and len(profile.estimator_candidates) > 1:
            forecaster = forecasters[0]
            resolved = [
                (f"{forecaster}+{estimator}", {"forecaster": forecaster, "estimator": estimator})
                for estimator in profile.estimator_candidates
            ]
        else:
            resolved = [(fc, {"forecaster": fc}) for fc in forecasters]
    else:
        if not candidates:
            raise InvalidInputError(
                "`candidates` must not be an empty list.",
                field = "candidates",
            )

        for entry in candidates:
            if not isinstance(entry, (tuple, list)) or len(entry) != 2:
                raise InvalidInputError(
                    "Each entry in `candidates` must be a (name, config) "
                    f"tuple, got {entry!r}.",
                    field = "candidates",
                )
            name, config = entry
            if not isinstance(config, dict):
                raise InvalidInputTypeError(
                    f"Configuration for '{name}' must be a dict, got "
                    f"{type(config).__name__}.",
                    field = "candidates",
                )
            if str(name) == STRATEGY_PLAN_NAME:
                # The row of the plan the strategy was created for, which
                # the summary names as that plan.
                raise InvalidInputError(
                    f"The candidate name '{STRATEGY_PLAN_NAME}' is reserved for "
                    f"the plan the strategy was created for. Rename the "
                    f"candidate.",
                    field = "candidates",
                )
            invalid_keys = set(config) - allowed_keys
            if invalid_keys:
                raise InvalidInputError(
                    f"Invalid config keys for '{name}': "
                    f"{sorted(invalid_keys)}. Allowed keys: "
                    f"{sorted(allowed_keys)}.",
                    field = "candidates",
                )
            resolved.append((str(name), config))

    families: dict[str, list[str]] = {}
    for name, config in resolved:
        family = _comparison_family(
            config.get("forecaster") or profile.forecaster, n_series
        )
        if family is not None:
            families.setdefault(family, []).append(name)
    if len(families) > 1:
        listed = "; ".join(f"{family}: {names}" for family, names in families.items())
        raise InvalidInputError(
            f"Candidates mix forecaster families whose metrics are not "
            f"comparable ({listed}). A multivariate forecaster is scored on "
            f"the single series it predicts, a multi-series forecaster on the "
            f"average across all series. Compare each family in its own call.",
            field = "candidates",
        )

    names = [name for name, _ in resolved]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise InvalidInputError(
            f"Candidate names must be unique, found duplicates: "
            f"{duplicates}.",
            field = "candidates",
        )

    return resolved


def strategy_candidate_config(plan: ForecastPlan) -> CandidateConfig:
    """
    Configuration of a candidate whose plan holds the decisions of `plan`.

    The forecaster, the estimator and its keyword arguments, the lags and
    the window features are carried over always; `use_exog`,
    `differentiation`, `calendar_features`, `target_transformer` and
    `dropna_from_series` only when the user chose them
    (`plan.overridden_fields`), so the rules decide them again as they did
    for `plan`. These are the decisions `refine_plan()` carries over to a
    plan of the same forecaster. The interval and the metric are not
    carried over: they are those of the comparison.

    Parameters
    ----------
    plan : ForecastPlan
        Plan to turn into a candidate, usually the plan a strategy of
        `create_cv()` was created for (`CVResult.plan`).

    Returns
    -------
    config : CandidateConfig
        Configuration accepted by `compare()`, without None values.
    """

    config: CandidateConfig = {"forecaster": plan.forecaster}
    if plan.estimator is not None:
        config["estimator"] = plan.estimator
    if plan.estimator_kwargs:
        config["estimator_kwargs"] = dict(plan.estimator_kwargs)
    for name in ("lags", "window_features"):
        value = plan.forecaster_kwargs.get(name)
        if value is not None:
            config[name] = value
    for name in (
        "use_exog",
        "differentiation",
        "calendar_features",
        "target_transformer",
        "dropna_from_series",
    ):
        if name in plan.overridden_fields:
            value = plan_override_value(plan, name)
            if value is not None:
                config[name] = value

    return config


def _same_plan_decisions(first: ForecastPlan, second: ForecastPlan) -> bool:
    """
    Whether two plans make the same decisions, so they render the same
    script: the explanation, the warnings and the marks of who made each
    decision are not compared.
    """

    return (
        not discarded_plan_edits(first, second, set())
        and first.forecaster_kwargs == second.forecaster_kwargs
    )


def add_strategy_candidate(
    candidates: list[tuple[str, CandidateConfig]],
    strategy_plan: ForecastPlan,
    profile: ForecastingProfile,
    build_plan: Callable[[CandidateConfig], ForecastPlan],
) -> tuple[list[tuple[str, CandidateConfig]], str | None, str | None]:
    """
    Add the plan a strategy was created for to the automatic candidates.

    `compare()` without `candidates` compares the configurations the
    profile recommends. When its strategy comes from `create_cv()` for
    another plan (one refined with another estimator or other lags, for
    example), that plan is the one the user means to compare, so it is
    appended as the row `STRATEGY_PLAN_NAME`, with the configuration of
    `strategy_candidate_config()`. When the plan makes the same decisions
    as one of the automatic candidates, nothing is appended and that
    candidate is its row. A plan of another forecaster family is not
    comparable with the candidates, so it is left out, and the note says
    so.

    Parameters
    ----------
    candidates : list of tuple of (str, CandidateConfig)
        Automatic candidates, as returned by `resolve_compare_candidates()`.
    strategy_plan : ForecastPlan
        Plan the strategy was created for (`CVResult.plan`).
    profile : ForecastingProfile
        Shared profile used for every candidate.
    build_plan : Callable
        Function that builds the plan of a candidate configuration as the
        comparison does (same profile, steps, interval and metric). Its
        warnings are the caller's to silence. A configuration it rejects
        is never equal to the plan; the candidate then fails when it runs,
        with its own reason.

    Returns
    -------
    candidates : list of tuple of (str, CandidateConfig)
        Candidates with the plan of the strategy appended last when it is
        none of them.
    strategy_name : str, None
        Name of the row that runs the plan of the strategy: the appended
        `STRATEGY_PLAN_NAME`, or the automatic candidate it matches. None
        when the plan is left out.
    note : str, None
        Sentence explaining why the plan is left out, or which of its
        values its row does not run (edited by hand, which `plan()` does
        not rebuild). None otherwise.
    """

    n_series = profile.data_profile.n_series
    family = _comparison_family(strategy_plan.forecaster, n_series)
    families = {
        _comparison_family(config.get("forecaster") or profile.forecaster, n_series)
        for _, config in candidates
    }
    if family not in families:
        note = (
            f"The plan the strategy was created for "
            f"({strategy_plan.forecaster}) is not in the comparison: its "
            f"metrics are not comparable with those of the candidates the "
            f"profile recommends (a multivariate forecaster is scored on the "
            f"single series it predicts, a multi-series forecaster on the "
            f"average across all series). Backtest it, or compare it with "
            f"`candidates` of its family."
        )
        return candidates, None, note

    config = strategy_candidate_config(strategy_plan)
    try:
        rebuilt = build_plan(config)
    except Exception:
        # It fails again when it runs, and its row records why.
        return [*candidates, (STRATEGY_PLAN_NAME, config)], STRATEGY_PLAN_NAME, None

    # The interval and the metric are the comparison's for every row.
    discarded = discarded_plan_edits(strategy_plan, rebuilt, {"interval", "metric"})
    if discarded:
        note = (
            f"The row '{STRATEGY_PLAN_NAME}' runs the plan the strategy was "
            f"created for as `plan()` rebuilds it, which changes these values "
            f"of that plan: {discarded}. Pass the plan to `backtest()` to "
            f"measure it as it is."
        )
        return [*candidates, (STRATEGY_PLAN_NAME, config)], STRATEGY_PLAN_NAME, note

    for name, candidate_config in candidates:
        try:
            candidate_plan = build_plan(candidate_config)
        except Exception:
            continue
        if _same_plan_decisions(rebuilt, candidate_plan):
            return candidates, name, None

    return [*candidates, (STRATEGY_PLAN_NAME, config)], STRATEGY_PLAN_NAME, None


def match_strategy_plan(
    strategy_plan: ForecastPlan,
    plans: dict[str, ForecastPlan],
    profile: ForecastingProfile,
    build_plan: Callable[[CandidateConfig], ForecastPlan],
) -> tuple[str | None, str | None]:
    """
    Find the explicit candidate of `compare()` that runs the plan a strategy
    was created for.

    Explicit `candidates` are the configurations the user chose, and they
    run as given: the plan of the strategy is not added as one more row.
    When a candidate makes the same decisions as that plan (as
    `add_strategy_candidate()` rebuilds it), the text of the strategy names
    its row; when none does, the note says that the plan was not compared,
    so the summary is not read as its result.

    Parameters
    ----------
    strategy_plan : ForecastPlan
        Plan the strategy was created for (`CVResult.plan`).
    plans : dict
        Plans of the candidates, by name, the baseline left out.
    profile : ForecastingProfile
        Shared profile used for every candidate.
    build_plan : Callable
        Function that builds the plan of a candidate configuration as the
        comparison does (same profile, steps, interval and metric). Its
        warnings are the caller's to silence.

    Returns
    -------
    name : str, None
        Name of the candidate that runs the plan of the strategy, or None.
    note : str, None
        Sentence saying that the plan of the strategy was not compared, when
        no candidate runs it. None otherwise, and when no plan of a
        candidate could be built.
    """

    if not plans:
        # No candidate could be built: nothing was compared at all.
        return None, None
    estimator = f" + {strategy_plan.estimator}" if strategy_plan.estimator else ""
    label = f"{strategy_plan.forecaster}{estimator}"
    n_series = profile.data_profile.n_series
    family = _comparison_family(strategy_plan.forecaster, n_series)
    families = {_comparison_family(plan.forecaster, n_series) for plan in plans.values()}
    if family not in families:
        note = (
            f"The plan the strategy was created for ({label}) was not "
            f"compared: `candidates` runs only the configurations given, and "
            f"its metrics are not comparable with theirs (a multivariate "
            f"forecaster is scored on the single series it predicts, a "
            f"multi-series forecaster on the average across all series). "
            f"Backtest it, or compare it with `candidates` of its family."
        )
        return None, note

    try:
        rebuilt = build_plan(strategy_candidate_config(strategy_plan))
    except Exception:
        rebuilt = None
    if rebuilt is not None:
        for name, plan in plans.items():
            if _same_plan_decisions(rebuilt, plan):
                return name, None

    note = (
        f"The plan the strategy was created for ({label}) makes other "
        f"decisions than every candidate, so it was not compared: "
        f"`candidates` runs only the configurations given. Add it to "
        f"`candidates` with its decisions, or leave `candidates` out to run "
        f"it in the row '{STRATEGY_PLAN_NAME}' next to the configurations the "
        f"profile recommends."
    )
    return None, note


class DefaultCandidates(NamedTuple):
    """
    Candidates that `compare()` without `candidates` runs, before the
    baseline, as returned by `resolve_default_candidates()`.

    Attributes
    ----------
    candidates : list of tuple of (str, CandidateConfig)
        `(name, config)` pairs, in the order they run.
    strategy_name : str, None
        Name of the row that runs the plan the strategy was created for,
        or None when no row runs it.
    backend_note : str, None
        Why a foundation candidate was left out, see
        `missing_foundation_backend()`.
    strategy_note : str, None
        Why the plan of the strategy was left out, or which of its values
        its row does not run, see `add_strategy_candidate()`.
    budget_note : str, None
        Which candidates were left out for exceeding the fit budget, see
        `exclude_costly_candidates()`.
    skip_folds_note : str, None
        Why `ForecasterStats` was left out of a strategy with `skip_folds`,
        see `stats_skip_folds_exclusion()`.
    """

    candidates: list[tuple[str, CandidateConfig]]
    strategy_name: str | None
    backend_note: str | None
    strategy_note: str | None
    budget_note: str | None
    skip_folds_note: str | None = None


def resolve_default_candidates(
    profile: ForecastingProfile,
    strategy_plan: ForecastPlan | None,
    build_plan: Callable[[CandidateConfig], ForecastPlan],
    n_fits: int,
    steps: int,
    n_folds: int,
    skip_folds: object = None,
) -> DefaultCandidates:
    """
    Resolve the candidates of `compare()` without `candidates`.

    The one sequence that decides what such a comparison runs, shared by
    `compare()` and by the cost the MCP server announces in `create_cv`, so
    the two never disagree: the candidates of the profile without a
    foundation model whose backend is not installed (nor `ForecasterStats`
    when the strategy skips folds), the plan of the
    strategy when it is none of them, and without the alternatives above
    the fit budget (the recommended forecaster and the plan of the strategy
    always run). The baseline is added afterwards.

    Parameters
    ----------
    profile : ForecastingProfile
        Shared profile used for every candidate.
    strategy_plan : ForecastPlan, None
        Plan the strategy was created for (`CVResult.plan`), or None when
        the strategy is a `TimeSeriesFold`.
    build_plan : Callable
        Function that builds the plan of a candidate configuration as the
        comparison does, see `add_strategy_candidate()`.
    n_fits : int
        Number of folds in which a forecaster is trained under the shared
        strategy, see `count_cv_fits`.
    steps : int
        Forecast horizon of each fold.
    n_folds : int
        Number of folds of the shared strategy.
    skip_folds : int, list, default None
        `skip_folds` of the shared strategy.

    Returns
    -------
    resolved : DefaultCandidates
        Candidates, the row of the plan of the strategy and the notes of
        what was left out.
    """

    excluded, backend_note = missing_foundation_backend(profile)
    skipped, skip_folds_note = stats_skip_folds_exclusion(profile, skip_folds)
    candidates = resolve_compare_candidates(
                     candidates = None,
                     profile    = profile,
                     exclude    = excluded | skipped,
                 )
    strategy_name = None
    strategy_note = None
    if strategy_plan is not None:
        candidates, strategy_name, strategy_note = add_strategy_candidate(
            candidates    = candidates,
            strategy_plan = strategy_plan,
            profile       = profile,
            build_plan    = build_plan,
        )
    candidates, budget_note = exclude_costly_candidates(
        candidate_configs = candidates,
        preferred         = profile.forecaster,
        n_fits            = n_fits,
        steps             = steps,
        n_folds           = n_folds,
        keep              = frozenset({strategy_name} - {None}),
    )

    return DefaultCandidates(
        candidates      = candidates,
        strategy_name   = strategy_name,
        backend_note    = backend_note,
        strategy_note   = strategy_note,
        budget_note     = budget_note,
        skip_folds_note = skip_folds_note,
    )


def aggregate_metrics(metrics: pd.DataFrame | None) -> dict[str, Any]:
    """
    Reduce a backtest metrics DataFrame to one scalar per metric.

    For single-series tasks the single row is used directly. For
    multi-series tasks the skforecast `'average'` aggregate row is
    used, falling back to the first row when it is absent.

    Parameters
    ----------
    metrics : pandas DataFrame, None
        Backtest metrics returned by skforecast.

    Returns
    -------
    aggregated : dict
        Mapping of metric name to a scalar value.
    """

    if metrics is None or len(metrics) == 0:
        return {}
    if "levels" in metrics.columns:
        average = metrics[metrics["levels"] == "average"]
        row = average.iloc[0] if not average.empty else metrics.iloc[0]
        return {c: row[c] for c in metrics.columns if c != "levels"}
    row = metrics.iloc[0]
    return {c: row[c] for c in metrics.columns}

def add_baseline_candidate(
    candidates: list[tuple[str, CandidateConfig]],
    profile: ForecastingProfile,
    interval: list[float] | None = None,
) -> tuple[list[tuple[str, CandidateConfig]], str | None, str | None]:
    """
    Append the `ForecasterEquivalentDate` baseline to the candidates.

    The baseline is a single-series forecaster, so it is only added when
    the candidates score a single series. It is also left out when the
    target has missing values, which it would repeat as missing
    predictions, and when `interval` is asymmetric, which its conformal
    intervals cannot predict (it would only fail). When the caller already
    passed a `ForecasterEquivalentDate` candidate, that one is the baseline
    and nothing is appended.

    Parameters
    ----------
    candidates : list of tuple of (str, CandidateConfig)
        Resolved candidates, as returned by `resolve_compare_candidates()`.
    profile : ForecastingProfile
        Shared profile used for every candidate.
    interval : list of float, default None
        Prediction interval of the comparison, already validated.

    Returns
    -------
    candidates : list of tuple of (str, CandidateConfig)
        Candidates with the baseline appended last when it applies.
    baseline_name : str, None
        Name of the baseline candidate, or None when there is none.
    note : str, None
        Sentence explaining why no baseline was added, or None.

    Raises
    ------
    ValueError
        If a candidate already uses the name reserved for the baseline.
    """

    for name, config in candidates:
        if config.get("forecaster") in BASELINE_FORECASTERS:
            return candidates, name, None

    # An unknown forecaster has no family; it fails on its own when run,
    # so it says nothing about whether the baseline is comparable.
    n_series = profile.data_profile.n_series
    families = {
        _comparison_family(config.get("forecaster") or profile.forecaster, n_series)
        for _, config in candidates
    } - {None}
    if not families:
        families = {_comparison_family(profile.forecaster, n_series)}
    if families != {"single-target"}:
        note = (
            "No baseline: ForecasterEquivalentDate forecasts a single series, "
            "so it cannot be ranked against multi-series or multivariate "
            "candidates."
        )
        return candidates, None, note

    missing_note = baseline_missing_values_note(profile.data_profile)
    if missing_note is not None:
        note = (
            f"No baseline: {missing_note}. Impute the target to compare "
            f"the candidates against it."
        )
        return candidates, None, note

    if interval is not None and not is_symmetric_interval(interval):
        note = (
            f"No baseline: ForecasterEquivalentDate predicts symmetric "
            f"intervals only (lower + upper = 1), and the interval is "
            f"{interval}. Pass a symmetric interval, such as [0.1, 0.9], to "
            f"compare the candidates against it."
        )
        return candidates, None, note

    forecaster_kwargs, _ = select_baseline_config(profile.data_profile)
    if forecaster_kwargs["offset"] == 1:
        baseline_name = "Baseline (naive)"
    else:
        baseline_name = "Baseline (seasonal naive)"

    if baseline_name in {name for name, _ in candidates}:
        raise InvalidInputError(
            f"The candidate name '{baseline_name}' is reserved for the "
            f"baseline. Rename the candidate or pass `baseline=False`.",
            field = "candidates",
        )

    baseline_config: CandidateConfig = {"forecaster": "ForecasterEquivalentDate"}
    return [*candidates, (baseline_name, baseline_config)], baseline_name, None


def compare_sort_key(
    item: tuple[Any, Any, Any],
    baseline_name: str | None = None,
) -> tuple[bool, float, bool]:
    """
    Sort key placing NaN ranking values last while keeping order.

    On a tie the baseline goes first, so a candidate ranks above the
    baseline only when it beats it.

    Parameters
    ----------
    item : tuple
        A `(name, backtest, ranking_value)` tuple whose third element
        is the ranking value.
    baseline_name : str, default None
        Name of the baseline candidate, if any.

    Returns
    -------
    key : tuple of (bool, float, bool)
        `(is_nan, value, is_not_baseline)` so NaN entries sort last,
        finite values sort ascending, and the baseline wins ties.
    """

    value = item[2]
    is_nan = bool(pd.isna(value))
    return (is_nan, 0.0 if is_nan else float(value), item[0] != baseline_name)

def build_comparison_table(
    rows: list[tuple[dict, float]],
    metric_columns: list[str],
    any_error: bool,
    baseline_name: str | None = None,
) -> pd.DataFrame:
    """
    Assemble and rank the `compare()` results table.

    Parameters
    ----------
    rows : list of tuple of (dict, float)
        Per-candidate `(row, ranking_value)` pairs.
    metric_columns : list of str
        Metric column names, in display order.
    any_error : bool
        Whether at least one candidate failed (controls the `'error'`
        column).
    baseline_name : str, default None
        Name of the baseline candidate. On a tie it ranks above the other
        candidates, as in `compare_sort_key()`.

    Returns
    -------
    results : pandas DataFrame
        Ranked table sorted best to worst by the ranking value, with a
        leading `'rank'` column.
    """

    results = pd.DataFrame([row for row, _ in rows])
    results["_rank_value"] = [value for _, value in rows]
    results["_not_baseline"] = results["name"] != baseline_name
    results = results.sort_values(
        ["_rank_value", "_not_baseline"],
        ascending    = True,
        na_position  = "last",
        kind         = "stable",
    ).reset_index(drop=True)
    results.insert(0, "rank", range(1, len(results) + 1))

    ordered = ["rank", "name", "forecaster", "estimator", *metric_columns]
    if any_error:
        ordered.append("error")
    return results[ordered]

def exclude_costly_candidates(
    candidate_configs: list[tuple[str, CandidateConfig]],
    preferred: str,
    n_fits: int,
    steps: int,
    budget: int | None = None,
    n_folds: int | None = None,
    keep: frozenset[str] = frozenset(),
) -> tuple[list[tuple[str, CandidateConfig]], str | None]:
    """
    Leave out the automatic candidates that would fit too many estimators.

    `compare()` without `candidates` chooses the candidates itself, so it
    also keeps their cost bounded: with a strategy that refits in every
    fold, a direct forecaster fits one estimator per step and fold, which
    can take hours. The recommended forecaster is always kept, since the
    comparison exists to measure the alternatives against it, and so are
    the candidates in `keep` (the plan the strategy was created for).

    Parameters
    ----------
    candidate_configs : list of tuple of (str, CandidateConfig)
        Automatic candidates as `(name, config)` pairs.
    preferred : str
        Recommended forecaster of the profile, never left out.
    n_fits : int
        Number of folds in which a forecaster is trained under the shared
        strategy, see `count_cv_fits`.
    steps : int
        Forecast horizon of each fold.
    budget : int, default None
        Largest number of estimator fits a candidate may cost. None uses
        `COMPARE_FIT_BUDGET`.
    n_folds : int, default None
        Number of folds of the shared strategy. skforecast refits
        `ForecasterStats` in every fold, so its cost is `n_folds` when
        given, see `count_estimator_fits`.
    keep : frozenset of str, default frozenset()
        Names of the candidates never left out, whatever their cost.

    Returns
    -------
    kept : list of tuple of (str, CandidateConfig)
        Candidates within the budget or in `keep`, in input order.
    note : str, None
        Sentence explaining the exclusion, or None when nothing is left out.
    """

    budget = COMPARE_FIT_BUDGET if budget is None else budget

    kept = []
    costs = []
    for name, config in candidate_configs:
        forecaster = config.get("forecaster") or preferred
        estimator_fits = count_estimator_fits(
                             n_fits     = n_fits,
                             forecaster = forecaster,
                             steps      = steps,
                             n_folds    = n_folds,
                         )
        if forecaster != preferred and name not in keep and estimator_fits > budget:
            costs.append(
                f"'{name}': "
                f"{long_training_message(estimator_fits, n_fits, forecaster, steps)}"
            )
        else:
            kept.append((name, config))

    if not costs:
        return kept, None

    note = (
        f"Left out of the automatic candidates because this cross-validation "
        f"strategy exceeds the budget of {budget} estimator fits: "
        f"{'; '.join(costs)}. Pass them in `candidates` to include them."
    )

    return kept, note


def buildable_candidates(
    candidate_configs: list[tuple[str, CandidateConfig]],
    build_plan: Callable[[CandidateConfig], ForecastPlan],
) -> list[tuple[str, CandidateConfig]]:
    """
    Keep the candidates whose plan can be built.

    `compare()` builds the plan of every candidate before any of them runs,
    and one whose plan cannot be built fails there and runs nothing, so it
    is not counted in the cost. This is that filter for a count made
    without `compare()` (the cost the MCP server announces in `create_cv`),
    so the two counts agree.

    Parameters
    ----------
    candidate_configs : list of tuple of (str, CandidateConfig)
        Candidates as `(name, config)` pairs.
    build_plan : Callable
        Function that builds the plan of a candidate configuration as the
        comparison does, see `add_strategy_candidate()`. Its warnings are
        the caller's to silence.

    Returns
    -------
    candidates : list of tuple of (str, CandidateConfig)
        The candidates whose plan can be built, in input order.
    """

    kept = []
    for name, config in candidate_configs:
        try:
            build_plan(config)
        except Exception:
            continue
        kept.append((name, config))

    return kept


def count_comparison_cost(
    candidate_configs: list[tuple[str, CandidateConfig]],
    preferred: str,
    steps: int,
    n_fits: int,
    n_folds: int,
    n_series: int,
) -> ComparisonCost:
    """
    Count the cost of a comparison before it runs.

    The one count of what `compare()` runs on a shared strategy, the
    baseline included, shared by `compare()` (which applies the
    thresholds of an expensive run to its totals) and by the cost the MCP
    server announces in `create_cv` for a `compare` without candidates.
    It comes from the forecaster of each candidate and the strategy, so it
    is the same with automatic and with explicit candidates, and nothing
    runs to get it.

    Parameters
    ----------
    candidate_configs : list of tuple of (str, CandidateConfig)
        Candidates whose plan can be built, as `(name, config)` pairs,
        the baseline included when the comparison runs it, in the order
        they run. A candidate whose plan cannot be built runs nothing, so
        it is left out (see `buildable_candidates()`).
    preferred : str
        Recommended forecaster of the profile, the one of a candidate
        whose config does not name one.
    steps : int
        Forecast horizon of each fold.
    n_fits : int
        Number of folds in which a forecaster is trained under the shared
        strategy, see `count_cv_fits`.
    n_folds : int
        Number of folds of the shared strategy.
    n_series : int
        Number of series of the data.

    Returns
    -------
    cost : ComparisonCost
        Cost of each candidate and the totals.
    """

    candidates = {}
    for name, config in candidate_configs:
        forecaster = config.get("forecaster") or preferred
        candidates[name] = CandidateCost(
            forecaster        = forecaster,
            n_fits            = count_trainings(
                                    n_fits     = n_fits,
                                    forecaster = forecaster,
                                    n_folds    = n_folds,
                                ),
            estimator_fits    = count_estimator_fits(
                                    n_fits     = n_fits,
                                    forecaster = forecaster,
                                    steps      = steps,
                                    n_folds    = n_folds,
                                ),
            inference_windows = count_inference_windows(
                                    n_folds    = n_folds,
                                    n_series   = n_series,
                                    forecaster = forecaster,
                                ),
        )

    return ComparisonCost(n_folds=n_folds, candidates=candidates)


def build_comparison_explanation(
    n_candidates: int,
    ranked: list[tuple[str, BacktestResult, float]],
    ranking_metric: str,
    any_error: bool,
    cv_explanation: str,
    baseline_name: str | None = None,
    baseline_note: str | None = None,
    backend_note: str | None = None,
    budget_note: str | None = None,
    strategy_row: str | None = None,
    strategy_note: str | None = None,
    interval: list[float] | None = None,
    skip_folds_note: str | None = None,
    left_out_note: str | None = None,
) -> str:
    """
    Build the deterministic `compare()` summary explanation.

    Parameters
    ----------
    n_candidates : int
        Total number of candidates evaluated.
    ranked : list of tuple of (str, BacktestResult, float)
        Successful candidates ordered best to worst. Never empty: a
        comparison with no successful candidate raises instead.
    ranking_metric : str
        Metric used to rank the table.
    any_error : bool
        Whether at least one candidate failed.
    cv_explanation : str
        Description of the shared cross-validation strategy.
    baseline_name : str, default None
        Name of the baseline candidate. When given, the summary says how
        many configurations beat it, which ones, and by how much the best
        one does (see `_baseline_sentence()`).
    baseline_note : str, default None
        Sentence explaining why no baseline was added, appended as is.
    backend_note : str, default None
        Sentence explaining why a foundation candidate was left out,
        appended as is.
    budget_note : str, default None
        Sentence explaining which candidates were left out for exceeding
        the fit budget, appended as is.
    strategy_row : str, default None
        Name of the row added to run the plan the strategy was created for
        (`STRATEGY_PLAN_NAME`). When given, the summary says that this row
        is that plan, where it ranks, and that the rows named after a
        forecaster are the configurations the profile recommends.
    strategy_note : str, default None
        Sentence explaining why the plan the strategy was created for is
        not in the comparison, or which of its values its row does not
        run, appended as is.
    interval : list of float, default None
        Prediction interval of the comparison. When given, the summary says
        that the table carries its measured coverage and width next to its
        nominal coverage, and that they do not rank.
    skip_folds_note : str, default None
        Sentence explaining why `ForecasterStats` was left out of a
        strategy with `skip_folds`, appended as is.
    left_out_note : str, default None
        Sentences naming the candidates whose backtest left series out of
        some test folds where they have values, appended as is.

    Returns
    -------
    explanation : str
        Human-readable summary of the comparison.
    """

    best_name, best_result, best_value = ranked[0]
    label = best_result.plan.forecaster
    if best_result.plan.estimator:
        label += f" / {best_result.plan.estimator}"

    # Multi-series candidates are ranked on the skforecast `average` row
    # (arithmetic mean of the per-series values), not on the `pooling` row,
    # so the wording must not say "pooled": the model would repeat it.
    metrics = best_result.metrics
    averaged = (
        metrics is not None
        and "levels" in metrics.columns
        and bool((metrics["levels"] == "average").any())
    )
    metric_desc = ranking_metric
    if averaged:
        metric_desc += " averaged across series"

    noun = "configuration" if n_candidates == 1 else "configurations"
    best_sentence = f"Best: '{best_name}' ({label}) = {best_value:.4f}"
    if len(ranked) > 1:
        # The runner-up is only quoted when its value is usable: the
        # table sorts NaN last, so a non-finite runner-up carries no
        # information about the margin. A baseline runner-up is left to
        # the baseline sentence, which quotes the same margin.
        runner_name, _, runner_value = ranked[1]
        if np.isfinite(runner_value) and runner_name != baseline_name:
            if best_value == runner_value:
                # Two candidates with the same value are a tie: "0.0%
                # ahead" would present the first of them as better.
                best_sentence += (
                    f", tied with '{runner_name}' ({runner_value:.4f})"
                )
            elif np.isfinite(best_value) and runner_value != 0:
                margin = 100 * (runner_value - best_value) / abs(runner_value)
                best_sentence += (
                    f", {margin:.1f}% ahead of '{runner_name}' "
                    f"({runner_value:.4f})"
                )
            else:
                best_sentence += (
                    f", ahead of '{runner_name}' ({runner_value:.4f})"
                )
    best_sentence += "."

    parts = [
        f"Compared {n_candidates} {noun}, ranked ascending by "
        f"{metric_desc}."
    ]
    # The row of the plan the strategy was created for is named here, with
    # its rank, so it is not taken for the row of its forecaster, which runs
    # the plan the profile recommends.
    if strategy_row is not None:
        positions = {name: position for position, (name, _, _) in enumerate(ranked)}
        if strategy_row in positions:
            _, strategy_result, strategy_value = ranked[positions[strategy_row]]
            strategy_label = strategy_result.plan.forecaster
            if strategy_result.plan.estimator:
                strategy_label += f" / {strategy_result.plan.estimator}"
            standing = (
                f"({strategy_label}), ranked {positions[strategy_row] + 1} of "
                f"{n_candidates} ({strategy_value:.4f})"
            )
        else:
            standing = "and failed to run"
        parts.append(
            f"'{strategy_row}' runs the plan the strategy was created for "
            f"{standing}; the rows named after a forecaster run the "
            f"configurations the profile recommends, not that plan."
        )
    parts.append(f"Shared cross-validation strategy: {cv_explanation}")
    # The shared strategy describes trained models; a foundation model is
    # not trained, so its window and refit settings mean nothing for it.
    if any(
        result.plan.forecaster in FOUNDATION_FORECASTERS for _, result, _ in ranked
    ):
        parts.append(
            "ForecasterFoundation is not trained: the window and refit "
            "settings do not apply to it, each fold forecasts from the "
            "observations before it."
        )
    # skforecast refits ForecasterStats in every fold whatever the shared
    # strategy says, so its own trainings are stated.
    stats_results = [
        result for _, result, _ in ranked
        if result.plan.forecaster == "ForecasterStats"
    ]
    if stats_results:
        stats_cv = stats_results[0].cv_config
        window = "fixed" if stats_cv["fixed_train_size"] else "expanding"
        parts.append(
            f"ForecasterStats is refitted in every fold on a {window} window "
            f"({stats_cv['n_fits']} trainings): skforecast requires it for "
            f"ARIMA models."
        )
    parts.append(best_sentence)
    if baseline_name is not None:
        parts.append(_baseline_sentence(ranked, baseline_name, ranking_metric))
    if interval is not None:
        across = " (averaged across series)" if averaged else ""
        parts.append(
            f"The table also gives, for the prediction interval "
            f"{interval_label(interval)}, the share of the actual values "
            f"inside it (coverage) and its mean width in the units of the "
            f"target (interval_width){across}; they do not change the "
            f"ranking."
        )
    if baseline_note is not None:
        parts.append(baseline_note)
    if strategy_note is not None:
        parts.append(strategy_note)
    if backend_note is not None:
        parts.append(backend_note)
    if skip_folds_note is not None:
        parts.append(skip_folds_note)
    if budget_note is not None:
        parts.append(budget_note)
    if left_out_note is not None:
        parts.append(left_out_note)
    if any_error:
        n_failed = n_candidates - len(ranked)
        if n_failed == 1:
            parts.append("1 configuration failed to run and is ranked last.")
        else:
            parts.append(
                f"{n_failed} configurations failed to run and are ranked "
                f"last."
            )
    return " ".join(parts)


def _baseline_sentence(
    ranked: list[tuple[str, BacktestResult, float]],
    baseline_name: str,
    ranking_metric: str,
) -> str:
    """
    Describe how the ranked candidates compare with the baseline.

    A candidate beats the baseline only when its ranking value is finite
    and strictly lower, which is when it ranks above it (the baseline wins
    ties, see `compare_sort_key()`). A non-finite baseline value ranks
    last and cannot be compared. With more than one configuration, the
    sentence states how many of them beat the baseline and names the
    shorter list (those that beat it, or those that do not), so the best
    one is never read as the only one.

    Parameters
    ----------
    ranked : list of tuple of (str, BacktestResult, float)
        Successful candidates ordered best to worst.
    baseline_name : str
        Name of the baseline candidate.
    ranking_metric : str
        Name of the metric used to rank the candidates.

    Returns
    -------
    sentence : str
        One or two sentences comparing the candidates with the baseline.
    """

    values = {name: value for name, _, value in ranked}
    if baseline_name not in values:
        return (
            f"The baseline '{baseline_name}' failed to run, so the "
            f"candidates cannot be checked against it."
        )

    models = [(name, value) for name, value in values.items() if name != baseline_name]
    if not models:
        return f"Only the baseline '{baseline_name}' ran successfully."

    baseline_value = values[baseline_name]
    if not np.isfinite(baseline_value):
        return (
            f"The baseline '{baseline_name}' has no finite {ranking_metric}, "
            f"so the candidates cannot be checked against it."
        )

    beating = [
        (name, value)
        for name, value in models
        if np.isfinite(value) and value < baseline_value
    ]
    reference = f"the baseline '{baseline_name}' ({baseline_value:.4f})"
    if not beating:
        return (
            f"No configuration beats {reference}: the added complexity is not "
            f"justified on this data."
        )

    # `ranked` is sorted ascending, so the first candidate that beats the
    # baseline is the best one.
    best_name, best_value = beating[0]
    margin = ""
    if baseline_value != 0:
        improvement = 100 * (baseline_value - best_value) / abs(baseline_value)
        margin = f" by {improvement:.1f}%"
    if len(models) == 1:
        return f"'{best_name}' beats {reference}{margin}."

    # The count of those that beat it is always stated, so the best one is
    # not read as the only one. The shorter list is named: those that beat
    # it, or those that do not.
    beating_names = [name for name, _ in beating]
    others = [name for name, _ in models if name not in beating_names]
    if len(beating) == len(models):
        every = "Both" if len(models) == 2 else f"All {len(models)}"
        sentence = f"{every} configurations beat {reference}."
    else:
        verb = "beats" if len(beating) == 1 else "beat"
        sentence = f"{len(beating)} of {len(models)} configurations {verb} {reference}"
        if len(beating) <= len(others):
            sentence += f": {_quoted_list(beating_names)}."
        else:
            verb = "does" if len(others) == 1 else "do"
            sentence += f"; {_quoted_list(others)} {verb} not."
    if len(beating) > 1:
        sentence += f" The best, '{best_name}', beats it{margin}."
    elif margin:
        # One beats it, and the sentence ends with its name.
        sentence = f"{sentence[:-1]},{margin}."
    return sentence


def _quoted_list(names: list[str]) -> str:
    """Quote candidate names and join them as an English list."""
    quoted = [f"'{name}'" for name in names]
    if len(quoted) <= 2:
        return " and ".join(quoted)

    return ", ".join(quoted[:-1]) + f" and {quoted[-1]}"
