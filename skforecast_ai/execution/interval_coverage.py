################################################################################
#                           Interval coverage                                  #
#                                                                              #
# Coverage and width of the prediction interval measured by the backtesting   #
# of skforecast, read against the nominal coverage of the plan.                #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import math
import warnings
from typing import Any, NamedTuple
import pandas as pd

from ..exceptions import IntervalCoverageWarning


# Columns that the backtesting of skforecast (0.27 or later) appends to the
# metrics, after the requested ones, when the predictions define an interval
# with a lower and an upper bound.
INTERVAL_METRICS = ("coverage", "interval_width")

# Rows of the multi-series metrics that aggregate the series.
_AGGREGATED_ROWS = ("average", "weighted_average", "pooling")

# A series covers "clearly less" than the nominal level when its coverage is
# below the nominal level by more than `COVERAGE_Z` standard errors of a
# binomial proportion with the number of predictions evaluated, and by at
# least `MIN_COVERAGE_SHORTFALL`. The first term keeps the warning from
# firing by chance on a short backtest; the second keeps it from firing on a
# gap too small to change how the interval is read on a long one.
COVERAGE_Z = 2.0
MIN_COVERAGE_SHORTFALL = 0.05

# Series named one by one in the summary and in the warning; the rest are
# counted.
MAX_SUMMARY_SERIES = 10
MAX_WARNING_SERIES = 5


class SeriesCoverage(NamedTuple):
    """
    Coverage and width of the prediction interval of one series.

    Attributes
    ----------
    series : str, None
        Name of the series, None for a single-series backtest.
    coverage : float
        Share of the actual values inside the interval (`coverage` of the
        metrics of skforecast).
    interval_width : float
        Mean of `upper_bound - lower_bound`, in the units of the series
        (`interval_width` of the metrics of skforecast).
    n_predictions : int
        Number of predictions with both bounds, which the coverage is
        measured on.
    """

    series: str | None
    coverage: float
    interval_width: float
    n_predictions: int


def nominal_coverage(interval: list[float]) -> float:
    """
    Nominal coverage of a prediction interval given as `[lower, upper]`
    quantiles.

    Parameters
    ----------
    interval : list of float
        Quantiles of the bounds, as in `ForecastPlan.interval`.

    Returns
    -------
    nominal : float
        `upper - lower`, rounded to 10 decimals so that `[0.1, 0.9]` gives
        exactly 0.8.
    """

    return round(float(interval[1]) - float(interval[0]), 10)


def coverage_threshold(nominal: float, n_predictions: int) -> float:
    """
    Coverage below which an interval covers clearly less than its nominal
    level.

    The threshold is the nominal coverage minus the larger of two binomial
    standard errors, `COVERAGE_Z * sqrt(nominal * (1 - nominal) / n)`, and
    `MIN_COVERAGE_SHORTFALL`.

    Parameters
    ----------
    nominal : float
        Nominal coverage of the interval, between 0 and 1.
    n_predictions : int
        Number of predictions the coverage is measured on.

    Returns
    -------
    threshold : float
        Coverage below which the warning is emitted. Minus infinity when
        there is no prediction.
    """

    if n_predictions <= 0:
        return -math.inf
    standard_error = math.sqrt(nominal * (1 - nominal) / n_predictions)

    return nominal - max(COVERAGE_Z * standard_error, MIN_COVERAGE_SHORTFALL)


def _bound_columns(
    predictions: pd.DataFrame,
    interval: list[float],
) -> tuple[str, str] | None:
    """
    Columns of the lower and upper bound of the predictions, as skforecast
    reads them for the interval metrics: `lower_bound` and `upper_bound`,
    or the quantile columns of the bounds of a foundation model.
    """

    if {"lower_bound", "upper_bound"} <= set(predictions.columns):
        return "lower_bound", "upper_bound"
    lower, upper = (f"q_{bound}" for bound in interval)
    if {lower, upper} <= set(predictions.columns):
        return lower, upper

    return None


