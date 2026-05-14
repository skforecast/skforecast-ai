"""Programmatic execution of forecasting workflows using skforecast APIs.

This module executes the same code that ``generate_code()`` produces,
guaranteeing perfect fidelity between the inspectable script and the
actual execution.
"""

from __future__ import annotations

import io
import traceback
from contextlib import redirect_stdout
from typing import Any

import pandas as pd

from ..exceptions import ForecastExecutionError
from ..generation.code_templates import generate_template
from ..schemas import DataProfile, ForecastPlan, GeneratedCode


def validate_run_inputs(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> list[str]:
    """
    Validate preconditions before executing a forecasting workflow.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Validated forecast plan.

    Returns
    -------
    warnings : list
        List of human-readable warning strings. Empty if all checks pass.
    """
    warnings: list[str] = []

    if plan.steps > profile.n_observations:
        warnings.append(
            f"Forecast horizon ({plan.steps}) exceeds available observations "
            f"({profile.n_observations})."
        )

    if profile.n_observations < 50:
        warnings.append(
            f"Series has only {profile.n_observations} observations. "
            f"Backtesting results may be unreliable with fewer than 50 "
            f"observations."
        )

    test_size = int(profile.n_observations * 0.2)
    if plan.steps > test_size:
        warnings.append(
            f"steps ({plan.steps}) exceeds test set size ({test_size}). "
            f"Backtesting may not produce meaningful results."
        )

    if plan.use_exog and profile.exog_columns:
        missing_cols = [
            col for col in profile.exog_columns if col not in data.columns
        ]
        if missing_cols:
            warnings.append(
                f"Exogenous columns missing from data: {missing_cols}."
            )

    if profile.missing_target or profile.missing_exog:
        total_missing = (
            sum(profile.missing_target.values())
            + sum(profile.missing_exog.values())
        )
        if total_missing > 0:
            cols_with_missing = list(profile.missing_target.keys()) + list(
                profile.missing_exog.keys()
            )
            warnings.append(
                f"Data contains {total_missing} missing value(s) across "
                f"columns: {cols_with_missing}. "
                f"This may cause errors during execution."
            )

    return warnings


def run_forecast(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    exog_future: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Execute a forecasting workflow by running the generated code.

    The code executed is identical to what ``generate_code()`` produces
    (minus the CSV loading preamble). This guarantees that the
    ``RunResult.code`` field always reflects exactly what was run.

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
        Dictionary with keys ``'metrics'``, ``'predictions'``,
        ``'intervals'``, ``'warnings'``, and ``'generated_code'``.
    """
    generated = generate_template(plan, profile)

    # Execute the generated code with `data` pre-loaded in the namespace
    namespace = _exec_generated_code(generated, data)

    # Extract standard results from the executed namespace
    predictions = namespace.get("predictions")
    forecaster = namespace.get("forecaster")

    # Build unified metrics DataFrame
    metrics_df = namespace.get("metrics_df")
    if metrics_df is not None:
        # Multi-series: metrics_df already has columns [series, MAE, MSE, MASE]
        metrics = metrics_df
    else:
        # Single series: scalar variables mae, mse, mase
        mae = namespace.get("mae")
        mse = namespace.get("mse")
        mase = namespace.get("mase")
        target_name = profile.target
        if isinstance(target_name, list):
            target_name = target_name[0]
        metrics = pd.DataFrame([{
            "series": target_name,
            "MAE": mae,
            "MSE": mse,
            "MASE": mase,
        }])

    # Handle interval predictions: if predict_interval or predict_quantiles
    # was used, predictions already contains interval columns
    intervals = None
    if plan.interval_method is not None and predictions is not None:
        intervals = predictions.copy()
        # Extract point predictions only
        if "pred" in predictions.columns:
            predictions = predictions[["pred"]].copy()

    # If exog_future is provided, re-predict using the trained forecaster
    if exog_future is not None and forecaster is not None:
        predictions = _repredict_with_exog_future(
            forecaster, plan, exog_future
        )
        if plan.interval_method is not None:
            intervals = predictions.copy() if isinstance(predictions, pd.DataFrame) else predictions
            if isinstance(predictions, pd.DataFrame) and "pred" in predictions.columns:
                predictions = predictions[["pred"]].copy()

    # Ensure predictions is a DataFrame
    if isinstance(predictions, pd.Series):
        predictions = predictions.to_frame()

    return {
        "metrics": metrics,
        "predictions": predictions,
        "intervals": intervals,
        "generated_code": generated,
    }


def _exec_generated_code(
    generated: GeneratedCode,
    data: pd.DataFrame,
) -> dict[str, Any]:
    """
    Execute the generated code with data injected into the namespace.

    Parameters
    ----------
    generated : GeneratedCode
        Structured generated code.
    data : pandas DataFrame
        Input dataset to inject as the ``data`` variable.

    Returns
    -------
    namespace : dict
        Executed namespace containing all variables produced by the code.
    """
    code_to_exec = generated.executable
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
    predictions : pandas DataFrame or Series
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
