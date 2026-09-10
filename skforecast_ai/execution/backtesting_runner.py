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
    render_backtesting_foundation,
    render_backtesting_multi_series,
    render_backtesting_multivariate,
    render_backtesting_single_series,
    render_backtesting_statistical,
)
from ..schemas import DataProfile, ForecastPlan, RenderedScript
from .comparison import aggregate_metrics
from ._exec import exec_rendered

_RENDER_DISPATCH: dict[
    str, Callable[[ForecastPlan, DataProfile, Any], RenderedScript]
] = {
    "single_series": render_backtesting_single_series,
    "multi_series": render_backtesting_multi_series,
    "multivariate": render_backtesting_multivariate,
    "statistical": render_backtesting_statistical,
    "foundation": render_backtesting_foundation,
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
        and `'explanation'`.
    """

    # Render backtesting code
    rendered = render_backtesting_script(profile, plan, cv)

    # Execute the rendered code with `data` pre-loaded in the namespace
    namespace = _exec_rendered_code(rendered, data, show_progress)

    # Extract results from namespace
    metrics = namespace.get("metrics")
    predictions = namespace.get("predictions")

    # Build explanation
    explanation = _build_backtest_explanation(
        cv_explanation=cv_explanation,
        metrics=metrics,
    )

    return {
        "metrics": metrics,
        "predictions": predictions,
        "rendered_code": rendered,
        "explanation": explanation,
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
        raise ValueError(
            f"Unsupported task_type '{plan.task_type}'. "
            f"Supported types: {supported}"
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
    # the user.
    if not show_progress:
        code_to_exec = re.sub(
            r"show_progress\s*=\s*True",
            "show_progress = False",
            code_to_exec,
        )

    return exec_rendered(code_to_exec, {"data": data.copy()}, "<backtesting>")


def _build_backtest_explanation(
    cv_explanation: str,
    metrics: pd.DataFrame,
) -> str:
    """
    Build the full backtesting explanation.

    Concatenates the CV explanation with a post-execution summary.

    Parameters
    ----------
    cv_explanation : str
        Explanation from `create_cv`.
    metrics : pandas DataFrame
        Backtesting metrics result.

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
        if isinstance(value, float)
    ]

    if summary_parts:
        metrics_str = ", ".join(summary_parts)
        multi_series = metrics is not None and "levels" in metrics.columns
        label = "Results (average across series)" if multi_series else "Results"
        return f"{cv_explanation} {label}: {metrics_str}."

    return cv_explanation
