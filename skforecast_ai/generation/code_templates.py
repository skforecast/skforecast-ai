"""Code generation templates for skforecast workflows."""

from ..schemas import DataProfile, ForecastPlan  # noqa: I001


ESTIMATOR_IMPORTS: dict[str, str] = {
    "LGBMRegressor": "from lightgbm import LGBMRegressor",
    "Ridge": "from sklearn.linear_model import Ridge",
    "XGBRegressor": "from xgboost import XGBRegressor",
    "CatBoostRegressor": "from catboost import CatBoostRegressor",
    "RandomForestRegressor": "from sklearn.ensemble import RandomForestRegressor",
}


def generate_code(
    plan: ForecastPlan,
    profile: DataProfile,
    data_path: str = "data.csv",
) -> str:
    """
    Generate a complete Python script from a forecast plan and data profile.

    Parameters
    ----------
    plan : ForecastPlan
        Validated forecast plan produced by the recommendation engine.
    profile : DataProfile
        Profiled dataset metadata.
    data_path : str, default 'data.csv'
        Path to the CSV file to embed in the generated script.

    Returns
    -------
    code : str
        Syntactically valid Python code implementing the forecasting workflow.
    """
    dispatch = {
        "single_series": _template_single_series,
        "multi_series": _template_multi_series,
        "statistical": _template_statistical,
        "foundation": _template_foundation,
    }

    template_fn = dispatch.get(plan.task_type)
    if template_fn is None:
        supported = list(dispatch.keys())
        raise ValueError(
            f"Unsupported task_type '{plan.task_type}'. "
            f"Supported types: {supported}"
        )

    return template_fn(plan, profile, data_path)


