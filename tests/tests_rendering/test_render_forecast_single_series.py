# Unit test render_forecast_single_series rendering

from skforecast_ai.rendering import render_forecast_single_series
from skforecast_ai.schemas import RenderedScript

from .fixtures_rendering import (
    plan_single_direct,
    plan_single_no_end_train,
    plan_single_predict_exog,
    plan_single_recursive,
    plan_single_recursive_no_exog,
    plan_single_with_intervals,
    plan_single_with_window_features,
    profile_single,
    profile_single_no_exog,
)


# =============================================================================
# Tests: render_forecast_single_series — structure
# =============================================================================
def test_render_forecast_single_series_output_when_no_exog_structure():
    """
    Test that render_forecast_single_series returns a RenderedScript
    with non-empty imports, data_loading, and core sections, and that
    full_script is their concatenation.
    """
    result = render_forecast_single_series(plan_single_recursive_no_exog, profile_single_no_exog)

    assert isinstance(result, RenderedScript)
    assert result.imports.strip() != ""
    assert result.data_loading.strip() != ""
    assert result.core.strip() != ""
    assert result.full_script == result.imports + "\n" + result.data_loading + "\n" + result.core


# =============================================================================
# Tests: render_forecast_single_series — full script comparison
# =============================================================================
def test_render_forecast_single_series_output_when_no_exog():
    """
    Test that render_forecast_single_series produces the expected full
    script for a basic recursive forecaster without exogenous variables.
    """
    result = render_forecast_single_series(plan_single_recursive_no_exog, profile_single_no_exog)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.recursive import ForecasterRecursive\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "data_train = data.loc[:end_train]\n"
        "data_test  = data.loc[data.index > end_train]\n"
        "\n"
        "print(\n"
        '    f"Train dates : {data_train.index.min()} --- '
        '{data_train.index.max()}  (n={len(data_train)})"\n'
        ")\n"
        "print(\n"
        '    f"Test dates  : {data_test.index.min()} --- '
        '{data_test.index.max()}  (n={len(data_test)})"\n'
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursive(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(y=data_train['sales'])\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set\n"
        "actual = data_test['sales'].iloc[:steps]\n"
        "mae = mean_absolute_error(actual, predictions)\n"
        "mse = mean_squared_error(actual, predictions)\n"
        "mase = mean_absolute_scaled_error(\n"
        "    y_true  = actual,\n"
        "    y_pred  = predictions,\n"
        "    y_train = data_train['sales'],\n"
        ")\n"
        "\n"
        'print(f"MAE  : {mae:.4f}")\n'
        'print(f"MSE  : {mse:.4f}")\n'
        'print(f"MASE : {mase:.4f}")\n'
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, retrain with all available data\n"
        "# and call predict() on the desired horizon.\n"
    )
    assert result.full_script == expected


def test_render_forecast_single_series_output_when_exog():
    """
    Test that render_forecast_single_series produces the expected full
    script when exogenous variables are included.
    """
    result = render_forecast_single_series(plan_single_recursive, profile_single)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.recursive import ForecasterRecursive\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "data_train = data.loc[:end_train]\n"
        "data_test  = data.loc[data.index > end_train]\n"
        "exog_features = ['promo']\n"
        "\n"
        "print(\n"
        '    f"Train dates : {data_train.index.min()} --- '
        '{data_train.index.max()}  (n={len(data_train)})"\n'
        ")\n"
        "print(\n"
        '    f"Test dates  : {data_test.index.min()} --- '
        '{data_test.index.max()}  (n={len(data_test)})"\n'
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursive(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(y=data_train['sales'], exog=data_train[exog_features])\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps, exog=data_test[exog_features])\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set\n"
        "actual = data_test['sales'].iloc[:steps]\n"
        "mae = mean_absolute_error(actual, predictions)\n"
        "mse = mean_squared_error(actual, predictions)\n"
        "mase = mean_absolute_scaled_error(\n"
        "    y_true  = actual,\n"
        "    y_pred  = predictions,\n"
        "    y_train = data_train['sales'],\n"
        ")\n"
        "\n"
        'print(f"MAE  : {mae:.4f}")\n'
        'print(f"MSE  : {mse:.4f}")\n'
        'print(f"MASE : {mase:.4f}")\n'
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, retrain with all available data\n"
        "# and provide future exogenous values covering the forecast horizon.\n"
    )
    assert result.full_script == expected


