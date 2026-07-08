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


def render_forecast_script(
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
    exog: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Execute a forecasting workflow by running the generated code.

    The code executed is identical to what `forecast_code()` produces
    (minus the CSV loading preamble). This guarantees that the
    `ForecastResult.code` field always reflects exactly what was run.

    The behavior depends on `plan.end_train`:

    - Evaluation mode (`plan.end_train` is set): the data is split, the
      forecaster is trained on the training portion, the test portion is
      predicted and metrics are computed.
    - Prediction mode (`plan.end_train` is None): the forecaster is
      trained on all the data and forecasts the future. Future exogenous
      variables, when required, are supplied through `exog`.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset with the target series and optional exogenous
        variables.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Validated forecast plan produced by the recommendation engine.
    exog : pandas DataFrame, default None
        Future exogenous variables covering the forecast horizon. Used
        only in prediction mode; injected into the executed code as the
        `exog_future` variable.

    Returns
    -------
    result : dict
        Dictionary with keys `'metrics'`, `'predictions'`, and
        `'rendered_code'`. In prediction mode `'metrics'` is None. When
        prediction intervals are requested, the interval columns are
        included in `'predictions'`.
    """
    rendered = render_forecast_script(profile, plan)

    # The rendered code prepares the future exog exactly like `data`
    # (sort + asfreq, plus `set_index` when a date column is used). When
    # the data uses a date column, `data` is injected with that column
    # present, so the injected future exog must expose the same column for
    # the shared preparation code to run identically. Users typically pass
    # exog pre-indexed by datetime, so move that index back to a named
    # column here.
    if (
        exog is not None
        and profile.date_column
        and profile.date_column not in exog.columns
    ):
        exog = exog.copy()
        exog.index.name = profile.date_column
        exog = exog.reset_index()

    # Execute the rendered code with `data` (and optional future `exog`)
    # pre-loaded in the namespace. The future exog is injected raw; the
    # rendered core code prepares it (same steps as `data`), so that
    # preparation is both shown in `result.code` and actually run.
    namespace = _exec_rendered_code(rendered, data, exog)

    # Extract standard results from the executed namespace
    predictions = namespace.get("predictions")

    evaluate_mode = plan.end_train is not None

    if not evaluate_mode:
        # Prediction mode forecasts the future; there is no ground truth
        # to compare against, so no metrics are produced.
        metrics = None
    else:
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

    # Ensure predictions is a DataFrame
    if isinstance(predictions, pd.Series):
        predictions = predictions.to_frame()

    return {
        "metrics": metrics,
        "predictions": predictions,
        "rendered_code": rendered,
    }


def _exec_rendered_code(
    rendered: RenderedScript,
    data: pd.DataFrame,
    exog: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Execute the rendered code with data injected into the namespace.

    Parameters
    ----------
    rendered : RenderedScript
        Structured rendered code.
    data : pandas DataFrame
        Input dataset to inject as the `data` variable.
    exog : pandas DataFrame, default None
        Future exogenous variables to inject as the `exog_future`
        variable (prediction mode only).

    Returns
    -------
    namespace : dict
        Executed namespace containing all variables produced by the code.
    """
    code_to_exec = rendered.executable
    namespace: dict[str, Any] = {"data": data.copy()}
    if exog is not None:
        namespace["exog_future"] = exog.copy()

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