def _template_single_series(
    plan: ForecastPlan,
    profile: DataProfile,
    data_path: str,
) -> str:
    """Generate code for ForecasterRecursive or ForecasterDirect."""

    is_direct = plan.forecaster == "ForecasterDirect"
    forecaster_module = "direct" if is_direct else "recursive"
    forecaster_class = plan.forecaster
    estimator_import = ESTIMATOR_IMPORTS.get(
        plan.estimator or "",
        f"from __main__ import {plan.estimator}  "
        f"# TODO: replace with correct import for {plan.estimator}",
    )

    lines: list[str] = []

    # Imports
    lines.append("import pandas as pd")
    lines.append(f"from skforecast.{forecaster_module} import {forecaster_class}")
    lines.append(
        "from skforecast.model_selection import backtesting_forecaster, TimeSeriesFold"
    )
    lines.append(estimator_import)
    if plan.forecaster_kwargs.get("transformer_y") or plan.forecaster_kwargs.get("transformer_exog"):
        lines.append("from sklearn.preprocessing import StandardScaler")
    lines.append("")

    # Load data
    lines.append("# Load data")
    lines.append(f"data = pd.read_csv('{data_path}', index_col=0, parse_dates=True)")
    if profile.frequency:
        lines.append(f"data = data.asfreq('{profile.frequency}')")
    lines.append("")

    # Train/test split
    exog_columns = profile.exog_columns
    lines.append("# Train/test split (time-based)")
    lines.append("n_train = int(len(data) * 0.8)")
    lines.append(f"y_train = data.iloc[:n_train]['{profile.target}']")
    lines.append(f"y_test = data.iloc[n_train:]['{profile.target}']")
    if plan.use_exog and exog_columns:
        exog_cols_repr = repr(exog_columns)
        lines.append(f"exog_train = data.iloc[:n_train][{exog_cols_repr}]")
        lines.append(f"exog_test = data.iloc[n_train:][{exog_cols_repr}]")
    lines.append("")

    # Create forecaster
    lines.append("# Create forecaster")
    lags = plan.forecaster_kwargs.get("lags")
    dropna = plan.forecaster_kwargs.get("dropna_from_series")
    transformer_y = plan.forecaster_kwargs.get("transformer_y")
    transformer_exog = plan.forecaster_kwargs.get("transformer_exog")
    if is_direct:
        lines.append(f"forecaster = {forecaster_class}(")
        lines.append(f"    steps     = {plan.steps},")
        lines.append(f"    estimator = {plan.estimator}(random_state=123),")
        lines.append(f"    lags      = {lags},")
        if transformer_y is not None:
            lines.append(f"    transformer_y = {transformer_y}(),")
        if transformer_exog is not None:
            lines.append(f"    transformer_exog = {transformer_exog}(),")
        if dropna is not None:
            lines.append(f"    dropna_from_series = {dropna},")
        lines.append(")")
    else:
        lines.append(f"forecaster = {forecaster_class}(")
        lines.append(f"    estimator = {plan.estimator}(random_state=123),")
        lines.append(f"    lags      = {lags},")
        if transformer_y is not None:
            lines.append(f"    transformer_y = {transformer_y}(),")
        if transformer_exog is not None:
            lines.append(f"    transformer_exog = {transformer_exog}(),")
        if dropna is not None:
            lines.append(f"    dropna_from_series = {dropna},")
        lines.append(")")
    lines.append("")

    # Fit
    lines.append("# Fit")
    if plan.use_exog and exog_columns:
        lines.append("forecaster.fit(y=y_train, exog=exog_train)")
    else:
        lines.append("forecaster.fit(y=y_train)")
    lines.append("")

    # Predict
    lines.append("# Predict")
    if plan.use_exog and exog_columns:
        lines.append(
            f"predictions = forecaster.predict(steps={plan.steps}, "
            f"exog=exog_test.iloc[:{plan.steps}])"
        )
    else:
        lines.append(f"predictions = forecaster.predict(steps={plan.steps})")
    lines.append("print(predictions)")
    lines.append("")

    # Backtesting
    lines.append("# Backtesting")
    lines.append("cv = TimeSeriesFold(")
    lines.append(f"    steps              = {plan.steps},")
    lines.append("    initial_train_size = n_train,")
    lines.append("    refit              = False,")
    lines.append(")")
    lines.append("")
    lines.append("metric, predictions_bt = backtesting_forecaster(")
    lines.append("    forecaster = forecaster,")
    lines.append(f"    y          = data['{profile.target}'],")
    if plan.use_exog and exog_columns:
        lines.append(f"    exog       = data[{repr(exog_columns)}],")
    lines.append("    cv         = cv,")
    lines.append(f"    metric     = '{plan.metric}',")
    lines.append(")")
    lines.append('print(f"Backtest {metric}")')
    lines.append("")

    # Prediction intervals
    if plan.interval_method is not None:
        lines.append("# Prediction intervals")
        if plan.use_exog and exog_columns:
            lines.append(
                "forecaster.fit(y=y_train, exog=exog_train, "
                "store_in_sample_residuals=True)"
            )
            lines.append("predictions_interval = forecaster.predict_interval(")
            lines.append(f"    steps    = {plan.steps},")
            lines.append(f"    exog     = exog_test.iloc[:{plan.steps}],")
            lines.append(f"    method   = '{plan.interval_method}',")
            lines.append("    interval = [10, 90],")
            lines.append(")")
        else:
            lines.append(
                "forecaster.fit(y=y_train, store_in_sample_residuals=True)"
            )
            lines.append("predictions_interval = forecaster.predict_interval(")
            lines.append(f"    steps    = {plan.steps},")
            lines.append(f"    method   = '{plan.interval_method}',")
            lines.append("    interval = [10, 90],")
            lines.append(")")
        lines.append("print(predictions_interval)")
        lines.append("")

    return "\n".join(lines)


