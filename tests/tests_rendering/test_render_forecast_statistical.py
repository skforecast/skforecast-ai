# Unit test render_forecast_statistical rendering

from skforecast_ai.rendering import render_forecast_statistical
from skforecast_ai.schemas import RenderedScript

from .fixtures_rendering import (
    plan_statistical,
    plan_statistical_with_intervals,
    profile_single_no_exog,
)


# =============================================================================
# Tests: render_forecast_statistical — full script comparison
# =============================================================================
def test_render_forecast_statistical_output_when_daily_frequency():
    """
    Test that render_forecast_statistical produces the expected full
    script for Auto-ARIMA with daily frequency (m=7).
    """
    result = render_forecast_statistical(plan_statistical, profile_single_no_exog)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from skforecast.stats import Arima\n"
        "from skforecast.recursive import ForecasterStats\n"
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
        "# Create forecaster (Auto-ARIMA)\n"
        "forecaster = ForecasterStats(\n"
        "    estimator = Arima(order=None, seasonal_order=None, m=7),\n"
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


def test_render_forecast_statistical_output_when_intervals_requested():
    """
    Test that render_forecast_statistical produces the expected full
    script when native prediction intervals are requested.
    """
    result = render_forecast_statistical(plan_statistical_with_intervals, profile_single_no_exog)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from skforecast.stats import Arima\n"
        "from skforecast.recursive import ForecasterStats\n"
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
        "# Create forecaster (Auto-ARIMA)\n"
        "forecaster = ForecasterStats(\n"
        "    estimator = Arima(order=None, seasonal_order=None, m=7),\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(y=data_train['sales'])\n"
        "\n"
        "# Predict intervals (native)\n"
        "steps = 10\n"
        "predictions = forecaster.predict_interval(\n"
        "    steps    = steps,\n"
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
