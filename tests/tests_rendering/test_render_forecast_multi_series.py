# Unit test render_forecast_multi_series rendering

from skforecast_ai.rendering import render_forecast_multi_series, render_forecast_multivariate
from skforecast_ai.schemas import RenderedScript

from .fixtures_rendering import (
    plan_multi_series,
    plan_multi_series_exog,
    plan_multivariate,
    profile_multi_long,
    profile_multi_long_exog,
    profile_multi_wide,
    profile_multi_wide_exog,
)


# =============================================================================
# Tests: render_forecast_multi_series — full script comparison
# =============================================================================
def test_render_forecast_multi_series_output_when_wide_format():
    """
    Test that render_forecast_multi_series produces the expected full
    script for wide-format data with ForecasterRecursiveMultiSeries.
    """
    result = render_forecast_multi_series(plan_multi_series, profile_multi_wide)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.recursive import ForecasterRecursiveMultiSeries\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Reshape to dict format (optimal for ForecasterRecursiveMultiSeries)\n"
        "series_dict = data[['series_a', 'series_b']].to_dict('series')\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "series_dict_train = {k: v.loc[:end_train] for k, v in series_dict.items()}\n"
        "series_dict_test  = {k: v.loc[v.index > end_train] for k, v in series_dict.items()}\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursiveMultiSeries(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        "    encoding  = 'ordinal',\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(series=series_dict_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set (per series)\n"
        "metrics_list = []\n"
        "for series_name in series_dict_test:\n"
        "    actual = series_dict_test[series_name].iloc[:steps]\n"
        "    mask = predictions['level'] == series_name\n"
        "    pred = predictions.loc[mask, 'pred'].values\n"
        "    metrics_list.append({\n"
        '        "series": series_name,\n'
        '        "MAE": mean_absolute_error(actual, pred),\n'
        '        "MSE": mean_squared_error(actual, pred),\n'
        '        "MASE": mean_absolute_scaled_error(\n'
        "            actual, pred, y_train=series_dict_train[series_name]\n"
        "        ),\n"
        "    })\n"
        "metrics_df = pd.DataFrame(metrics_list)\n"
        "print(metrics_df.to_string(index=False))\n"
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, retrain with all available data\n"
        "# and call predict() on the desired horizon.\n"
    )
    assert result.full_script == expected


def test_render_forecast_multi_series_output_when_long_format():
    """
    Test that render_forecast_multi_series produces the expected full
    script for long-format data using reshape_series_long_to_dict.
    """
    result = render_forecast_multi_series(plan_multi_series, profile_multi_long)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.preprocessing import reshape_series_long_to_dict\n"
        "from skforecast.recursive import ForecasterRecursiveMultiSeries\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.sort_values('date')\n"
        "\n"
        "# Reshape to dict format (optimal for ForecasterRecursiveMultiSeries)\n"
        "series_dict = reshape_series_long_to_dict(\n"
        "    data      = data,\n"
        "    series_id = 'series_id',\n"
        "    index     = 'date',\n"
        "    values    = 'value',\n"
        "    freq      = 'D',\n"
        ")\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "series_dict_train = {k: v.loc[:end_train] for k, v in series_dict.items()}\n"
        "series_dict_test  = {k: v.loc[v.index > end_train] for k, v in series_dict.items()}\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursiveMultiSeries(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        "    encoding  = 'ordinal',\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(series=series_dict_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set (per series)\n"
        "metrics_list = []\n"
        "for series_name in series_dict_test:\n"
        "    actual = series_dict_test[series_name].iloc[:steps]\n"
        "    mask = predictions['level'] == series_name\n"
        "    pred = predictions.loc[mask, 'pred'].values\n"
        "    metrics_list.append({\n"
        '        "series": series_name,\n'
        '        "MAE": mean_absolute_error(actual, pred),\n'
        '        "MSE": mean_squared_error(actual, pred),\n'
        '        "MASE": mean_absolute_scaled_error(\n'
        "            actual, pred, y_train=series_dict_train[series_name]\n"
        "        ),\n"
        "    })\n"
        "metrics_df = pd.DataFrame(metrics_list)\n"
        "print(metrics_df.to_string(index=False))\n"
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, retrain with all available data\n"
        "# and call predict() on the desired horizon.\n"
    )
    assert result.full_script == expected


