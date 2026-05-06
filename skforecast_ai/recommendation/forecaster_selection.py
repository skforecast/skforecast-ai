"""Two-stage recommendation: ForecasterProfile then ForecastPlan."""

from __future__ import annotations

import pandas as pd

from ..preparation import derive_preprocessing_steps
from ..profiling.analysis import create_analysis_context
from ..schemas import DataProfile, ForecasterProfile, ForecastPlan
from .rules import (
    build_data_requirements,
    build_explanation,
    check_exog_usage,
    select_backtesting,
    select_dropna_from_series,
    select_estimator_and_candidates,
    select_forecaster_and_candidates,
    select_interval_method,
    select_lags,
    select_metric,
    select_task_type_from_forecaster,
)


def _resolve_choice(
    name: str | None,
    candidates: list[str],
    label: str,
) -> str | None:
    """
    Resolve a user-supplied choice against the compatible candidates.

    Parameters
    ----------
    name : str, None
        User-supplied class name. If `None`, the first candidate is used.
    candidates : list
        Ordered list of compatible candidates.
    label : str
        Label used in the error message (e.g. `'Forecaster'`,
        `'Estimator'`).

    Returns
    -------
    resolved : str or None
        The resolved name, or `None` when no candidates exist and no
        explicit name was provided.
    """
    if name is None:
        return candidates[0] if candidates else None

    if not candidates:
        raise ValueError(
            f"{label} '{name}' was provided but no candidates are available "
            f"for this problem."
        )

    if name not in candidates:
        raise ValueError(
            f"{label} '{name}' is not compatible with this profile. "
            f"Available candidates: {candidates}."
        )

    return name


def _build_profile_explanation(
    task_type: str,
    forecaster: str,
    forecaster_candidates: list[str],
    estimator: str | None,
    estimator_candidates: list[str],
    data_profile: DataProfile,
) -> str:
    """
    Build a short explanation of the coarse modeling decisions.

    Parameters
    ----------
    task_type : str
        Selected task type.
    forecaster : str
        Selected forecaster class name.
    forecaster_candidates : list
        Compatible forecaster alternatives.
    estimator : str or None
        Selected estimator name.
    estimator_candidates : list
        Compatible estimator alternatives.
    data_profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    explanation : str
        Multi-sentence explanation of the coarse decisions.
    """
    parts: list[str] = []

    if task_type == "multi_series":
        parts.append(
            f"The dataset contains {data_profile.n_series} series, so a "
            f"multi-series forecaster ({forecaster}) is recommended."
        )
    elif task_type == "multivariate":
        parts.append(
            f"A multivariate forecaster ({forecaster}) is recommended for "
            "predicting the target using multiple correlated series as features."
        )
    elif task_type == "foundation":
        parts.append(
            f"A foundation model ({forecaster}) was selected per user "
            "preference."
        )
    elif task_type == "statistical":
        parts.append(
            f"A statistical model ({forecaster}) was selected per user "
            "preference."
        )
    else:
        parts.append(
            f"A single-series ML forecaster ({forecaster}) is recommended."
        )

    alt_forecasters = [c for c in forecaster_candidates if c != forecaster]
    if alt_forecasters:
        parts.append(f"Alternative forecasters: {alt_forecasters}.")

    if estimator is not None:
        parts.append(f"Estimator: {estimator}.")
        alt_estimators = [c for c in estimator_candidates if c != estimator]
        if alt_estimators:
            parts.append(f"Alternative estimators: {alt_estimators}.")

    return " ".join(parts)
