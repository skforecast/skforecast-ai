################################################################################
#                          Backtesting Runner                                  #
#                                                                              #
# Programmatic execution of backtesting workflows using skforecast APIs        #
# Render the backtesting code as a string and code via exec()                  #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import re
from typing import Any, Callable
import pandas as pd
from skforecast.model_selection import TimeSeriesFold

from ..rendering.backtesting import (
    render_backtesting_baseline,
    render_backtesting_foundation,
    render_backtesting_multi_series,
    render_backtesting_multivariate,
    render_backtesting_single_series,
    render_backtesting_statistical,
)
from .._last_window import describe_left_out_of_folds, series_left_out_of_folds
from ..schemas import DataProfile, ForecastPlan, RenderedScript
from ..exceptions import InvalidInputError
from .comparison import aggregate_metrics
from .interval_coverage import INTERVAL_METRICS, describe_interval_coverage
from ._exec import exec_rendered

_RENDER_DISPATCH: dict[
    str, Callable[[ForecastPlan, DataProfile, Any], RenderedScript]
] = {
    "single_series": render_backtesting_single_series,
    "multi_series": render_backtesting_multi_series,
    "multivariate": render_backtesting_multivariate,
    "statistical": render_backtesting_statistical,
    "foundation": render_backtesting_foundation,
    "baseline": render_backtesting_baseline,
}


def run_backtest(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    cv: Any,
    cv_explanation: str,
    show_progress: bool = True,
) -> dict[str, Any]:
    """
    Execute a backtesting workflow by running the generated code.

    The code executed is identical to what `render_backtesting_script`
    produces (minus the CSV loading preamble). This guarantees that the
    `BacktestResult.code` field always reflects exactly what was run.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset with DatetimeIndex, target, and optional exog.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Validated forecast plan.
    cv : TimeSeriesFold
        Cross-validation fold splitter.
    cv_explanation : str
        Human-readable CV explanation (from `create_cv`).
    show_progress : bool, default True
        Whether to display a progress bar during backtesting.

    Returns
    -------
    result : dict
        Dictionary with keys `'metrics'`, `'predictions'`, `'rendered_code'`,
        `'explanation'` and `'left_out_of_folds'`: the text about the series
        that the backtest did not forecast in some test fold where they have
        a value (see `series_left_out_of_folds`), also at the end of the
        explanation, or None.
    """

    # Render backtesting code
    rendered = render_backtesting_script(profile, plan, cv)

    # Execute the rendered code with `data` pre-loaded in the namespace
    namespace = _exec_rendered_code(rendered, data, show_progress)

    # Extract results from namespace
    metrics = namespace.get("metrics")
    predictions = namespace.get("predictions")

    # The series a fold left out are read from the predictions, which
    # carry the level and the fold of each one: skforecast does not warn
    # about them when the script runs with `suppress_warnings=True`.
    left_out = describe_left_out_of_folds(
        left_out = series_left_out_of_folds(
                       data        = data,
                       profile     = profile,
                       plan        = plan,
                       cv          = cv,
                       predictions = predictions,
                   ),
        plan     = plan,
    )

    # Build explanation
    explanation = _build_backtest_explanation(
        cv_explanation = cv_explanation,
        metrics        = metrics,
        predictions    = predictions,
        interval       = plan.interval,
    )
    if left_out is not None:
        explanation = f"{explanation} {left_out}"

    return {
        "metrics": metrics,
        "predictions": predictions,
        "rendered_code": rendered,
        "explanation": explanation,
        "left_out_of_folds": left_out,
    }


def render_backtesting_script(
    profile: DataProfile,
    plan: ForecastPlan,
    cv: TimeSeriesFold,
) -> RenderedScript:
    """
    Render structured backtesting code from a plan, profile, and CV.

    Parameters
    ----------
    profile : DataProfile
        Profile of the input dataset.
    plan : ForecastPlan
        Validated forecast plan.
    cv : TimeSeriesFold
        Cross-validation fold splitter.

    Returns
    -------
    rendered : RenderedScript
        Structured code split into imports, data_loading, and core
        sections.
    """
    render_fn = _RENDER_DISPATCH.get(plan.task_type)
    if render_fn is None:
        supported = list(_RENDER_DISPATCH.keys())
        raise InvalidInputError(
            f"Unsupported task_type '{plan.task_type}'. "
            f"Supported types: {supported}",
            field = "task_type",
        )
    return render_fn(plan, profile, cv)


def _exec_rendered_code(
    rendered: RenderedScript,
    data: pd.DataFrame,
    show_progress: bool = True,
) -> dict[str, Any]:
    """
    Execute the rendered backtesting code with data injected into the
    namespace.

    Parameters
    ----------
    rendered : RenderedScript
        Structured rendered code.
    data : pandas DataFrame
        Input dataset to inject as the `data` variable.
    show_progress : bool, default True
        Whether to display a progress bar during backtesting.

    Returns
    -------
    namespace : dict
        Executed namespace containing all variables produced by the
        code.
    """
    code_to_exec = rendered.executable

    # The rendered script always shows `show_progress = True`, so the value
    # is patched only in the code that runs, never in the code returned to
    # the user. The pattern is anchored to the keyword line of the
    # backtesting call: a column name written as a string literal in the
    # script (`'show_progress = True'`) is never rewritten.
    if not show_progress:
        code_to_exec = re.sub(
            r"^(\s+show_progress\s*=\s*)True,$",
            r"\g<1>False,",
            code_to_exec,
            flags=re.MULTILINE,
        )

    return exec_rendered(code_to_exec, {"data": data.copy()}, "<backtesting>")


def _build_backtest_explanation(
    cv_explanation: str,
    metrics: pd.DataFrame,
    predictions: pd.DataFrame | None = None,
    interval: list[float] | None = None,
) -> str:
    """
    Build the full backtesting explanation.

    Concatenates the CV explanation with a post-execution summary. With a
    prediction interval, the coverage and the width that skforecast
    measured (`coverage` and `interval_width` of the metrics) are not
    listed with the other metrics: a sentence of their own states them by
    series next to the nominal coverage of the interval.

    Parameters
    ----------
    cv_explanation : str
        Explanation from `create_cv`.
    metrics : pandas DataFrame
        Backtesting metrics result.
    predictions : pandas DataFrame, default None
        Backtesting predictions, which give the number of predictions the
        coverage of each series is measured on.
    interval : list of float, default None
        Prediction interval of the plan.

    Returns
    -------
    explanation : str
        Combined CV + results explanation.
    """

    # One scalar per metric. For multi-series backtests skforecast appends
    # aggregate rows (`average`, `weighted_average`, `pooling`); averaging
    # the whole column would blend them with the per-series rows into a
    # number that matches no row, so the `average` row is used instead.
    summary_parts = [
        f"{name}: {value:.4f}"
        for name, value in aggregate_metrics(metrics).items()
        if isinstance(value, float) and name not in INTERVAL_METRICS
    ]

    explanation = cv_explanation
    if summary_parts:
        metrics_str = ", ".join(summary_parts)
        multi_series = metrics is not None and "levels" in metrics.columns
        label = "Results (average across series)" if multi_series else "Results"
        explanation = f"{cv_explanation} {label}: {metrics_str}."
    coverage = describe_interval_coverage(metrics, predictions, interval)
    if coverage is not None:
        explanation = f"{explanation} {coverage}"

    return explanation
