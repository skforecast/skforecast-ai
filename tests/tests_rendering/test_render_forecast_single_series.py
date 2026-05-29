# Unit test render_forecast_single_series rendering

import re

import pytest

from skforecast_ai.rendering import render_forecast_single_series
from skforecast_ai.schemas import RenderedScript

from .fixtures_rendering import (
    plan_single_direct,
    plan_single_recursive,
    plan_single_recursive_no_exog,
    plan_single_with_intervals,
    plan_single_with_window_features,
    profile_single,
    profile_single_no_end_train,
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
        "end_train = '2023-03-12'  # 80% of data, adjust to change the split point\n"
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
        "end_train = '2023-03-12'  # 80% of data, adjust to change the split point\n"
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
        "end_train = '2023-03-12'  # 80% of data, adjust to change the split point\n"
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
        "    interval = [10, 90],\n"
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
        "end_train = '2023-03-12'  # 80% of data, adjust to change the split point\n"
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
        "end_train = '2023-03-12'  # 80% of data, adjust to change the split point\n"
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
# Tests: Negative — error when profile.end_train is None
# =============================================================================
def test_render_forecast_single_series_ValueError_when_end_train_is_none():
    """
    Test that render_forecast_single_series raises ValueError when
    profile.end_train is None (data profiling not completed).
    """
    msg = re.escape(
        "profile.end_train must be set before generating code. "
        "Run data profiling first so the 80% split date is computed."
    )
    with pytest.raises(ValueError, match=msg):
        render_forecast_single_series(plan_single_recursive_no_exog, profile_single_no_end_train)