def _template_multi_series(
    plan: ForecastPlan,
    profile: DataProfile,
    data_path: str,
) -> str:
    """Generate code for ForecasterRecursiveMultiSeries."""

    estimator_import = ESTIMATOR_IMPORTS.get(
        plan.estimator or "",
        f"from __main__ import {plan.estimator}  "
        f"# TODO: replace with correct import for {plan.estimator}",
    )
    series_id = profile.series_id_column or "series_id"
    date_col = profile.date_column or "date"

    lines: list[str] = []

    # Imports
    lines.append("import pandas as pd")
    lines.append("from skforecast.recursive import ForecasterRecursiveMultiSeries")
    lines.append(
        "from skforecast.model_selection import "
        "backtesting_forecaster_multiseries, TimeSeriesFold"
    )
    lines.append(estimator_import)
    if plan.forecaster_kwargs.get("transformer_series") or plan.forecaster_kwargs.get("transformer_exog"):
        lines.append("from sklearn.preprocessing import StandardScaler")
    lines.append("")

    # Load data
    lines.append("# Load data (long format)")
    lines.append(f"data = pd.read_csv('{data_path}', parse_dates=['{date_col}'])")
    lines.append("")

    # Pivot to wide format
    lines.append("# Pivot to wide format (columns = series)")
    lines.append("series = data.pivot_table(")
    lines.append(
        f"    index='{date_col}', columns='{series_id}',"
        f" values='{profile.target}'"
    )
    lines.append(")")
    lines.append("series.index = pd.DatetimeIndex(series.index)")
    lines.append("series.index.name = None")
    if profile.frequency:
        lines.append(f"series = series.asfreq('{profile.frequency}')")
    lines.append("")

    # Train/test split
    lines.append("# Train/test split")
    lines.append("n_train = int(len(series) * 0.8)")
    lines.append("")

    # Create forecaster
    lags = plan.forecaster_kwargs.get("lags")
    encoding = plan.forecaster_kwargs.get("encoding", "ordinal")
    dropna = plan.forecaster_kwargs.get("dropna_from_series")
    transformer_series = plan.forecaster_kwargs.get("transformer_series")
    transformer_exog = plan.forecaster_kwargs.get("transformer_exog")
    lines.append("# Create forecaster")
    lines.append("forecaster = ForecasterRecursiveMultiSeries(")
    lines.append(f"    estimator = {plan.estimator}(random_state=123),")
    lines.append(f"    lags      = {lags},")
    lines.append(f"    encoding  = '{encoding}',")
    if transformer_series is not None:
        lines.append(f"    transformer_series = {transformer_series}(),")
    if transformer_exog is not None:
        lines.append(f"    transformer_exog = {transformer_exog}(),")
    if dropna is not None:
        lines.append(f"    dropna_from_series = {dropna},")
    lines.append(")")
    lines.append("")

    # Fit
    lines.append("# Fit")
    lines.append("forecaster.fit(series=series)")
    lines.append("")

    # Predict
    lines.append("# Predict")
    lines.append(f"predictions = forecaster.predict(steps={plan.steps})")
    lines.append("print(predictions)")
    lines.append("")

    # Backtesting
    lines.append("# Backtesting")
    lines.append("cv = TimeSeriesFold(")
    lines.append(f"    steps              = {plan.steps},")
    lines.append("    initial_train_size = n_train,")
    lines.append("    refit              = False,")
    lines.append(")")
    lines.append("")
    lines.append("metric, predictions_bt = backtesting_forecaster_multiseries(")
    lines.append("    forecaster = forecaster,")
    lines.append("    series     = series,")
    lines.append("    cv         = cv,")
    lines.append(f"    metric     = '{plan.metric}',")
    lines.append(")")
    lines.append('print(f"Backtest {metric}")')
    lines.append("")

    # Prediction intervals
    if plan.interval_method is not None:
        lines.append("# Prediction intervals")
        lines.append(
            "forecaster.fit(series=series, store_in_sample_residuals=True)"
        )
        lines.append("predictions_interval = forecaster.predict_interval(")
        lines.append(f"    steps    = {plan.steps},")
        lines.append(f"    method   = '{plan.interval_method}',")
        lines.append("    interval = [10, 90],")
        lines.append(")")
        lines.append("print(predictions_interval)")
        lines.append("")

    return "\n".join(lines)