def test_render_forecast_single_series_output_when_intervals_requested():
    """
    Test that render_forecast_single_series produces the expected full
    script when prediction intervals are requested via bootstrapping.
    """
    result = render_forecast_single_series(plan_single_with_intervals, profile_single_no_exog)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.recursive import ForecasterRecursive\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "data_train = data.loc[:end_train]\n"
        "data_test  = data.loc[data.index > end_train]\n"
        "\n"
        "print(\n"
        '    f"Train dates : {data_train.index.min()} --- '
        '{data_train.index.max()}  (n={len(data_train)})"\n'
        ")\n"
        "print(\n"
        '    f"Test dates  : {data_test.index.min()} --- '
        '{data_test.index.max()}  (n={len(data_test)})"\n'
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursive(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(\n"
        "    y                         = data_train['sales'],\n"
        "    store_in_sample_residuals = True,\n"
        ")\n"
        "\n"
        "# Predict intervals\n"
        "steps = 10\n"
        "predictions = forecaster.predict_interval(\n"
        "    steps    = steps,\n"
        "    method   = 'bootstrapping',\n"
        "    interval = [0.1, 0.9],\n"
        ")\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set\n"
        "actual = data_test['sales'].iloc[:steps]\n"
        "mae = mean_absolute_error(actual, predictions['pred'])\n"
        "mse = mean_squared_error(actual, predictions['pred'])\n"
        "mase = mean_absolute_scaled_error(\n"
        "    y_true  = actual,\n"
        "    y_pred  = predictions['pred'],\n"
        "    y_train = data_train['sales'],\n"
        ")\n"
        "\n"
        'print(f"MAE  : {mae:.4f}")\n'
        'print(f"MSE  : {mse:.4f}")\n'
        'print(f"MASE : {mase:.4f}")\n'
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, retrain with all available data\n"
        "# and call predict() on the desired horizon.\n"
    )
    assert result.full_script == expected


def test_render_forecast_single_series_output_when_window_features():
    """
    Test that render_forecast_single_series produces the expected full
    script when window features (RollingFeatures) are included.
    """
    result = render_forecast_single_series(
        plan_single_with_window_features, profile_single_no_exog
    )

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.preprocessing import RollingFeatures\n"
        "from skforecast.recursive import ForecasterRecursive\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "data_train = data.loc[:end_train]\n"
        "data_test  = data.loc[data.index > end_train]\n"
        "\n"
        "print(\n"
        '    f"Train dates : {data_train.index.min()} --- '
        '{data_train.index.max()}  (n={len(data_train)})"\n'
        ")\n"
        "print(\n"
        '    f"Test dates  : {data_test.index.min()} --- '
        '{data_test.index.max()}  (n={len(data_test)})"\n'
        ")\n"
        "\n"
        "window_features = RollingFeatures(\n"
        "    stats        = ['mean', 'std'],\n"
        "    window_sizes = [7, 7],\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursive(\n"
        "    estimator       = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags            = 7,\n"
        "    window_features = window_features,\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(y=data_train['sales'])\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set\n"
        "actual = data_test['sales'].iloc[:steps]\n"
        "mae = mean_absolute_error(actual, predictions)\n"
        "mse = mean_squared_error(actual, predictions)\n"
        "mase = mean_absolute_scaled_error(\n"
        "    y_true  = actual,\n"
        "    y_pred  = predictions,\n"
        "    y_train = data_train['sales'],\n"
        ")\n"
        "\n"
        'print(f"MAE  : {mae:.4f}")\n'
        'print(f"MSE  : {mse:.4f}")\n'
        'print(f"MASE : {mase:.4f}")\n'
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, retrain with all available data\n"
        "# and call predict() on the desired horizon.\n"
    )
    assert result.full_script == expected


def test_render_forecast_single_series_output_when_direct_strategy():
    """
    Test that render_forecast_single_series produces the expected full
    script for ForecasterDirect with steps in the constructor.
    """
    result = render_forecast_single_series(plan_single_direct, profile_single_no_exog)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.direct import ForecasterDirect\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "data_train = data.loc[:end_train]\n"
        "data_test  = data.loc[data.index > end_train]\n"
        "\n"
        "print(\n"
        '    f"Train dates : {data_train.index.min()} --- '
        '{data_train.index.max()}  (n={len(data_train)})"\n'
        ")\n"
        "print(\n"
        '    f"Test dates  : {data_test.index.min()} --- '
        '{data_test.index.max()}  (n={len(data_test)})"\n'
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterDirect(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    steps     = 5,\n"
        "    lags      = 7,\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(y=data_train['sales'])\n"
        "\n"
        "# Predict\n"
        "steps = 5\n"
        "predictions = forecaster.predict(steps=steps)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set\n"
        "actual = data_test['sales'].iloc[:steps]\n"
        "mae = mean_absolute_error(actual, predictions)\n"
        "mse = mean_squared_error(actual, predictions)\n"
        "mase = mean_absolute_scaled_error(\n"
        "    y_true  = actual,\n"
        "    y_pred  = predictions,\n"
        "    y_train = data_train['sales'],\n"
        ")\n"
        "\n"
        'print(f"MAE  : {mae:.4f}")\n'
        'print(f"MSE  : {mse:.4f}")\n'
        'print(f"MASE : {mase:.4f}")\n'
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, retrain with all available data\n"
        "# and call predict() on the desired horizon.\n"
    )
    assert result.full_script == expected


