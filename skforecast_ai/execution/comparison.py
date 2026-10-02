################################################################################
#                              Comparison helpers                              #
#                                                                              #
# Candidate resolution, ranking and explanation for ForecastingAssistant.compare()#
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import Any
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
from .._utils import long_training_message
from ..exceptions import InvalidInputError, InvalidInputTypeError
from ..recommendation import (
    baseline_missing_values_note,
    count_estimator_fits,
    select_baseline_config,
)
from ..schemas import (
    CANDIDATE_CONFIG_KEYS,
    BacktestResult,
    CandidateConfig,
    ForecastingProfile,
)


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
) -> tuple[list[tuple[str, CandidateConfig]], str | None, str | None]:
    """
    Append the `ForecasterEquivalentDate` baseline to the candidates.

    The baseline is a single-series forecaster, so it is only added when
    the candidates score a single series. It is also left out when the
    target has missing values, which it would repeat as missing
    predictions. When the caller already passed a
    `ForecasterEquivalentDate` candidate, that one is the baseline and
    nothing is appended.

    Parameters
    ----------
    candidates : list of tuple of (str, CandidateConfig)
        Resolved candidates, as returned by `resolve_compare_candidates()`.
    profile : ForecastingProfile
        Shared profile used for every candidate.

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
) -> tuple[list[tuple[str, CandidateConfig]], str | None]:
    """
    Leave out the automatic candidates that would fit too many estimators.

    `compare()` without `candidates` chooses the candidates itself, so it
    also keeps their cost bounded: with a strategy that refits in every
    fold, a direct forecaster fits one estimator per step and fold, which
    can take hours. The recommended forecaster is always kept, since the
    comparison exists to measure the alternatives against it.

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

    Returns
    -------
    kept : list of tuple of (str, CandidateConfig)
        Candidates within the budget, in input order.
    note : str, None
        Sentence explaining the exclusion, or None when nothing is left out.
    """

    budget = COMPARE_FIT_BUDGET if budget is None else budget

    kept = []
    costs = []
    for name, config in candidate_configs:
        forecaster = config.get("forecaster") or preferred
        estimator_fits = count_estimator_fits(n_fits, forecaster, steps)
        if forecaster != preferred and estimator_fits > budget:
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
        Name of the baseline candidate. When given, the summary says
        whether the best configuration beats it and by how much.
    baseline_note : str, default None
        Sentence explaining why no baseline was added, appended as is.
    backend_note : str, default None
        Sentence explaining why a foundation candidate was left out,
        appended as is.
    budget_note : str, default None
        Sentence explaining which candidates were left out for exceeding
        the fit budget, appended as is.

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
            if np.isfinite(best_value) and runner_value != 0:
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
        f"{metric_desc}.",
        f"Shared cross-validation strategy: {cv_explanation}",
    ]
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
    parts.append(best_sentence)
    if baseline_name is not None:
        parts.append(_baseline_sentence(ranked, baseline_name, ranking_metric))
    if baseline_note is not None:
        parts.append(baseline_note)
    if backend_note is not None:
        parts.append(backend_note)
    if budget_note is not None:
        parts.append(budget_note)
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
    last and cannot be compared.

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
    if not beating:
        return (
            f"No configuration beats the baseline '{baseline_name}' "
            f"({baseline_value:.4f}): the added complexity is not justified "
            f"on this data."
        )

    # `ranked` is sorted ascending, so the first candidate that beats the
    # baseline is the best one.
    best_name, best_value = beating[0]
    sentence = (
        f"'{best_name}' beats the baseline '{baseline_name}' "
        f"({baseline_value:.4f})"
    )
    if baseline_value != 0:
        improvement = 100 * (baseline_value - best_value) / abs(baseline_value)
        sentence += f" by {improvement:.1f}%"
    sentence += "."

    n_not_beating = len(models) - len(beating)
    if n_not_beating == 1:
        sentence += " 1 configuration does not beat it."
    elif n_not_beating > 1:
        sentence += f" {n_not_beating} configurations do not beat it."
    return sentence