def _template_statistical(
    plan: ForecastPlan,
    profile: DataProfile,
    data_path: str,
) -> str:
    """Generate code for ForecasterStats with Auto-ARIMA."""

    lines: list[str] = []

    # Imports
    lines.append("import pandas as pd")
    lines.append("from skforecast.stats import ForecasterStats, Arima")
    lines.append(
        "from skforecast.model_selection import backtesting_stats, TimeSeriesFold"
    )
    lines.append("")

    # Load data
    lines.append("# Load data")
    lines.append(f"data = pd.read_csv('{data_path}', index_col=0, parse_dates=True)")
    if profile.frequency:
        lines.append(f"data = data.asfreq('{profile.frequency}')")
    lines.append("")

    # Train/test split
    lines.append("# Train/test split (time-based)")
    lines.append("n_train = int(len(data) * 0.8)")
    lines.append(f"y_train = data.iloc[:n_train]['{profile.target}']")
    lines.append(f"y_test = data.iloc[n_train:]['{profile.target}']")
    lines.append("")

    # Create forecaster
    lines.append("# Create forecaster (Auto-ARIMA)")
    lines.append("forecaster = ForecasterStats(")
    lines.append("    estimator = Arima(order=None, seasonal=True),")
    lines.append(")")
    lines.append("")

    # Fit
    lines.append("# Fit")
    lines.append("forecaster.fit(y=y_train)")
    lines.append("")

    # Predict
    lines.append("# Predict")
    lines.append(f"predictions = forecaster.predict(steps={plan.steps})")
    lines.append("print(predictions)")
    lines.append("")

    # Backtesting
    lines.append("# Backtesting")
    lines.append("cv = TimeSeriesFold(")
    lines.append(f"    steps              = {plan.steps},")
    lines.append("    initial_train_size = n_train,")
    lines.append("    refit              = False,")
    lines.append(")")
    lines.append("")
    lines.append("metric, predictions_bt = backtesting_stats(")
    lines.append("    forecaster = forecaster,")
    lines.append(f"    y          = data['{profile.target}'],")
    lines.append("    cv         = cv,")
    lines.append(f"    metric     = '{plan.metric}',")
    lines.append(")")
    lines.append('print(f"Backtest {metric}")')
    lines.append("")

    # Prediction intervals (native)
    lines.append("# Prediction intervals (native)")
    lines.append("predictions_interval = forecaster.predict_interval(")
    lines.append(f"    steps    = {plan.steps},")
    lines.append("    interval = [10, 90],")
    lines.append(")")
    lines.append("print(predictions_interval)")
    lines.append("")

    return "\n".join(lines)


def _template_foundation(
    plan: ForecastPlan,
    profile: DataProfile,
    data_path: str,
) -> str:
    """Generate code for ForecasterFoundation with Chronos-2."""

    lines: list[str] = []

    # Imports
    lines.append("import pandas as pd")
    lines.append(
        "from skforecast.foundation import FoundationModel, ForecasterFoundation"
    )
    lines.append(
        "from skforecast.model_selection import backtesting_foundation, TimeSeriesFold"
    )
    lines.append("")

    # Load data
    lines.append("# Load data")
    lines.append(f"data = pd.read_csv('{data_path}', index_col=0, parse_dates=True)")
    if profile.frequency:
        lines.append(f"data = data.asfreq('{profile.frequency}')")
    lines.append("")

    # Create foundation model
    lines.append("# Create foundation model (Chronos-2)")
    lines.append("model = FoundationModel(")
    lines.append("    model_id       = 'autogluon/chronos-2-small',")
    lines.append("    context_length = 2048,")
    lines.append("    device_map     = 'auto',")
    lines.append(")")
    lines.append("")

    # Create forecaster
    lines.append("# Create forecaster")
    lines.append("forecaster = ForecasterFoundation(estimator=model)")
    lines.append("")

    # Fit
    lines.append("# Fit (stores context only — no training)")
    lines.append(f"forecaster.fit(series=data['{profile.target}'])")
    lines.append("")

    # Predict
    lines.append("# Predict")
    lines.append(f"predictions = forecaster.predict(steps={plan.steps})")
    lines.append("print(predictions)")
    lines.append("")

    # Backtesting
    lines.append("# Backtesting")
    lines.append("cv = TimeSeriesFold(")
    lines.append(f"    steps              = {plan.steps},")
    lines.append("    initial_train_size = int(len(data) * 0.8),")
    lines.append("    refit              = False,")
    lines.append(")")
    lines.append("")
    lines.append("metric, predictions_bt = backtesting_foundation(")
    lines.append("    forecaster = forecaster,")
    lines.append(f"    series     = data['{profile.target}'],")
    lines.append("    cv         = cv,")
    lines.append(f"    metric     = '{plan.metric}',")
    lines.append(")")
    lines.append('print(f"Backtest {metric}")')
    lines.append("")

    # Quantile predictions
    lines.append("# Quantile predictions (native)")
    lines.append("predictions_quantiles = forecaster.predict_quantiles(")
    lines.append(f"    steps     = {plan.steps},")
    lines.append("    quantiles = [0.1, 0.5, 0.9],")
    lines.append(")")
    lines.append("print(predictions_quantiles)")
    lines.append("")

    return "\n".join(lines)
