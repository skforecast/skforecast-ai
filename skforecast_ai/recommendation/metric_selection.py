################################################################################
#                       Recommendations: metrics                               #
#                                                                              #
# Deterministic metric selection based on data characteristics and task type   #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from ..schemas import DataProfile


def select_metric(
    data_profile: DataProfile,
) -> tuple[str, str, list[str]]:
    """
    Select the recommended evaluation metric and the set of metrics to
    compute based on data characteristics.

    Decision rules are derived from the metric-selection skill
    (`skforecast_ai/skills/metric-selection/SKILL.md`).

    Parameters
    ----------
    data_profile : DataProfile
        Profiled dataset metadata containing `target_stats`, `n_series`,
        and `target_dtype`.

    Returns
    -------
    metric : str
        Recommended primary metric (string name matching
        sklearn/skforecast conventions).
    explanation : str
        One-sentence justification for the recommendation.
    metrics_to_compute : list of str
        Full list of metrics to evaluate in generated code.

    Notes
    -----
    A categorical `target_dtype` is treated as a classification task and
    returns classification metrics (skill step 4), never regression error
    metrics which are undefined for class labels.
    """

    has_zeros = _target_has_zeros_or_near_zero(data_profile)
    is_multi_series = data_profile.n_series > 1

    if data_profile.target_dtype == "categorical":
        # Classification target: regression error metrics (MAE, MAPE, MASE)
        # are undefined for class labels. Use skill step 4 metrics.
        metric = "balanced_accuracy_score"
        explanation = (
            "Balanced accuracy handles the class imbalance common in "
            "time series classification."
        )
        metrics_to_compute = [
            "balanced_accuracy_score",
            "accuracy_score",
            "f1_score",
        ]
        return metric, explanation, metrics_to_compute

    if is_multi_series:
        metric = "mean_absolute_scaled_error"
        explanation = (
            "MASE is scale-independent, enabling fair comparison "
            "across differently-scaled series."
        )
    else:
        metric = "mean_absolute_error"
        explanation = (
            "MAE is interpretable, robust to outliers, and works at "
            "any scale."
        )

    metrics_to_compute = [
        "mean_absolute_error",
        "mean_squared_error",
        "mean_absolute_scaled_error",
    ]
    if not has_zeros:
        metrics_to_compute.append("mean_absolute_percentage_error")

    return metric, explanation, metrics_to_compute


def _target_has_zeros_or_near_zero(data_profile: DataProfile) -> bool:
    """
    Check whether any target series has a minimum value at or near zero.

    Parameters
    ----------
    data_profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    has_zeros : bool
        True if any series has `min` <= 0.01 in absolute value.
    """

    for stats in data_profile.target_stats.values():
        min_val = stats.get("min")
        if min_val is not None and abs(min_val) <= 0.01:
            return True
    return False