# =============================================================================
# Tests: Prediction mode — no train/test split when plan.end_train is None
# =============================================================================
def test_render_forecast_single_series_output_when_prediction_mode():
    """
    Test that render_forecast_single_series produces prediction-mode code
    when plan.end_train is None: no train/test split, fit on the full
    data, and no metrics section.
    """
    result = render_forecast_single_series(
        plan_single_no_end_train, profile_single_no_exog
    )

    expected = (
        "import pandas as pd\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.recursive import ForecasterRecursive\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursive(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(y=data['sales'])\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps)\n"
        "print(predictions)\n"
    )
    assert result.full_script == expected

    # Prediction mode must not emit any of the evaluation-mode constructs.
    assert "# Train/test split" not in result.full_script
    assert "data_train" not in result.full_script
    assert "data_test" not in result.full_script
    assert "# Evaluate on test set" not in result.full_script
    assert "mean_absolute_error" not in result.full_script


def test_render_forecast_single_series_prepares_future_exog_index_when_prediction_exog():
    """
    Test that prediction mode with exog loads and prepares the future
    exogenous frame exactly like `data` (same `date_column`-driven read
    and index setup), so `data` and `exog_future` share one code path and
    the standalone script and the in-memory run agree. `profile_single`
    uses a `date_column`, so both use the read_csv + set_index style.
    """
    result = render_forecast_single_series(
        plan_single_predict_exog, profile_single
    )
    date_col = profile_single.date_column
    freq = profile_single.frequency

    # The future exog is loaded in the (non-executed) preamble, mirroring
    # how `data` is loaded (no index_col, since a date column is used).
    assert "data = pd.read_csv('data.csv')" in result.data_loading
    assert "exog_future = pd.read_csv('exog_future.csv')" in result.data_loading

    # ... and prepared in the executed core with the same steps as `data`.
    assert f"exog_future[{date_col!r}] = pd.to_datetime(exog_future[{date_col!r}])" in result.core
    assert f"exog_future = exog_future.set_index({date_col!r})" in result.core
    assert f"exog_future = exog_future.asfreq('{freq}')" in result.core
    assert "exog_future = exog_future.sort_index()" in result.core

    prep_pos = result.core.index("exog_future = exog_future.set_index")
    fit_pos = result.core.index("forecaster.fit(")
    assert prep_pos < fit_pos


def test_render_forecast_single_series_future_exog_uses_index_style_when_no_date_column():
    """
    Test that when the profile has no date column (the datetime is already
    the index), both `data` and `exog_future` are loaded with the
    index-based read (`index_col=0, parse_dates=True`) and prepared with
    asfreq + sort only, keeping the two consistent.
    """
    profile = profile_single_no_exog.model_copy(
        update={"date_column": None, "exog_columns": ["promo"]}
    )
    result = render_forecast_single_series(plan_single_predict_exog, profile)

    assert (
        "data = pd.read_csv('data.csv', index_col=0, parse_dates=True)"
        in result.data_loading
    )
    assert (
        "exog_future = pd.read_csv('exog_future.csv', index_col=0, parse_dates=True)"
        in result.data_loading
    )
    assert "exog_future = exog_future.asfreq('D')" in result.core
    assert "exog_future = exog_future.sort_index()" in result.core
    # No date column, so no set_index for either frame.
    assert "exog_future.set_index" not in result.core


def test_render_forecast_single_series_no_future_exog_prep_when_no_exog():
    """
    Test that prediction mode without exog does not emit any future
    exogenous index preparation.
    """
    result = render_forecast_single_series(
        plan_single_no_end_train, profile_single_no_exog
    )

    assert "exog_future" not in result.full_script
