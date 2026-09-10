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
from ..schemas import (
    CANDIDATE_CONFIG_KEYS,
    BacktestResult,
    CandidateConfig,
    ForecastingProfile,
)


def resolve_compare_candidates(
    candidates: list[tuple[str, CandidateConfig]] | None,
    profile: ForecastingProfile,
) -> list[tuple[str, CandidateConfig]]:
    """
    Resolve the candidate configurations for `ForecastingAssistant.compare()`.

    When `candidates` is None, the candidates are derived from
    `profile.forecaster_candidates`, each labelled by its forecaster
    class name. Otherwise the user-supplied `(name, config)` tuples
    are validated. Names must be unique in both cases, since they key
    the `candidates` and `failures` mappings of the result.

    Parameters
    ----------
    candidates : list of tuple of (str, dict), None
        User-supplied configurations, or None to auto-build.
    profile : ForecastingProfile
        Shared profile used to derive the auto candidates.

    Returns
    -------
    resolved : list of tuple of (str, dict)
        Validated `(name, config)` tuples.
    """

    allowed_keys = CANDIDATE_CONFIG_KEYS

    resolved: list[tuple[str, CandidateConfig]] = []
    if candidates is None:
        if not profile.forecaster_candidates:
            raise ValueError(
                "Profile has no forecaster candidates to compare. "
                "Pass an explicit `candidates` list."
            )
        resolved = [
            (fc, {"forecaster": fc})
            for fc in profile.forecaster_candidates
        ]
    else:
        if not candidates:
            raise ValueError("`candidates` must not be an empty list.")

        for entry in candidates:
            if not isinstance(entry, (tuple, list)) or len(entry) != 2:
                raise ValueError(
                    "Each entry in `candidates` must be a (name, config) "
                    f"tuple, got {entry!r}."
                )
            name, config = entry
            if not isinstance(config, dict):
                raise TypeError(
                    f"Configuration for '{name}' must be a dict, got "
                    f"{type(config).__name__}."
                )
            invalid_keys = set(config) - allowed_keys
            if invalid_keys:
                raise ValueError(
                    f"Invalid config keys for '{name}': "
                    f"{sorted(invalid_keys)}. Allowed keys: "
                    f"{sorted(allowed_keys)}."
                )
            resolved.append((str(name), config))

    names = [name for name, _ in resolved]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(
            f"Candidate names must be unique, found duplicates: "
            f"{duplicates}."
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

def compare_sort_key(item: tuple[Any, Any, Any]) -> tuple[bool, float]:
    """
    Sort key placing NaN ranking values last while keeping order.

    Parameters
    ----------
    item : tuple
        A `(name, backtest, ranking_value)` tuple whose third element
        is the ranking value.

    Returns
    -------
    key : tuple of (bool, float)
        `(is_nan, value)` so NaN entries sort last and finite values
        sort ascending.
    """

    value = item[2]
    is_nan = bool(pd.isna(value))
    return (is_nan, 0.0 if is_nan else float(value))

def build_comparison_table(
    rows: list[tuple[dict, float]],
    metric_columns: list[str],
    any_error: bool,
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

    Returns
    -------
    results : pandas DataFrame
        Ranked table sorted best to worst by the ranking value, with a
        leading `'rank'` column.
    """

    results = pd.DataFrame([row for row, _ in rows])
    results["_rank_value"] = [value for _, value in rows]
    results = results.sort_values(
        "_rank_value",
        ascending    = True,
        na_position  = "last",
        kind         = "stable",
    ).reset_index(drop=True)
    results.insert(0, "rank", range(1, len(results) + 1))

    ordered = ["rank", "name", "forecaster", "estimator", *metric_columns]
    if any_error:
        ordered.append("error")
    return results[ordered]

def build_comparison_explanation(
    n_candidates: int,
    ranked: list[tuple[str, BacktestResult, float]],
    ranking_metric: str,
    any_error: bool,
    cv_explanation: str,
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

    Returns
    -------
    explanation : str
        Human-readable summary of the comparison.
    """

    best_name, best_result, best_value = ranked[0]
    label = best_result.plan.forecaster
    if best_result.plan.estimator:
        label += f" / {best_result.plan.estimator}"

    metrics = best_result.metrics
    pooled = (
        metrics is not None
        and "levels" in metrics.columns
        and bool((metrics["levels"] == "average").any())
    )
    metric_desc = ranking_metric
    if pooled:
        metric_desc += " pooled across series"

    noun = "configuration" if n_candidates == 1 else "configurations"
    best_sentence = f"Best: '{best_name}' ({label}) = {best_value:.4f}"
    if len(ranked) > 1:
        # The runner-up is only quoted when its value is usable: the
        # table sorts NaN last, so a non-finite runner-up carries no
        # information about the margin.
        runner_name, _, runner_value = ranked[1]
        if np.isfinite(runner_value):
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
        best_sentence,
    ]
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
