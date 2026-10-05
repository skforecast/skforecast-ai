# Unit test render_forecast_statistical rendering

import pytest

from skforecast_ai.rendering import render_forecast_statistical
from skforecast_ai.schemas import RenderedScript

from .fixtures_rendering import (
    plan_statistical,
    plan_statistical_exog,
    plan_statistical_with_intervals,
    profile_single_mixed_exog,
    profile_single_no_exog,
)


# =============================================================================
# Tests: render_forecast_statistical: full script comparison
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


# =============================================================================
# Tests: render_forecast_statistical - categorical exog exclusion
# =============================================================================
def test_render_forecast_statistical_output_when_categorical_exog():
    """
    Test that render_forecast_statistical keeps only the numeric
    exogenous columns and documents the exclusion of the categorical
    ones, which statistical models cannot handle.
    """
    result = render_forecast_statistical(
        plan_statistical_exog, profile_single_mixed_exog
    )

    assert isinstance(result, RenderedScript)

    script = result.full_script
    expected_exog_block = (
        "# Categorical exog excluded (holiday): statistical models only "
        "accept numeric exogenous variables\n"
        "exog_features = ['temp']\n"
    )
    expected_fit = (
        "forecaster.fit(y=data_train['sales'], exog=data_train[exog_features])"
    )

    assert expected_exog_block in script
    assert expected_fit in script
    assert "'holiday'" not in script


# =============================================================================
# Tests: render_forecast_statistical: seasonal period
# =============================================================================
@pytest.mark.parametrize(
    "frequency, expected_estimator",
    [
        ("QS-OCT", "Arima(order=None, seasonal_order=None, m=4)"),
        ("QE-DEC", "Arima(order=None, seasonal_order=None, m=4)"),
        ("W-WED", "Arima(order=None, seasonal_order=None, m=52)"),
        ("YE-DEC", "Arima(order=None, seasonal_order=None, m=1)"),
        ("Q-DEC", "Arima(order=None, seasonal_order=None, m=4)"),
        ("3h", "Arima(order=None, seasonal_order=None, m=8)"),
        ("14h", "Arima(order=None, seasonal_order=None, m=12)"),
        ("4W", "Arima(order=None, seasonal_order=None)"),
        ("2W", "Arima(order=None, seasonal_order=None)"),
        ("10s", "Arima(order=None, seasonal_order=None)"),
        ("3D", "Arima(order=None, seasonal_order=None)"),
        ("7MS", "Arima(order=None, seasonal_order=None)"),
    ],
    ids=lambda dt: f"frequency, expected_estimator: {dt}",
)
def test_render_forecast_statistical_output_seasonal_period_when_anchored_or_multiplied_frequency(
    frequency, expected_estimator
):
    """
    Test that render_forecast_statistical gives Auto-ARIMA the seasonal
    period of the base alias of an anchored frequency (quarters starting in
    October, weeks ending on Wednesday, years ending in December, and the
    quarter alias of pandas 2.1), as the lags and the baseline read it. A
    multiplied frequency outside the table gets the first period of
    estimate_seasonality when it is a whole cycle of 12 steps at most
    ('3h': 8, '14h': 12) and none otherwise ('4W': 13, '2W': 26 and '10s':
    360 are longer; '3D': 2 steps are not a week; '7MS': a period of 1).
    """
    profile = profile_single_no_exog.model_copy(update={"frequency": frequency})

    result = render_forecast_statistical(plan_statistical, profile)

    assert f"    estimator = {expected_estimator},\n" in result.full_script
    assert f"data = data.asfreq({frequency!r})\n" in result.full_script