def series_coverages(
    metrics: pd.DataFrame | None,
    predictions: pd.DataFrame | None,
    interval: list[float] | None,
) -> list[SeriesCoverage]:
    """
    Coverage and width of the prediction interval of each series of a
    backtest, as the backtesting of skforecast measured them.

    Nothing is computed here but the number of predictions of each series:
    the coverage and the width are the `coverage` and `interval_width`
    columns of the metrics.

    Parameters
    ----------
    metrics : pandas DataFrame, None
        Metrics of the backtest. One row for a single series; one row per
        series in a `levels` column, plus the aggregated rows, for several.
    predictions : pandas DataFrame, None
        Predictions of the backtest, with a `level` column for several
        series.
    interval : list of float, None
        Prediction interval of the plan.

    Returns
    -------
    coverages : list of SeriesCoverage
        One per series, in the order of the metrics. Empty when the backtest
        has no interval or the metrics do not carry its coverage. A series
        whose coverage is missing (no prediction with both bounds) is left
        out.
    """

    if (
        interval is None
        or metrics is None
        or predictions is None
        or not set(INTERVAL_METRICS) <= set(metrics.columns)
    ):
        return []
    bounds = _bound_columns(predictions, interval)
    if bounds is None:
        return []
    with_bounds = predictions[list(bounds)].notna().all(axis=1)

    coverages = []
    if "levels" in metrics.columns:
        counts = (
            predictions.loc[with_bounds, "level"].astype(str).value_counts()
            if "level" in predictions.columns else pd.Series(dtype=int)
        )
        rows = metrics[~metrics["levels"].isin(_AGGREGATED_ROWS)]
        for _, row in rows.iterrows():
            series = str(row["levels"])
            n_predictions = int(counts.get(series, 0))
            if pd.isna(row["coverage"]) or n_predictions == 0:
                continue
            coverages.append(
                SeriesCoverage(
                    series         = series,
                    coverage       = float(row["coverage"]),
                    interval_width = float(row["interval_width"]),
                    n_predictions  = n_predictions,
                )
            )
    else:
        row = metrics.iloc[0]
        n_predictions = int(with_bounds.sum())
        if not pd.isna(row["coverage"]) and n_predictions > 0:
            coverages.append(
                SeriesCoverage(
                    series         = None,
                    coverage       = float(row["coverage"]),
                    interval_width = float(row["interval_width"]),
                    n_predictions  = n_predictions,
                )
            )

    return coverages


def low_coverage_series(
    coverages: list[SeriesCoverage],
    interval: list[float],
) -> list[SeriesCoverage]:
    """
    Series whose interval covers clearly less than its nominal level (see
    `coverage_threshold()`).

    Parameters
    ----------
    coverages : list of SeriesCoverage
        Coverage of each series, from `series_coverages()`.
    interval : list of float
        Prediction interval of the plan.

    Returns
    -------
    low : list of SeriesCoverage
        The series below the threshold, from the lowest coverage to the
        highest (in the order of `coverages` on a tie).
    """

    nominal = nominal_coverage(interval)
    low = [
        coverage for coverage in coverages
        if coverage.coverage < coverage_threshold(nominal, coverage.n_predictions)
    ]

    return sorted(low, key=lambda coverage: coverage.coverage)


def _percent(value: float) -> str:
    """Format a share as a percentage with at most one decimal."""
    text = f"{100 * value:.1f}".removesuffix(".0")
    return f"{text} %"


def interval_label(interval: list[float]) -> str:
    """Name an interval with its quantiles and its nominal coverage."""
    return (
        f"[{interval[0]:g}, {interval[1]:g}] (nominal coverage "
        f"{_percent(nominal_coverage(interval))})"
    )


def describe_interval_coverage(
    metrics: pd.DataFrame | None,
    predictions: pd.DataFrame | None,
    interval: list[float] | None,
) -> str | None:
    """
    Sentence of the summary of a backtest with the measured coverage and
    width of its prediction interval next to the nominal coverage.

    Parameters
    ----------
    metrics : pandas DataFrame, None
        Metrics of the backtest.
    predictions : pandas DataFrame, None
        Predictions of the backtest.
    interval : list of float, None
        Prediction interval of the plan.

    Returns
    -------
    sentence : str, None
        The sentence, by series when there are several (the
        `MAX_SUMMARY_SERIES` with the lowest coverage when there are more),
        with the average across series. None when the backtest has no
        interval or skforecast did not measure it.
    """

    coverages = series_coverages(metrics, predictions, interval)
    if not coverages:
        return None
    label = interval_label(interval)

    if "levels" not in metrics.columns:
        single = coverages[0]
        return (
            f"Prediction interval {label}: {_percent(single.coverage)} of the "
            f"{single.n_predictions} actual values fell inside it "
            f"(coverage: {single.coverage:.4f}), with a mean width of "
            f"{single.interval_width:.4f} in the units of the target "
            f"(interval_width)."
        )

    shown = coverages
    intro = "by series"
    if len(coverages) > MAX_SUMMARY_SERIES:
        shown = sorted(coverages, key=lambda c: c.coverage)[:MAX_SUMMARY_SERIES]
        intro = (
            f"for the {MAX_SUMMARY_SERIES} series with the lowest coverage of "
            f"{len(coverages)}"
        )
    parts = [
        f"'{c.series}' {_percent(c.coverage)} of {c.n_predictions} "
        f"predictions, width {c.interval_width:.4f}"
        for c in shown
    ]
    average = metrics[metrics["levels"] == "average"]
    if len(coverages) > 1 and not average.empty:
        row = average.iloc[0]
        parts.append(
            f"average across series {_percent(row['coverage'])}, width "
            f"{row['interval_width']:.4f}"
        )

    return (
        f"Prediction interval {label}, share of the actual values inside it "
        f"(coverage) and mean width in the units of each series "
        f"(interval_width), {intro}: {'; '.join(parts)}."
    )


