"""Programmatic execution of forecasting workflows using skforecast APIs.

This module executes the same code that `forecast_code()` produces,
guaranteeing perfect fidelity between the inspectable script and the
actual execution.
"""

from __future__ import annotations
from typing import Any, Callable

import io
import traceback
from contextlib import redirect_stdout

import pandas as pd

from ..exceptions import ForecastExecutionError
from ..rendering._helpers import _METRIC_REGISTRY
from ..schemas import DataProfile, ForecastPlan, RenderedScript

from ..rendering.single_series import render_forecast_single_series
from ..rendering.multi_series import render_forecast_multi_series, render_forecast_multivariate
from ..rendering.statistical import render_forecast_statistical
from ..rendering.foundation import render_forecast_foundation

_RENDER_DISPATCH: dict[str, Callable[[ForecastPlan, DataProfile], RenderedScript]] = {
    "single_series": render_forecast_single_series,
    "multi_series": render_forecast_multi_series,
    "multivariate": render_forecast_multivariate,
    "statistical": render_forecast_statistical,
    "foundation": render_forecast_foundation,
}


def render_script(
    profile: DataProfile,
    plan: ForecastPlan,
) -> RenderedScript:
    """
    Render structured code from a plan and data profile.

    Parameters
    ----------
    profile : DataProfile
        Profile of the input dataset.
    plan : ForecastPlan
        Validated forecast plan.

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
    return render_fn(plan, profile)


def run_forecast(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    exog_future: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Execute a forecasting workflow by running the generated code.

    The code executed is identical to what `forecast_code()` produces
    (minus the CSV loading preamble). This guarantees that the
    `ForecastResult.code` field always reflects exactly what was run.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset with the target series and optional exogenous
        variables.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Validated forecast plan produced by the recommendation engine.
    exog_future : pandas DataFrame, default None
        Exogenous variables covering the forecast horizon. If provided,
        predictions are re-computed using these values after the main
        execution.

    Returns
    -------
    result : dict
        Dictionary with keys `'metrics'`, `'predictions'`,
        `'intervals'`, and `'generated_code'`.
    """
    rendered = render_script(profile, plan)

    # Execute the rendered code with `data` pre-loaded in the namespace
    namespace = _exec_rendered_code(rendered, data)

    # Extract standard results from the executed namespace
    predictions = namespace.get("predictions")
    forecaster = namespace.get("forecaster")

    # Build unified metrics DataFrame
    metrics_df = namespace.get("metrics_df")
    if metrics_df is not None:
        # Multi-series: metrics_df already has dynamic columns
        metrics = metrics_df
    else:
        # Single series: extract scalar variables by metric var name
        target_name = profile.target
        if isinstance(target_name, list):
            target_name = target_name[0]
        row: dict[str, object] = {"series": target_name}
        for m in plan.metrics_to_compute:
            info = _METRIC_REGISTRY.get(m)
            if info is None:
                continue
            row[info["label"]] = namespace.get(info["var"])
        metrics = pd.DataFrame([row])

    # If exog_future is provided, re-predict using the trained forecaster
    if exog_future is not None and forecaster is not None:
        predictions = _repredict_with_exog_future(
            forecaster, plan, exog_future
        )

    # Ensure predictions is a DataFrame
    if isinstance(predictions, pd.Series):
        predictions = predictions.to_frame()

    # Separate interval columns from point predictions
    intervals = None
    if plan.interval_method is not None and predictions is not None:
        intervals = predictions
        if "pred" in predictions.columns:
            predictions = predictions[["pred"]]

    return {
        "metrics": metrics,
        "predictions": predictions,
        "intervals": intervals,
        "generated_code": rendered,
    }


def _exec_rendered_code(
    rendered: RenderedScript,
    data: pd.DataFrame,
) -> dict[str, Any]:
    """
    Execute the rendered code with data injected into the namespace.

    Parameters
    ----------
    rendered : RenderedScript
        Structured rendered code.
    data : pandas DataFrame
        Input dataset to inject as the `data` variable.

    Returns
    -------
    namespace : dict
        Executed namespace containing all variables produced by the code.
    """
    code_to_exec = rendered.executable
    namespace: dict[str, Any] = {"data": data.copy()}

    compiled = compile(code_to_exec, "<forecast>", "exec")

    # Capture stdout (print statements in the generated code)
    stdout_capture = io.StringIO()
    try:
        with redirect_stdout(stdout_capture):
            exec(compiled, namespace)  # noqa: S102
    except Exception as e:
        tb = traceback.format_exc()
        raise ForecastExecutionError(
            original_error=e,
            generated_code=code_to_exec,
            execution_traceback=tb,
        ) from e

    return namespace


def _repredict_with_exog_future(
    forecaster: Any,
    plan: ForecastPlan,
    exog_future: pd.DataFrame,
) -> pd.DataFrame | pd.Series:
    """
    Re-run prediction using user-provided future exogenous variables.

    Parameters
    ----------
    forecaster : object
        Fitted forecaster from the executed namespace.
    plan : ForecastPlan
        Forecast plan.
    exog_future : pandas DataFrame
        Exogenous variables for the forecast horizon.

    Returns
    -------
    predictions : pandas DataFrame, pandas Series
        Re-computed predictions.
    """
    if plan.interval_method is not None:
        if plan.task_type == "foundation":
            quantiles = [0.1, 0.5, 0.9]
            if plan.interval is not None:
                quantiles = [round(v / 100, 2) for v in plan.interval]
                if 0.5 not in quantiles:
                    quantiles = sorted([quantiles[0], 0.5, quantiles[1]])
            return forecaster.predict_quantiles(
                steps=plan.steps, exog=exog_future, quantiles=quantiles
            )
        elif plan.task_type == "statistical":
            return forecaster.predict_interval(
                steps=plan.steps,
                exog=exog_future,
                interval=plan.interval or [10, 90],
            )
        else:
            return forecaster.predict_interval(
                steps=plan.steps,
                exog=exog_future,
                method=plan.interval_method,
                interval=plan.interval or [10, 90],
            )
    else:
        return forecaster.predict(steps=plan.steps, exog=exog_future)
