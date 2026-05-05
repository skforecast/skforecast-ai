"""Programmatic execution of forecasting workflows using skforecast APIs."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..schemas import DataProfile, ForecastPlan

ESTIMATOR_MAP: dict[str, tuple[str, str]] = {
    "LGBMRegressor": ("lightgbm", "LGBMRegressor"),
    "Ridge": ("sklearn.linear_model", "Ridge"),
    "XGBRegressor": ("xgboost", "XGBRegressor"),
    "CatBoostRegressor": ("catboost", "CatBoostRegressor"),
    "RandomForestRegressor": ("sklearn.ensemble", "RandomForestRegressor"),
}


def run_forecast(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    exog_future: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Execute a forecasting workflow programmatically.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset with the target series and optional exogenous variables.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Validated forecast plan produced by the recommendation engine.
    exog_future : pandas DataFrame, default None
        Exogenous variables covering the forecast horizon. If None and
        exog is used, the last ``plan.steps`` rows of training exog are
        used as a fallback.

    Returns
    -------
    result : dict
        Dictionary with keys `'metric_value'`, `'metric_name'`,
        `'predictions'`, `'intervals'`, and `'warnings'`.
    """
    dispatch = {
        "single_series": _run_single_series,
        "multi_series": _run_multi_series,
        "statistical": _run_statistical,
        "foundation": _run_foundation,
    }

    runner_fn = dispatch.get(plan.task_type)
    if runner_fn is None:
        supported = list(dispatch.keys())
        raise ValueError(
            f"Unsupported task_type '{plan.task_type}' for execution. "
            f"Supported types: {supported}"
        )

    return runner_fn(data, profile, plan, exog_future=exog_future)


def _resolve_estimator(name: str | None):
    """
    Resolve an estimator name string to an instantiated estimator object.

    Parameters
    ----------
    name : str, None
        Name of the estimator class (e.g. `'LGBMRegressor'`, `'Ridge'`).

    Returns
    -------
    estimator : object
        Instantiated estimator with `random_state=123`.
    """
    if name is None:
        raise ValueError("Estimator name cannot be None for ML-based forecasters.")

    import importlib

    if name not in ESTIMATOR_MAP:
        raise ValueError(
            f"Unknown estimator '{name}'. "
            f"Supported: {list(ESTIMATOR_MAP.keys())}"
        )

    module_path, class_name = ESTIMATOR_MAP[name]
    module = importlib.import_module(module_path)
    estimator_cls = getattr(module, class_name)
    return estimator_cls(random_state=123)