def low_coverage_message(
    low: list[SeriesCoverage],
    n_series: int,
    interval: list[float],
) -> str:
    """
    Text of the `IntervalCoverageWarning` of a backtest.

    Parameters
    ----------
    low : list of SeriesCoverage
        Series below the threshold, from `low_coverage_series()`.
    n_series : int
        Number of series whose coverage was measured.
    interval : list of float
        Prediction interval of the plan.

    Returns
    -------
    message : str
        What was measured, the rule and how to read the interval.
    """

    nominal = _percent(nominal_coverage(interval))
    rule = (
        f"more than {COVERAGE_Z:g} binomial standard errors for the number of "
        f"predictions, and at least {100 * MIN_COVERAGE_SHORTFALL:g} "
        f"percentage points, below {nominal}"
    )
    if low[0].series is None:
        single = low[0]
        measured = (
            f"only {_percent(single.coverage)} of the {single.n_predictions} "
            f"actual values of the backtest fell inside it"
        )
        subject = "this interval"
    else:
        named = ", ".join(
            f"'{c.series}' {_percent(c.coverage)} of {c.n_predictions} "
            f"predictions"
            for c in low[:MAX_WARNING_SERIES]
        )
        if len(low) > MAX_WARNING_SERIES:
            named += f" and {len(low) - MAX_WARNING_SERIES} more series"
        measured = (
            f"it covered clearly less in {len(low)} of {n_series} series "
            f"(share of the actual values inside it): {named}"
        )
        subject = "the interval of these series"

    return (
        f"The prediction interval {[*interval]} has a nominal coverage of "
        f"{nominal}, but {measured} ({rule}). Do not present {subject} as "
        f"covering {nominal}: report the coverage measured in the backtest "
        f"(the `coverage` column of the metrics)."
    )


def warn_low_coverage(
    metrics: pd.DataFrame | None,
    predictions: pd.DataFrame | None,
    interval: list[float] | None,
    stacklevel: int = 2,
) -> None:
    """
    Warn when the prediction interval of a backtest covers clearly less
    than its nominal level in any series.

    Parameters
    ----------
    metrics : pandas DataFrame, None
        Metrics of the backtest.
    predictions : pandas DataFrame, None
        Predictions of the backtest.
    interval : list of float, None
        Prediction interval of the plan.
    stacklevel : int, default 2
        Passed to `warnings.warn`, counted from the caller of this function.

    Returns
    -------
    None

    Notes
    -----
    An `IntervalCoverageWarning` is emitted when `low_coverage_series()`
    finds a series below the threshold of `coverage_threshold()`.
    """

    coverages = series_coverages(metrics, predictions, interval)
    low = low_coverage_series(coverages, interval) if coverages else []
    if low:
        warnings.warn(
            low_coverage_message(low, len(coverages), interval),
            IntervalCoverageWarning,
            stacklevel = stacklevel + 1,
        )


def describe_low_coverage_candidates(
    candidates: dict[str, Any],
    interval: list[float] | None,
) -> str | None:
    """
    Text of the `IntervalCoverageWarning` of a comparison, naming the
    candidates whose interval covers clearly less than its nominal level.

    Parameters
    ----------
    candidates : dict
        Mapping of candidate name to its `BacktestResult`, in the order of
        the table.
    interval : list of float, None
        Prediction interval of the comparison.

    Returns
    -------
    message : str, None
        The text, or None when no candidate is below the threshold.
    """

    if interval is None:
        return None
    named = []
    for name, result in candidates.items():
        coverages = series_coverages(
            result.metrics, result.predictions, result.plan.interval
        )
        low = low_coverage_series(coverages, result.plan.interval)
        if not low:
            continue
        if low[0].series is None:
            named.append(
                f"'{name}' ({_percent(low[0].coverage)} of "
                f"{low[0].n_predictions} actual values)"
            )
        else:
            named.append(
                f"'{name}' ({len(low)} of {len(coverages)} series, the lowest "
                f"'{low[0].series}' at {_percent(low[0].coverage)})"
            )
    if not named:
        return None
    nominal = _percent(nominal_coverage(interval))

    return (
        f"The prediction interval {[*interval]} has a nominal coverage of "
        f"{nominal}, but it covered clearly less (more than "
        f"{COVERAGE_Z:g} binomial standard errors for the number of "
        f"predictions, and at least {100 * MIN_COVERAGE_SHORTFALL:g} "
        f"percentage points, below {nominal}) in these candidates: "
        f"{', '.join(named)}. Do not present their interval as covering "
        f"{nominal}: report the coverage measured in the backtest (the "
        f"`coverage` column of the table, and of the metrics of each "
        f"candidate by series)."
    )
