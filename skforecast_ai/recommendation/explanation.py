"""Human-readable explanation builders for forecasting decisions."""

from __future__ import annotations

from ..schemas import DataProfile


def build_plan_explanation(
    forecaster: str,
    estimator: str | None,
    lags: list[int] | None,
    window_features: list[dict] | None,
    interval_method: str | None,
    dropna_from_series: bool | None,
    use_exog: bool,
) -> str:
    """
    Assemble a human-readable explanation of the plan-level decisions.

    Focuses on *what* the plan configures (lags, window features,
    interval method, NaN handling) rather than *why* a forecaster was
    chosen (which belongs in the profile explanation).

    Parameters
    ----------
    forecaster : str
        Selected forecaster class name.
    estimator : str, None
        Selected estimator name.
    lags : list of int, None
        Selected lag indices.
    window_features : list of dict, None
        Window feature configurations.
    interval_method : str, None
        Selected prediction interval method.
    dropna_from_series : bool, None
        NaN handling strategy.
    use_exog : bool
        Whether exogenous variables are included.

    Returns
    -------
    explanation : str
        Multi-sentence explanation of the plan configuration.
    """
    parts = []

    parts.append(f"Plan: {forecaster}")
    if estimator is not None:
        parts[-1] += f" + {estimator}"
    parts[-1] += "."

    if lags is not None:
        parts.append(f"Lags: {lags}.")

    if window_features is not None:
        stats = [wf.get("stats", []) for wf in window_features] if isinstance(window_features, list) else []
        flat_stats = [s for sublist in stats for s in sublist] if stats else []
        if flat_stats:
            parts.append(f"Window features: {flat_stats}.")

    if interval_method is not None:
        parts.append(f"Prediction intervals via {interval_method}.")

    if dropna_from_series is True:
        parts.append("NaN rows will be dropped before fitting.")
    elif dropna_from_series is False:
        parts.append("NaN rows kept (NaN-tolerant estimator).")

    if use_exog:
        parts.append("Exogenous variables included.")

    return " ".join(parts)


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
    forecaster_candidates : list of str
        Compatible forecaster alternatives.
    estimator : str, None
        Selected estimator name.
    estimator_candidates : list of str
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