def _prepare_single_series(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> dict[str, Any]:
    """
    Prepare data for single-series forecasting.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Forecast plan.

    Returns
    -------
    prepared : dict
        Dictionary with keys `'y'`, `'exog'`, `'n_train'`.
    """
    df = data.copy()

    if profile.date_column and profile.date_column in df.columns:
        df = df.set_index(profile.date_column)
        df.index = pd.DatetimeIndex(df.index)
    if profile.frequency:
        df = df.asfreq(profile.frequency)

    y = df[profile.target]
    n_train = int(len(y) * 0.8)

    exog = None
    if plan.use_exog and profile.exog_columns:
        exog = df[profile.exog_columns]

    return {"y": y, "exog": exog, "n_train": n_train}


def _run_single_series(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    exog_future: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Execute single-series forecasting with ForecasterRecursive or ForecasterDirect.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Forecast plan.
    exog_future : pandas DataFrame, default None
        Exogenous variables for the forecast horizon.

    Returns
    -------
    result : dict
        Execution results.
    """
    from skforecast.model_selection import TimeSeriesFold, backtesting_forecaster

    prepared = _prepare_single_series(data, profile, plan)
    y = prepared["y"]
    exog = prepared["exog"]
    n_train = prepared["n_train"]

    estimator = _resolve_estimator(plan.estimator)

    if plan.forecaster == "ForecasterDirect":
        from skforecast.direct import ForecasterDirect

        forecaster = ForecasterDirect(
            steps     = plan.steps,
            estimator = estimator,
            lags      = plan.lags,
        )
    else:
        from skforecast.recursive import ForecasterRecursive

        forecaster = ForecasterRecursive(
            estimator = estimator,
            lags      = plan.lags,
        )

    # Fit
    y_train = y.iloc[:n_train]
    exog_train = exog.iloc[:n_train] if exog is not None else None

    fit_kwargs: dict[str, Any] = {"y": y_train}
    if exog_train is not None:
        fit_kwargs["exog"] = exog_train
    if plan.interval_method is not None:
        fit_kwargs["store_in_sample_residuals"] = True
    forecaster.fit(**fit_kwargs)

    # Backtesting
    cv = TimeSeriesFold(
        steps              = plan.steps,
        initial_train_size = n_train,
        refit              = False,
    )

    bt_kwargs: dict[str, Any] = {
        "forecaster": forecaster,
        "y": y,
        "cv": cv,
        "metric": plan.metric,
    }
    if exog is not None:
        bt_kwargs["exog"] = exog
    metric_result, _ = backtesting_forecaster(**bt_kwargs)
    metric_value = float(metric_result.iloc[0, 0])

    # Re-fit for final predictions.
    if exog_future is not None:
        # User provided explicit future exog — fit on ALL data, predict forward.
        final_fit_kwargs: dict[str, Any] = {"y": y, "exog": exog}
        if plan.interval_method is not None:
            final_fit_kwargs["store_in_sample_residuals"] = True
        forecaster.fit(**final_fit_kwargs)

        predict_kwargs: dict[str, Any] = {
            "steps": plan.steps,
            "exog": exog_future,
        }
    elif exog is not None:
        # No explicit future exog — fallback: use last `steps` rows as proxy.
        n_final_train = len(y) - plan.steps
        y_final = y.iloc[:n_final_train]
        exog_final_train = exog.iloc[:n_final_train]
        exog_fallback = exog.iloc[n_final_train : n_final_train + plan.steps]

        final_fit_kwargs = {"y": y_final, "exog": exog_final_train}
        if plan.interval_method is not None:
            final_fit_kwargs["store_in_sample_residuals"] = True
        forecaster.fit(**final_fit_kwargs)

        predict_kwargs = {
            "steps": plan.steps,
            "exog": exog_fallback,
        }
    else:
        final_fit_kwargs = {"y": y}
        if plan.interval_method is not None:
            final_fit_kwargs["store_in_sample_residuals"] = True
        forecaster.fit(**final_fit_kwargs)

        predict_kwargs = {"steps": plan.steps}

    predictions = forecaster.predict(**predict_kwargs)

    # Intervals
    intervals = None
    if plan.interval_method is not None:
        interval_kwargs: dict[str, Any] = {
            "steps": plan.steps,
            "method": plan.interval_method,
            "interval": [10, 90],
        }
        # Use the same exog that was passed to predict()
        predict_exog = predict_kwargs.get("exog")
        if predict_exog is not None:
            interval_kwargs["exog"] = predict_exog
        intervals = forecaster.predict_interval(**interval_kwargs)

    preds = (
        predictions.to_frame()
        if isinstance(predictions, pd.Series)
        else predictions
    )

    return {
        "metric_value": metric_value,
        "metric_name": plan.metric,
        "predictions": preds,
        "intervals": intervals,
        "warnings": [],
    }


def _run_multi_series(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    exog_future: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Execute multi-series forecasting with ForecasterRecursiveMultiSeries.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset in long format.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Forecast plan.
    exog_future : pandas DataFrame, default None
        Exogenous variables for the forecast horizon (not yet supported).

    Returns
    -------
    result : dict
        Execution results.
    """
    from skforecast.model_selection import (
        TimeSeriesFold,
        backtesting_forecaster_multiseries,
    )
    from skforecast.recursive import ForecasterRecursiveMultiSeries

    series_id = profile.series_id_column or "series_id"
    date_col = profile.date_column or "date"

    # Pivot to wide format
    series = data.pivot_table(
        index=date_col, columns=series_id, values=profile.target
    )
    series.index = pd.DatetimeIndex(series.index)
    series.index.name = None
    if profile.frequency:
        series = series.asfreq(profile.frequency)

    n_train = int(len(series) * 0.8)

    estimator = _resolve_estimator(plan.estimator)

    forecaster = ForecasterRecursiveMultiSeries(
        estimator = estimator,
        lags      = plan.lags,
        encoding  = "ordinal",
    )

    # Fit
    fit_kwargs: dict[str, Any] = {"series": series}
    if plan.interval_method is not None:
        fit_kwargs["store_in_sample_residuals"] = True
    forecaster.fit(**fit_kwargs)

    # Backtesting
    cv = TimeSeriesFold(
        steps              = plan.steps,
        initial_train_size = n_train,
        refit              = False,
    )

    metric_result, _ = backtesting_forecaster_multiseries(
        forecaster = forecaster,
        series     = series,
        cv         = cv,
        metric     = plan.metric,
    )
    # Multi-series backtesting returns per-level metrics; use the "average" row
    avg_row = metric_result[metric_result["levels"] == "average"]
    metric_value = float(avg_row[plan.metric].iloc[0])

    # Re-fit on ALL data for final predictions
    forecaster.fit(**fit_kwargs)

    # Predict future steps beyond the end of the series
    predictions = forecaster.predict(steps=plan.steps)

    # Intervals
    intervals = None
    if plan.interval_method is not None:
        intervals = forecaster.predict_interval(
            steps    = plan.steps,
            method   = plan.interval_method,
            interval = [10, 90],
        )

    return {
        "metric_value": metric_value,
        "metric_name": plan.metric,
        "predictions": predictions,
        "intervals": intervals,
        "warnings": [],
    }


def _run_statistical(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    exog_future: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Execute statistical forecasting with ForecasterStats and Arima.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Forecast plan.
    exog_future : pandas DataFrame, default None
        Exogenous variables for the forecast horizon (not yet supported).

    Returns
    -------
    result : dict
        Execution results.
    """
    from skforecast.model_selection import TimeSeriesFold, backtesting_stats
    from skforecast.recursive import ForecasterStats
    from skforecast.stats import Arima

    prepared = _prepare_single_series(data, profile, plan)
    y = prepared["y"]
    n_train = prepared["n_train"]

    forecaster = ForecasterStats(
        estimator = Arima(order=None, seasonal=True),
    )

    # Fit
    y_train = y.iloc[:n_train]
    forecaster.fit(y=y_train)

    # Backtesting
    cv = TimeSeriesFold(
        steps              = plan.steps,
        initial_train_size = n_train,
        refit              = False,
    )

    metric_result, _ = backtesting_stats(
        forecaster = forecaster,
        y          = y,
        cv         = cv,
        metric     = plan.metric,
    )
    metric_value = float(metric_result.iloc[0, 0])

    # Re-fit on ALL data for final predictions
    forecaster.fit(y=y)

    # Predict future steps beyond the end of the series
    predictions = forecaster.predict(steps=plan.steps)

    # Intervals (native)
    intervals = forecaster.predict_interval(
        steps    = plan.steps,
        interval = [10, 90],
    )

    preds = (
        predictions.to_frame()
        if isinstance(predictions, pd.Series)
        else predictions
    )

    return {
        "metric_value": metric_value,
        "metric_name": plan.metric,
        "predictions": preds,
        "intervals": intervals,
        "warnings": [],
    }


def _run_foundation(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
    exog_future: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Execute foundation model forecasting with ForecasterFoundation.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Forecast plan.
    exog_future : pandas DataFrame, default None
        Exogenous variables for the forecast horizon (not yet supported).

    Returns
    -------
    result : dict
        Execution results.
    """
    from skforecast.foundation import ForecasterFoundation, FoundationModel
    from skforecast.model_selection import TimeSeriesFold, backtesting_foundation

    df = data.copy()
    if profile.date_column and profile.date_column in df.columns:
        df = df.set_index(profile.date_column)
        df.index = pd.DatetimeIndex(df.index)
    if profile.frequency:
        df = df.asfreq(profile.frequency)

    y = df[profile.target]
    n_train = int(len(y) * 0.8)

    model = FoundationModel(
        model_id       = "autogluon/chronos-2-small",
        context_length = 2048,
        device_map     = "auto",
    )
    forecaster = ForecasterFoundation(estimator=model)

    # Fit
    forecaster.fit(series=y)

    # Backtesting
    cv = TimeSeriesFold(
        steps              = plan.steps,
        initial_train_size = n_train,
        refit              = False,
    )

    metric_result, _ = backtesting_foundation(
        forecaster = forecaster,
        series     = y,
        cv         = cv,
        metric     = plan.metric,
    )
    metric_value = float(metric_result.iloc[0, 0])

    # Predict
    predictions = forecaster.predict(steps=plan.steps)

    # Quantile predictions (native)
    intervals = forecaster.predict_quantiles(
        steps     = plan.steps,
        quantiles = [0.1, 0.5, 0.9],
    )

    preds = (
        predictions.to_frame()
        if isinstance(predictions, pd.Series)
        else predictions
    )

    return {
        "metric_value": metric_value,
        "metric_name": plan.metric,
        "predictions": preds,
        "intervals": intervals,
        "warnings": [],
    }
