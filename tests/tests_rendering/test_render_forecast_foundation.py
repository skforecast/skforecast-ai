# Unit test render_forecast_foundation rendering

from skforecast_ai.rendering import render_forecast_foundation
from skforecast_ai.schemas import RenderedScript

from .fixtures_rendering import (
    plan_foundation,
    plan_foundation_with_intervals,
    profile_multi_wide,
    profile_single_no_exog,
)


# =============================================================================
# Tests: render_forecast_foundation — full script comparison
# =============================================================================
def test_render_forecast_foundation_output_when_single_series():
    """
    Test that render_forecast_foundation produces the expected full
    script for a single-series Chronos-2 foundation model.
    """
    result = render_forecast_foundation(plan_foundation, profile_single_no_exog)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from skforecast.foundation import FoundationModel, ForecasterFoundation\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "series = data['sales']\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # 80% of data, adjust to change the split point\n"
        "series_train = series.loc[:end_train]\n"
        "series_test  = series.loc[series.index > end_train]\n"
        "\n"
        "# Create foundation model (chronos-2-small)\n"
        "model = FoundationModel(\n"
        "    model_id       = 'autogluon/chronos-2-small',\n"
        "    context_length = 512,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=model)\n"
        "\n"
        "# Fit (stores context only — no training)\n"
        "forecaster.fit(series=series_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set\n"
        "actual = series_test.iloc[:steps]\n"
        "pred = predictions['pred'].values\n"
        "mae = mean_absolute_error(actual, pred)\n"
        "mse = mean_squared_error(actual, pred)\n"
        "mase = mean_absolute_scaled_error(\n"
        "    y_true  = actual,\n"
        "    y_pred  = pred,\n"
        "    y_train = series_train,\n"
        ")\n"
        "\n"
        'print(f"MAE  : {mae:.4f}")\n'
        'print(f"MSE  : {mse:.4f}")\n'
        'print(f"MASE : {mase:.4f}")\n'
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, pass all available data as context\n"
        "# and call predict() on the desired horizon.\n"
    )
    assert result.full_script == expected


def test_render_forecast_foundation_output_when_quantiles_requested():
    """
    Test that render_forecast_foundation produces predict_quantiles
    code when interval_method is 'native'.
    """
    result = render_forecast_foundation(plan_foundation_with_intervals, profile_single_no_exog)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from skforecast.foundation import FoundationModel, ForecasterFoundation\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "series = data['sales']\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # 80% of data, adjust to change the split point\n"
        "series_train = series.loc[:end_train]\n"
        "series_test  = series.loc[series.index > end_train]\n"
        "\n"
        "# Create foundation model (chronos-2-small)\n"
        "model = FoundationModel(\n"
        "    model_id       = 'autogluon/chronos-2-small',\n"
        "    context_length = 512,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=model)\n"
        "\n"
        "# Fit (stores context only — no training)\n"
        "forecaster.fit(series=series_train)\n"
        "\n"
        "# Predict quantiles (native)\n"
        "steps = 10\n"
        "predictions = forecaster.predict_quantiles(\n"
        "    steps     = steps,\n"
        "    quantiles = [0.1, 0.5, 0.9],\n"
        ")\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set\n"
        "actual = series_test.iloc[:steps]\n"
        "pred = predictions['q_0.5'].values\n"
        "mae = mean_absolute_error(actual, pred)\n"
        "mse = mean_squared_error(actual, pred)\n"
        "mase = mean_absolute_scaled_error(\n"
        "    y_true  = actual,\n"
        "    y_pred  = pred,\n"
        "    y_train = series_train,\n"
        ")\n"
        "\n"
        'print(f"MAE  : {mae:.4f}")\n'
        'print(f"MSE  : {mse:.4f}")\n'
        'print(f"MASE : {mase:.4f}")\n'
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, pass all available data as context\n"
        "# and call predict() on the desired horizon.\n"
    )
    assert result.full_script == expected


def test_render_forecast_foundation_output_when_multi_series():
    """
    Test that render_forecast_foundation produces the expected full
    script for multi-series (wide format) foundation model forecasting.
    """
    result = render_forecast_foundation(plan_foundation, profile_multi_wide)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from skforecast.foundation import FoundationModel, ForecasterFoundation\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "series = data[['series_a', 'series_b']]\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # 80% of data, adjust to change the split point\n"
        "series_train = series.loc[:end_train]\n"
        "series_test  = series.loc[series.index > end_train]\n"
        "\n"
        "# Create foundation model (chronos-2-small)\n"
        "model = FoundationModel(\n"
        "    model_id       = 'autogluon/chronos-2-small',\n"
        "    context_length = 512,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=model)\n"
        "\n"
        "# Fit (stores context only — no training)\n"
        "forecaster.fit(series=series_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps, levels=['series_a', 'series_b'])\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set (per series)\n"
        "metrics_list = []\n"
        "for level in predictions['level'].unique():\n"
        "    mask = predictions['level'] == level\n"
        "    pred = predictions.loc[mask, 'pred'].values\n"
        "    actual = series_test[level].iloc[:steps]\n"
        "    metrics_list.append({\n"
        '        "series": level,\n'
        '        "MAE": mean_absolute_error(actual, pred),\n'
        '        "MSE": mean_squared_error(actual, pred),\n'
        '        "MASE": mean_absolute_scaled_error(\n'
        "            actual, pred, y_train=series_train[level]\n"
        "        ),\n"
        "    })\n"
        "metrics_df = pd.DataFrame(metrics_list)\n"
        "print(metrics_df.to_string(index=False))\n"
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, pass all available data as context\n"
        "# and call predict() on the desired horizon.\n"
    )
    assert result.full_script == expected