# =============================================================================
# Tests: render_forecast_multivariate — full script comparison
# =============================================================================
def test_render_forecast_multivariate_output_when_wide_format():
    """
    Test that render_forecast_multivariate produces the expected full
    script for ForecasterDirectMultiVariate with level parameter.
    """
    result = render_forecast_multivariate(plan_multivariate, profile_multi_wide)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.direct import ForecasterDirectMultiVariate\n"
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
        "# Create forecaster\n"
        "forecaster = ForecasterDirectMultiVariate(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    level     = 'series_a',\n"
        "    steps     = 5,\n"
        "    lags      = 7,\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(series=data_train)\n"
        "\n"
        "# Predict\n"
        "steps = 5\n"
        "predictions = forecaster.predict(steps=steps)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set\n"
        "actual = data_test['series_a'].iloc[:steps]\n"
        "mae = mean_absolute_error(actual, predictions['pred'])\n"
        "mse = mean_squared_error(actual, predictions['pred'])\n"
        "mase = mean_absolute_scaled_error(\n"
        "    y_true  = actual,\n"
        "    y_pred  = predictions['pred'],\n"
        "    y_train = data_train['series_a'],\n"
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
# Tests: render_forecast_multi_series — exog enabled
# =============================================================================
def test_render_forecast_multi_series_output_when_wide_format_with_exog():
    """
    Test that render_forecast_multi_series produces correct exog handling
    for wide-format data with exogenous variables.
    """
    result = render_forecast_multi_series(plan_multi_series_exog, profile_multi_wide_exog)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.recursive import ForecasterRecursiveMultiSeries\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Reshape to dict format (optimal for ForecasterRecursiveMultiSeries)\n"
        "series_dict = data[['series_a', 'series_b']].to_dict('series')\n"
        "\n"
        "exog = data[['promo', 'holiday']]\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "series_dict_train = {k: v.loc[:end_train] for k, v in series_dict.items()}\n"
        "series_dict_test  = {k: v.loc[v.index > end_train] for k, v in series_dict.items()}\n"
        "exog_train = exog.loc[:end_train]\n"
        "exog_test  = exog.loc[exog.index > end_train]\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursiveMultiSeries(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        "    encoding  = 'ordinal',\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(series=series_dict_train, exog=exog_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps, exog=exog_test)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set (per series)\n"
        "metrics_list = []\n"
        "for series_name in series_dict_test:\n"
        "    actual = series_dict_test[series_name].iloc[:steps]\n"
        "    mask = predictions['level'] == series_name\n"
        "    pred = predictions.loc[mask, 'pred'].values\n"
        "    metrics_list.append({\n"
        '        "series": series_name,\n'
        '        "MAE": mean_absolute_error(actual, pred),\n'
        '        "MSE": mean_squared_error(actual, pred),\n'
        '        "MASE": mean_absolute_scaled_error(\n'
        "            actual, pred, y_train=series_dict_train[series_name]\n"
        "        ),\n"
        "    })\n"
        "metrics_df = pd.DataFrame(metrics_list)\n"
        "print(metrics_df.to_string(index=False))\n"
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, retrain with all available data\n"
        "# and provide future exogenous values covering the forecast horizon.\n"
    )
    assert result.full_script == expected


def test_render_forecast_multi_series_output_when_long_format_with_exog():
    """
    Test that render_forecast_multi_series produces correct reshape_exog_long_to_dict
    handling for long-format data with exogenous variables.
    """
    result = render_forecast_multi_series(plan_multi_series_exog, profile_multi_long_exog)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.preprocessing import reshape_series_long_to_dict, reshape_exog_long_to_dict\n"
        "from skforecast.recursive import ForecasterRecursiveMultiSeries\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.sort_values('date')\n"
        "\n"
        "# Reshape to dict format (optimal for ForecasterRecursiveMultiSeries)\n"
        "series_dict = reshape_series_long_to_dict(\n"
        "    data      = data,\n"
        "    series_id = 'series_id',\n"
        "    index     = 'date',\n"
        "    values    = 'value',\n"
        "    freq      = 'D',\n"
        ")\n"
        "\n"
        "exog_dict = reshape_exog_long_to_dict(\n"
        "    data      = data[['series_id', 'date', 'promo']],\n"
        "    series_id = 'series_id',\n"
        "    index     = 'date',\n"
        "    freq      = 'D',\n"
        ")\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "series_dict_train = {k: v.loc[:end_train] for k, v in series_dict.items()}\n"
        "series_dict_test  = {k: v.loc[v.index > end_train] for k, v in series_dict.items()}\n"
        "exog_dict_train = {k: v.loc[:end_train] for k, v in exog_dict.items()}\n"
        "exog_dict_test  = {k: v.loc[v.index > end_train] for k, v in exog_dict.items()}\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursiveMultiSeries(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        "    encoding  = 'ordinal',\n"
        ")\n"
        "\n"
        "# Fit\n"
        "forecaster.fit(series=series_dict_train, exog=exog_dict_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps, exog=exog_dict_test)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set (per series)\n"
        "metrics_list = []\n"
        "for series_name in series_dict_test:\n"
        "    actual = series_dict_test[series_name].iloc[:steps]\n"
        "    mask = predictions['level'] == series_name\n"
        "    pred = predictions.loc[mask, 'pred'].values\n"
        "    metrics_list.append({\n"
        '        "series": series_name,\n'
        '        "MAE": mean_absolute_error(actual, pred),\n'
        '        "MSE": mean_squared_error(actual, pred),\n'
        '        "MASE": mean_absolute_scaled_error(\n'
        "            actual, pred, y_train=series_dict_train[series_name]\n"
        "        ),\n"
        "    })\n"
        "metrics_df = pd.DataFrame(metrics_list)\n"
        "print(metrics_df.to_string(index=False))\n"
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, retrain with all available data\n"
        "# and provide future exogenous values covering the forecast horizon.\n"
    )
    assert result.full_script == expected
