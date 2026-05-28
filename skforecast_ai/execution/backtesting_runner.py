"""Programmatic execution of backtesting workflows using skforecast APIs.

Unlike `runner.py` which uses exec() on generated code, this module
calls skforecast backtesting functions directly via importlib. The
generated code in `BacktestResult.code` is for reproducibility only.
"""

from __future__ import annotations

import importlib
from typing import Any

import pandas as pd

from ..generation.code_templates import (
    _ESTIMATOR_DEFAULTS,
    _ESTIMATOR_IMPORTS,
    _emit_data_loading,
    _emit_index_setup,
    _emit_preprocessing_steps,
    _emit_transformer_exog,
    _emit_window_features,
    _get_estimator_constructor,
    _get_estimator_import,
    _get_target_str,
    _needs_column_transformer,
)
from ..schemas import DataProfile, ForecastPlan

# Mapping: forecaster class name → (module_path, class_name)
_FORECASTER_MODULES: dict[str, tuple[str, str]] = {
    "ForecasterRecursive": ("skforecast.recursive", "ForecasterRecursive"),
    "ForecasterDirect": ("skforecast.direct", "ForecasterDirect"),
    "ForecasterRecursiveMultiSeries": (
        "skforecast.recursive",
        "ForecasterRecursiveMultiSeries",
    ),
    "ForecasterDirectMultiVariate": (
        "skforecast.direct",
        "ForecasterDirectMultiVariate",
    ),
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
    Execute a backtesting workflow by calling skforecast APIs directly.

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
        Dictionary with keys `'metrics'`, `'predictions'`, `'code'`,
        and `'explanation'`.
    """

    task_type = plan.task_type

    if task_type not in ("single_series", "multi_series"):
        raise NotImplementedError(
            f"Backtesting for task_type '{task_type}' is not yet "
            f"supported. Currently supported: 'single_series', "
            f"'multi_series'."
        )

    # Build forecaster object
    forecaster = _build_forecaster(plan)

    # Prepare data and exog
    y_or_series, exog = _prepare_data(data, profile, plan)

    # Run backtesting
    metrics, predictions = _dispatch_backtesting(
        task_type=task_type,
        forecaster=forecaster,
        y_or_series=y_or_series,
        cv=cv,
        plan=plan,
        exog=exog,
        show_progress=show_progress,
    )

    # Generate reproducible code
    code = _generate_backtesting_code(profile, plan, cv)

    # Build explanation
    explanation = _build_backtest_explanation(
        cv_explanation=cv_explanation,
        metrics=metrics,
    )

    return {
        "metrics": metrics,
        "predictions": predictions,
        "code": code,
        "explanation": explanation,
    }


def _build_forecaster(plan: ForecastPlan) -> Any:
    """
    Instantiate a forecaster object from the plan.

    Parameters
    ----------
    plan : ForecastPlan
        Forecast plan with forecaster and estimator configuration.

    Returns
    -------
    forecaster : object
        Instantiated (unfitted) forecaster.
    """

    # Import and instantiate estimator
    estimator = None
    if plan.estimator is not None:
        import_str = _ESTIMATOR_IMPORTS.get(plan.estimator)
        if import_str is None:
            raise ValueError(
                f"Unknown estimator '{plan.estimator}'. "
                f"Supported: {list(_ESTIMATOR_IMPORTS.keys())}."
            )
        # Parse "from <module> import <class>" to get module path and class
        parts = import_str.split()
        module_path, class_name = parts[1], parts[3]
        mod = importlib.import_module(module_path)
        estimator_cls = getattr(mod, class_name)

        # Merge defaults with user kwargs
        defaults = _ESTIMATOR_DEFAULTS.get(plan.estimator, {})
        merged_kwargs = {**defaults, **(plan.estimator_kwargs or {})}
        estimator = estimator_cls(**merged_kwargs)

    # Import forecaster class
    fc_info = _FORECASTER_MODULES.get(plan.forecaster)
    if fc_info is None:
        raise ValueError(
            f"Unknown forecaster '{plan.forecaster}'. "
            f"Supported: {list(_FORECASTER_MODULES.keys())}."
        )
    fc_module_path, fc_class_name = fc_info
    fc_mod = importlib.import_module(fc_module_path)
    forecaster_cls = getattr(fc_mod, fc_class_name)

    # Build forecaster kwargs
    fc_kwargs: dict[str, Any] = {}
    plan_fc_kwargs = plan.forecaster_kwargs or {}

    if estimator is not None:
        fc_kwargs["estimator"] = estimator

    # Pass through known forecaster kwargs
    for key in (
        "lags", "steps", "encoding", "transformer_y", "transformer_exog",
        "window_features", "categorical_features", "differentiation",
        "dropna_from_series",
    ):
        value = plan_fc_kwargs.get(key)
        if value is not None:
            # Handle transformer_y/transformer_exog as class names
            if key in ("transformer_y",) and isinstance(value, str):
                from sklearn.preprocessing import StandardScaler
                fc_kwargs[key] = StandardScaler()
            elif key == "transformer_exog" and isinstance(value, str):
                # For backtesting, skip transformer_exog (complex setup)
                pass
            elif key == "window_features" and isinstance(value, list):
                # Convert dict representations to RollingFeatures objects
                from skforecast.preprocessing import RollingFeatures
                wf_objects = []
                for wf_dict in value:
                    if isinstance(wf_dict, dict):
                        wf_objects.append(RollingFeatures(
                            stats=wf_dict.get("stats", ["mean"]),
                            window_sizes=wf_dict.get("window_sizes", 7),
                        ))
                    else:
                        wf_objects.append(wf_dict)
                fc_kwargs[key] = wf_objects if len(wf_objects) > 1 else wf_objects[0]
            else:
                fc_kwargs[key] = value

    return forecaster_cls(**fc_kwargs)


def _prepare_data(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> tuple[Any, pd.DataFrame | None]:
    """
    Prepare target series/DataFrame and exogenous variables.

    Sets up DatetimeIndex and frequency on the data before extracting
    target and exogenous columns.

    Returns
    -------
    y_or_series : pandas Series or pandas DataFrame
        Target data in the format expected by the backtesting function.
    exog : pandas DataFrame, None
        Exogenous variables if used, otherwise None.
    """

    df = data.copy()

    # Pivot long-format multi-series to wide before setting index
    if (
        plan.task_type == "multi_series"
        and getattr(profile, "data_format", None) == "long"
        and profile.series_id_column
    ):
        target_col = _get_target_str(profile)
        df = df.pivot(
            index=profile.date_column,
            columns=profile.series_id_column,
            values=target_col,
        )
        df.index = pd.to_datetime(df.index)
        df.columns.name = None
        if profile.frequency and df.index.freq is None:
            df = df.asfreq(profile.frequency)
        df = df.sort_index()

        exog = None
        # Exog not supported for pivoted long format currently
        return df, exog

    # Set up DatetimeIndex if needed
    if profile.date_column and profile.date_column in df.columns:
        df[profile.date_column] = pd.to_datetime(df[profile.date_column])
        df = df.set_index(profile.date_column)
    if profile.frequency and df.index.freq is None:
        df = df.asfreq(profile.frequency)
    df = df.sort_index()

    exog = None
    if plan.use_exog and profile.exog_columns:
        exog = df[profile.exog_columns]

    if plan.task_type == "single_series":
        target = _get_target_str(profile)
        y = df[target]
        return y, exog

    elif plan.task_type == "multi_series":
        # Wide-format multi-series: target is already a list of columns
        if isinstance(profile.target, list):
            series = df[profile.target]
        else:
            series = df[[profile.target]]
        return series, exog


def _dispatch_backtesting(
    task_type: str,
    forecaster: Any,
    y_or_series: Any,
    cv: Any,
    plan: ForecastPlan,
    exog: pd.DataFrame | None,
    show_progress: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Dispatch to the appropriate skforecast backtesting function.

    Returns
    -------
    metrics : pandas DataFrame
        Metric values from backtesting.
    predictions : pandas DataFrame
        Predictions across all folds.
    """

    metric = plan.metrics_to_compute

    common_kwargs: dict[str, Any] = {
        "cv": cv,
        "metric": metric,
        "n_jobs": "auto",
        "verbose": False,
        "show_progress": show_progress,
        "suppress_warnings": True,
    }

    if plan.interval is not None:
        common_kwargs["interval"] = plan.interval

    if task_type == "single_series":
        from skforecast.model_selection import backtesting_forecaster

        metrics, predictions = backtesting_forecaster(
            forecaster=forecaster,
            y=y_or_series,
            exog=exog,
            **common_kwargs,
        )

    elif task_type == "multi_series":
        from skforecast.model_selection import (
            backtesting_forecaster_multiseries,
        )

        metrics, predictions = backtesting_forecaster_multiseries(
            forecaster=forecaster,
            series=y_or_series,
            exog=exog,
            **common_kwargs,
        )

    else:
        # TODO: Implement stats, foundation, multivariate
        raise NotImplementedError(
            f"Backtesting dispatch for '{task_type}' not implemented."
        )

    return metrics, predictions


def _generate_backtesting_code(
    profile: DataProfile,
    plan: ForecastPlan,
    cv: Any,
) -> str:
    """
    Generate a reproducible backtesting script.

    Parameters
    ----------
    profile : DataProfile
        Data profile.
    plan : ForecastPlan
        Forecast plan.
    cv : TimeSeriesFold
        Cross-validation configuration.

    Returns
    -------
    code : str
        Complete runnable Python script.
    """

    lines: list[str] = []
    target = _get_target_str(profile)
    is_multi = plan.task_type == "multi_series"

    # --- Imports ---
    lines.append("import pandas as pd")
    if plan.estimator:
        lines.append(_get_estimator_import(plan.estimator))

    # Derive module from _FORECASTER_MODULES
    fc_info = _FORECASTER_MODULES.get(plan.forecaster)
    fc_module = fc_info[0].split(".")[-1] if fc_info else "recursive"
    lines.append(
        f"from skforecast.{fc_module} import {plan.forecaster}"
    )
    if is_multi:
        lines.append(
            "from skforecast.model_selection import "
            "backtesting_forecaster_multiseries, TimeSeriesFold"
        )
    else:
        lines.append(
            "from skforecast.model_selection import "
            "backtesting_forecaster, TimeSeriesFold"
        )

    fc_kwargs = plan.forecaster_kwargs or {}
    window_features = fc_kwargs.get("window_features")
    categorical_features = fc_kwargs.get("categorical_features")
    transformer_y = fc_kwargs.get("transformer_y")
    transformer_series = fc_kwargs.get("transformer_series")
    transformer_exog = fc_kwargs.get("transformer_exog")

    if window_features:
        lines.append("from skforecast.preprocessing import RollingFeatures")
    if transformer_y or transformer_series or transformer_exog:
        lines.append("from sklearn.preprocessing import StandardScaler")
    if transformer_exog and _needs_column_transformer(profile):
        lines.append("from sklearn.compose import make_column_transformer")

    lines.append("")

    # --- Data loading ---
    _emit_data_loading(lines, profile)
    _emit_index_setup(lines, profile)

    # --- Preprocessing steps ---
    _emit_preprocessing_steps(lines, plan, profile)

    # --- Window features ---
    if window_features and isinstance(window_features, list):
        _emit_window_features(lines, window_features)
        lines.append("")

    # --- Transformer exog ---
    if transformer_exog and plan.use_exog and profile.exog_columns:
        _emit_transformer_exog(lines, transformer_exog, profile)

    # --- Forecaster instantiation ---
    lines.append("# Create forecaster")
    estimator_str = _get_estimator_constructor(
        plan.estimator, plan.estimator_kwargs
    )

    lags = fc_kwargs.get("lags")
    differentiation = fc_kwargs.get("differentiation")
    dropna = fc_kwargs.get("dropna_from_series")

    fc_params_raw: list[tuple[str, str]] = []
    if plan.estimator:
        fc_params_raw.append(("estimator", estimator_str))
    if plan.forecaster in (
        "ForecasterDirect", "ForecasterDirectMultiVariate"
    ):
        fc_params_raw.append(("steps", str(plan.steps)))
    fc_params_raw.append(("lags", str(lags)))
    if is_multi:
        encoding = fc_kwargs.get("encoding", "'ordinal'")
        if isinstance(encoding, str) and not encoding.startswith("'"):
            encoding = f"'{encoding}'"
        fc_params_raw.append(("encoding", encoding))
    if window_features:
        fc_params_raw.append(("window_features", "window_features"))
    if is_multi and transformer_series:
        fc_params_raw.append((
            "transformer_series", f"{transformer_series}()"
        ))
    elif not is_multi and transformer_y:
        fc_params_raw.append(("transformer_y", f"{transformer_y}()"))
    if transformer_exog and plan.use_exog and profile.exog_columns:
        fc_params_raw.append(("transformer_exog", "transformer_exog"))
    if categorical_features is not None:
        fc_params_raw.append((
            "categorical_features", f"'{categorical_features}'"
        ))
    if differentiation is not None:
        fc_params_raw.append(("differentiation", str(differentiation)))
    if dropna is not None:
        fc_params_raw.append(("dropna_from_series", str(dropna)))

    max_name_len = max(len(name) for name, _ in fc_params_raw)
    fc_params = [
        f"    {name:<{max_name_len}} = {value},"
        for name, value in fc_params_raw
    ]

    lines.append(f"forecaster = {plan.forecaster}(")
    lines.extend(fc_params)
    lines.append(")")
    lines.append("")

    # --- TimeSeriesFold ---
    lines.append("# Cross-validation configuration")

    cv_params_raw: list[tuple[str, str]] = []
    cv_params_raw.append(("steps", str(cv.steps)))
    cv_params_raw.append(("initial_train_size", str(cv.initial_train_size)))
    cv_params_raw.append(("refit", str(cv.refit)))
    cv_params_raw.append(("fixed_train_size", str(cv.fixed_train_size)))
    if cv.gap != 0:
        cv_params_raw.append(("gap", str(cv.gap)))
    if cv.fold_stride is not None and cv.fold_stride != cv.steps:
        cv_params_raw.append(("fold_stride", str(cv.fold_stride)))
    if cv.differentiation is not None:
        cv_params_raw.append(("differentiation", str(cv.differentiation)))

    max_cv_len = max(len(name) for name, _ in cv_params_raw)
    lines.append("cv = TimeSeriesFold(")
    for name, value in cv_params_raw:
        lines.append(f"    {name:<{max_cv_len}} = {value},")
    lines.append(")")
    lines.append("")

    # --- Backtesting call ---
    lines.append("# Run backtesting")
    metrics_repr = repr(plan.metrics_to_compute)

    bt_params_raw: list[tuple[str, str]] = []
    if is_multi:
        if isinstance(profile.target, list):
            series_expr = f"data[{repr(profile.target)}]"
        else:
            series_expr = f"data[[{repr(profile.target)}]]"

        bt_params_raw.append(("forecaster", "forecaster"))
        bt_params_raw.append(("series", series_expr))
    else:
        bt_params_raw.append(("forecaster", "forecaster"))
        bt_params_raw.append(("y", f"data[{repr(target)}]"))

    if plan.use_exog and profile.exog_columns:
        bt_params_raw.append(("exog", f"data[{repr(profile.exog_columns)}]"))
    bt_params_raw.append(("cv", "cv"))
    bt_params_raw.append(("metric", metrics_repr))
    if plan.interval is not None:
        bt_params_raw.append(("interval", repr(plan.interval)))
    bt_params_raw.append(("n_jobs", "'auto'"))
    bt_params_raw.append(("verbose", "False"))
    bt_params_raw.append(("show_progress", "True"))
    bt_params_raw.append(("suppress_warnings", "True"))

    max_bt_len = max(len(name) for name, _ in bt_params_raw)
    if is_multi:
        lines.append(
            "metrics, predictions = backtesting_forecaster_multiseries("
        )
    else:
        lines.append("metrics, predictions = backtesting_forecaster(")
    for name, value in bt_params_raw:
        lines.append(f"    {name:<{max_bt_len}} = {value},")
    lines.append(")")
    lines.append("")
    lines.append("print(metrics)")
    lines.append("print(predictions.head())")

    return "\n".join(lines)


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

    # Build metric summary
    summary_parts: list[str] = []
    if metrics is not None and not metrics.empty:
        for col in metrics.columns:
            if col in ("levels", "level"):
                continue
            val = metrics[col].mean()
            if isinstance(val, float):
                summary_parts.append(f"{col}: {val:.4f}")

    if summary_parts:
        metrics_str = ", ".join(summary_parts)
        results_summary = f"Backtesting completed. {metrics_str}."
    else:
        results_summary = "Backtesting completed."

    return f"{cv_explanation} {results_summary}"
