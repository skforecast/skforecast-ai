# Unit test render_forecast_baseline rendering

from skforecast_ai.rendering import render_forecast_baseline
from skforecast_ai.schemas import RenderedScript

from .fixtures_rendering import (
    plan_baseline,
    plan_baseline_naive,
    plan_baseline_no_end_train,
    plan_baseline_with_intervals,
    profile_single,
    profile_single_no_exog,
)


# =============================================================================
# Tests: render_forecast_baseline: full script comparison
# =============================================================================
def test_render_forecast_baseline_output_when_seasonal_naive():
    """
    Test that render_forecast_baseline produces the expected full script for
    a seasonal naive baseline in evaluation mode, without exogenous
    variables even though the profile has some.
    """
    result = render_forecast_baseline(plan_baseline, profile_single)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from skforecast.recursive import ForecasterEquivalentDate\n"
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
        '    f"Train dates : {data_train.index.min()} --- {data_train.index.max()}  (n={len(data_train)})"\n'
        ")\n"
        "print(\n"
        '    f"Test dates  : {data_test.index.min()} --- {data_test.index.max()}  (n={len(data_test)})"\n'
        ")\n"
        "\n"
        "# Create forecaster (baseline, seasonal naive)\n"
        "forecaster = ForecasterEquivalentDate(\n"
        "    offset    = 7,\n"
        "    n_offsets = 1,\n"
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


def test_render_forecast_baseline_output_when_naive():
    """
    Test that render_forecast_baseline labels an `offset=1` baseline as
    naive.
    """
    result = render_forecast_baseline(plan_baseline_naive, profile_single_no_exog)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from skforecast.recursive import ForecasterEquivalentDate\n"
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
        '    f"Train dates : {data_train.index.min()} --- {data_train.index.max()}  (n={len(data_train)})"\n'
        ")\n"
        "print(\n"
        '    f"Test dates  : {data_test.index.min()} --- {data_test.index.max()}  (n={len(data_test)})"\n'
        ")\n"
        "\n"
        "# Create forecaster (baseline, naive)\n"
        "forecaster = ForecasterEquivalentDate(\n"
        "    offset    = 1,\n"
        "    n_offsets = 1,\n"
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


def test_render_forecast_baseline_output_when_intervals_requested():
    """
    Test that render_forecast_baseline stores the in-sample residuals and
    predicts conformal intervals when an interval is requested.
    """
    result = render_forecast_baseline(plan_baseline_with_intervals, profile_single_no_exog)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from skforecast.recursive import ForecasterEquivalentDate\n"
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
        '    f"Train dates : {data_train.index.min()} --- {data_train.index.max()}  (n={len(data_train)})"\n'
        ")\n"
        "print(\n"
        '    f"Test dates  : {data_test.index.min()} --- {data_test.index.max()}  (n={len(data_test)})"\n'
        ")\n"
        "\n"
        "# Create forecaster (baseline, seasonal naive)\n"
        "forecaster = ForecasterEquivalentDate(\n"
        "    offset    = 7,\n"
        "    n_offsets = 1,\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(\n"
        "    y                         = data_train['sales'],\n"
        "    store_in_sample_residuals = True,\n"
        ")\n"
        "\n"
        "# Predict intervals (conformal)\n"
        "steps = 10\n"
        "predictions = forecaster.predict_interval(\n"
        "    steps    = steps,\n"
        "    method   = 'conformal',\n"
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


def test_render_forecast_baseline_output_when_prediction_mode():
    """
    Test that render_forecast_baseline fits on all the data and emits no
    train/test split or metrics when `end_train` is None.
    """
    result = render_forecast_baseline(plan_baseline_no_end_train, profile_single_no_exog)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from skforecast.recursive import ForecasterEquivalentDate\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Create forecaster (baseline, seasonal naive)\n"
        "forecaster = ForecasterEquivalentDate(\n"
        "    offset    = 7,\n"
        "    n_offsets = 1,\n"
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


def test_render_forecast_baseline_no_future_exog_when_prediction_mode_with_exog():
    """
    Test that render_forecast_baseline loads no future exogenous values in
    prediction mode, even when the profile has exogenous columns.
    """
    result = render_forecast_baseline(plan_baseline_no_end_train, profile_single)

    assert "exog" not in result.full_script
    assert result.full_script == render_forecast_baseline(
        plan_baseline_no_end_train, profile_single_no_exog
    ).full_script

