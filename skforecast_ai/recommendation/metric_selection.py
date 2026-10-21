################################################################################
#                       Recommendations: metrics                               #
#                                                                              #
# Deterministic metric selection based on data characteristics and task type   #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from ..exceptions import InvalidInputError
from ..schemas import DataProfile

# Half width of the band around zero where a target value makes MAPE
# meaningless.
NEAR_ZERO = 0.01

# Series named in the description of the series near zero, as in the other
# messages that name series.
_SHOWN_SERIES = 5

# sklearn computes MSLE on `log1p` of the values and rejects any value at or
# below this one, actual or predicted.
LOG_DOMAIN_FLOOR = -1


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
        One-sentence justification for the recommendation, followed by
        one sentence saying why MAPE is left out when it is.
    metrics_to_compute : list of str
        Full list of metrics to evaluate in generated code: MAE, RMSE (in
        the units of the target, unlike MSE), MASE and MAPE. MAPE is left
        out when the target of any series takes values at or around zero
        (see `series_near_zero`): it divides each error by the actual
        value, so those values make it meaningless.
    """

    near_zero = describe_series_near_zero(data_profile)
    is_multi_series = data_profile.n_series > 1

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
        "root_mean_squared_error",
        "mean_absolute_scaled_error",
    ]
    if near_zero is None:
        metrics_to_compute.append("mean_absolute_percentage_error")
    else:
        explanation += (
            f" MAPE is not computed: it divides each error by the actual "
            f"value, and {near_zero}."
        )

    return metric, explanation, metrics_to_compute


def series_near_zero(data_profile: DataProfile) -> list[str]:
    """
    Series whose target takes values at or around zero: its range reaches
    the band from `-NEAR_ZERO` to `NEAR_ZERO`, so it touches or crosses zero.

    MAPE divides each error by the actual value, so one value near zero is
    enough to make it explode (3e13 on a target from -10 to 10). Looking at
    the minimum alone missed a target with negative values, such as profits,
    temperatures or net flows.

    Parameters
    ----------
    data_profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    series : list of str
        Names of those series, in the order of `target_stats`. Series
        without statistics are left out.
    """

    return [
        series
        for series, stats in data_profile.target_stats.items()
        if stats.get("min") is not None
        and stats.get("max") is not None
        and stats["min"] <= NEAR_ZERO
        and stats["max"] >= -NEAR_ZERO
    ]


def describe_series_near_zero(data_profile: DataProfile) -> str | None:
    """
    Say which series take values at or around zero, with their range, to
    explain why MAPE has no meaning on them.

    Parameters
    ----------
    data_profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    description : str, None
        A clause such as "the target takes values at or around zero (from
        -10 to 10)", or None when no series does.
    """

    found = series_near_zero(data_profile)
    if not found:
        return None

    def _range(series: str) -> str:
        stats = data_profile.target_stats[series]
        return f"{stats['min']:g} to {stats['max']:g}"

    if len(data_profile.target_stats) == 1:
        where = f"(from {_range(found[0])})"
    elif len(found) == 1:
        where = f"in series {found[0]!r} (from {_range(found[0])})"
    else:
        shown = ", ".join(
            f"{series!r}: {_range(series)}" for series in found[:_SHOWN_SERIES]
        )
        if len(found) > _SHOWN_SERIES:
            shown += f" and {len(found) - _SHOWN_SERIES} more series"
        where = f"in {len(found)} series ({shown})"

    return f"the target takes values at or around zero {where}"


def check_metric_domain(metrics: list[str], data_profile: DataProfile) -> None:
    """
    Reject a metric the target of the data cannot take.

    `mean_squared_log_error` takes the logarithm of `1 + value`, so sklearn
    rejects a value at or below -1 and the script failed after training.
    Checked on the range of the target in the profile; a prediction at or
    below -1 on a target above it still fails when the script runs.

    Parameters
    ----------
    metrics : list of str
        Metrics the plan computes.
    data_profile : DataProfile
        Profiled dataset metadata.

    Returns
    -------
    None
    """

    if "mean_squared_log_error" not in metrics:
        return

    below = [
        (series, stats["min"])
        for series, stats in data_profile.target_stats.items()
        if stats.get("min") is not None and stats["min"] <= LOG_DOMAIN_FLOOR
    ]
    if not below:
        return

    if len(data_profile.target_stats) == 1:
        where = f"the target has values down to {below[0][1]:g}"
    else:
        shown = ", ".join(
            f"{series!r} (down to {minimum:g})"
            for series, minimum in below[:_SHOWN_SERIES]
        )
        if len(below) > _SHOWN_SERIES:
            shown += f" and {len(below) - _SHOWN_SERIES} more series"
        where = f"the target has values at or below -1 in {shown}"

    raise InvalidInputError(
        f"`mean_squared_log_error` cannot be computed on this data: it takes "
        f"the logarithm of 1 plus each value, so it needs values above -1, "
        f"and {where}. Use a metric without a logarithm, such as "
        f"`mean_absolute_error` or `root_mean_squared_error`.",
        field = "metric",
    )
