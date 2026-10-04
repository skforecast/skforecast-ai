# Unit test render_forecast_foundation rendering

from skforecast_ai.rendering import render_forecast_foundation
from skforecast_ai.schemas import RenderedScript

from .fixtures_rendering import (
    plan_foundation,
    plan_foundation_exog_no_end_train,
    plan_foundation_numeric_covariates,
    plan_foundation_numeric_covariates_no_end_train,
    plan_foundation_with_intervals,
    profile_multi_long,
    profile_multi_long_exog,
    profile_multi_wide,
    profile_multi_wide_exog,
    profile_single_mixed_exog,
    profile_single_no_exog,
    profile_single_unused_columns,
)


# =============================================================================
# Tests: render_forecast_foundation: full script comparison
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
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "series_train = series.loc[:end_train]\n"
        "series_test  = series.loc[series.index > end_train]\n"
        "\n"
        "# Create foundation model (chronos-2-small)\n"
        "estimator = FoundationModel(\n"
        "    model_id       = 'autogluon/chronos-2-small',\n"
        "    context_length = 512,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=estimator)\n"
        "\n"
        "# Fit (stores context only, no training)\n"
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
    Test that render_forecast_foundation produces predict_interval code
    when interval_method is 'native', so the predictions have the `pred`,
    `lower_bound` and `upper_bound` columns of every other forecaster.
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
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "series_train = series.loc[:end_train]\n"
        "series_test  = series.loc[series.index > end_train]\n"
        "\n"
        "# Create foundation model (chronos-2-small)\n"
        "estimator = FoundationModel(\n"
        "    model_id       = 'autogluon/chronos-2-small',\n"
        "    context_length = 512,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=estimator)\n"
        "\n"
        "# Fit (stores context only, no training)\n"
        "forecaster.fit(series=series_train)\n"
        "\n"
        "# Predict intervals (native quantiles)\n"
        "steps = 10\n"
        "predictions = forecaster.predict_interval(\n"
        "    steps    = steps,\n"
        "    interval = [0.1, 0.9],\n"
        ")\n"
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


# =============================================================================
# Tests: render_forecast_foundation: capabilities of the foundation model
# =============================================================================
def test_render_forecast_foundation_output_when_model_only_accepts_numeric_covariates():
    """
    Test that render_forecast_foundation loads the model of plan.estimator
    with the default context length of its adapter (2048 for TimesFM 3.0),
    and excludes the categorical exog, with a note, when the model only
    accepts numeric covariates.
    """
    result = render_forecast_foundation(
        plan_foundation_numeric_covariates, profile_single_mixed_exog
    )

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
        "# Categorical exog excluded (holiday): 'google/timesfm-3.0-pytorch' only accepts numeric covariates\n"
        "exog = data[['temp']]\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "series_train = series.loc[:end_train]\n"
        "series_test  = series.loc[series.index > end_train]\n"
        "exog_train = exog.loc[:end_train]\n"
        "exog_test  = exog.loc[exog.index > end_train]\n"
        "\n"
        "# Create foundation model (timesfm-3.0-pytorch)\n"
        "estimator = FoundationModel(\n"
        "    model_id       = 'google/timesfm-3.0-pytorch',\n"
        "    context_length = 2048,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=estimator)\n"
        "\n"
        "# Fit (stores context only, no training)\n"
        "forecaster.fit(series=series_train, exog=exog_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps, exog=exog_test)\n"
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
        "# and provide future exogenous values covering the forecast horizon.\n"
    )
    assert result.full_script == expected


def test_render_forecast_foundation_output_when_prediction_mode_excludes_categorical_exog():
    """
    Test that in prediction mode the future exog is restricted to the
    numeric columns, since the loaded file also holds the categorical ones
    that the model cannot take.
    """
    result = render_forecast_foundation(
        plan_foundation_numeric_covariates_no_end_train, profile_single_mixed_exog
    )

    expected = (
        "import pandas as pd\n"
        "from skforecast.foundation import FoundationModel, ForecasterFoundation\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "# Load future exogenous variables covering the forecast horizon\n"
        "exog_future = pd.read_csv('exog_future.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "exog_future['date'] = pd.to_datetime(exog_future['date'])\n"
        "exog_future = exog_future.set_index('date')\n"
        "exog_future = exog_future.asfreq('D')\n"
        "exog_future = exog_future.sort_index()\n"
        "\n"
        "series = data['sales']\n"
        "# Categorical exog excluded (holiday): 'google/timesfm-3.0-pytorch' only accepts numeric covariates\n"
        "exog = data[['temp']]\n"
        "\n"
        "# Create foundation model (timesfm-3.0-pytorch)\n"
        "estimator = FoundationModel(\n"
        "    model_id       = 'google/timesfm-3.0-pytorch',\n"
        "    context_length = 2048,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=estimator)\n"
        "\n"
        "# Fit (stores context only, no training)\n"
        "forecaster.fit(series=series, exog=exog)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps, exog=exog_future[['temp']])\n"
        "print(predictions)\n"
    )
    assert result.full_script == expected


def test_render_forecast_foundation_output_when_prediction_mode_with_unused_columns():
    """
    Test that in prediction mode the future exog is restricted to the
    columns of the profile when the profile leaves columns out, since the
    loaded file can also hold them and the model takes every column it is
    given.
    """
    result = render_forecast_foundation(
        plan_foundation_exog_no_end_train, profile_single_unused_columns
    )

    expected = (
        "import pandas as pd\n"
        "from skforecast.foundation import FoundationModel, ForecasterFoundation\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "# Load future exogenous variables covering the forecast horizon\n"
        "exog_future = pd.read_csv('exog_future.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "exog_future['date'] = pd.to_datetime(exog_future['date'])\n"
        "exog_future = exog_future.set_index('date')\n"
        "exog_future = exog_future.asfreq('D')\n"
        "exog_future = exog_future.sort_index()\n"
        "\n"
        "series = data['sales']\n"
        "exog = data[['temp']]\n"
        "\n"
        "# Create foundation model (chronos-2-small)\n"
        "estimator = FoundationModel(\n"
        "    model_id       = 'autogluon/chronos-2-small',\n"
        "    context_length = 512,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=estimator)\n"
        "\n"
        "# Fit (stores context only, no training)\n"
        "forecaster.fit(series=series, exog=exog)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps, exog=exog_future[['temp']])\n"
        "print(predictions)\n"
    )
    assert result.full_script == expected


# =============================================================================
# Tests: render_forecast_foundation: multi-series
# =============================================================================
def test_render_forecast_foundation_output_when_multi_series():
    """
    Test that render_forecast_foundation passes wide multi-series data as a
    dict with one entry per series, splits it per series, predicts every
    series and evaluates each one.
    """
    result = render_forecast_foundation(plan_foundation, profile_multi_wide)

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
        "# Reshape to dict format (one entry per series)\n"
        "series_dict = data[['series_a', 'series_b']].to_dict('series')\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "series_dict_train = {k: v.loc[:end_train] for k, v in series_dict.items()}\n"
        "series_dict_test  = {k: v.loc[v.index > end_train] for k, v in series_dict.items()}\n"
        "\n"
        "# Create foundation model (chronos-2-small)\n"
        "estimator = FoundationModel(\n"
        "    model_id       = 'autogluon/chronos-2-small',\n"
        "    context_length = 512,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=estimator)\n"
        "\n"
        "# Fit (stores context only, no training)\n"
        "forecaster.fit(series=series_dict_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set (per series)\n"
        "metrics_list = []\n"
        "for level in predictions['level'].unique():\n"
        "    mask = predictions['level'] == level\n"
        "    pred = predictions.loc[mask, 'pred'].values\n"
        "    actual = series_dict_test[level].iloc[:steps]\n"
        "    metrics_list.append({\n"
        '        "series": level,\n'
        '        "MAE": mean_absolute_error(actual, pred),\n'
        '        "MSE": mean_squared_error(actual, pred),\n'
        '        "MASE": mean_absolute_scaled_error(\n'
        "            actual, pred, y_train=series_dict_train[level]\n"
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


def test_render_forecast_foundation_output_when_multi_series_long_format():
    """
    Test that render_forecast_foundation reshapes long-format data into a
    dict with one entry per series with `reshape_series_long_to_dict`.
    """
    result = render_forecast_foundation(plan_foundation, profile_multi_long)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from skforecast.preprocessing import reshape_series_long_to_dict\n"
        "from skforecast.foundation import FoundationModel, ForecasterFoundation\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.sort_values('date')\n"
        "\n"
        "# Reshape to dict format (one entry per series)\n"
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
        "# Create foundation model (chronos-2-small)\n"
        "estimator = FoundationModel(\n"
        "    model_id       = 'autogluon/chronos-2-small',\n"
        "    context_length = 512,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=estimator)\n"
        "\n"
        "# Fit (stores context only, no training)\n"
        "forecaster.fit(series=series_dict_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set (per series)\n"
        "metrics_list = []\n"
        "for level in predictions['level'].unique():\n"
        "    mask = predictions['level'] == level\n"
        "    pred = predictions.loc[mask, 'pred'].values\n"
        "    actual = series_dict_test[level].iloc[:steps]\n"
        "    metrics_list.append({\n"
        '        "series": level,\n'
        '        "MAE": mean_absolute_error(actual, pred),\n'
        '        "MSE": mean_squared_error(actual, pred),\n'
        '        "MASE": mean_absolute_scaled_error(\n'
        "            actual, pred, y_train=series_dict_train[level]\n"
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


def test_render_forecast_foundation_output_when_multi_series_long_format_with_exog():
    """
    Test that long-format exogenous variables are reshaped into one frame
    per series with `reshape_exog_long_to_dict` and split like the series.
    """
    result = render_forecast_foundation(plan_foundation_numeric_covariates, profile_multi_long_exog)

    expected = (
        "import pandas as pd\n"
        "from sklearn.metrics import mean_absolute_error, mean_squared_error\n"
        "from skforecast.metrics import mean_absolute_scaled_error\n"
        "from skforecast.preprocessing import reshape_series_long_to_dict, reshape_exog_long_to_dict\n"
        "from skforecast.foundation import FoundationModel, ForecasterFoundation\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.sort_values('date')\n"
        "\n"
        "# Reshape to dict format (one entry per series)\n"
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
        "# Create foundation model (timesfm-3.0-pytorch)\n"
        "estimator = FoundationModel(\n"
        "    model_id       = 'google/timesfm-3.0-pytorch',\n"
        "    context_length = 2048,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=estimator)\n"
        "\n"
        "# Fit (stores context only, no training)\n"
        "forecaster.fit(series=series_dict_train, exog=exog_dict_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps, exog=exog_dict_test)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set (per series)\n"
        "metrics_list = []\n"
        "for level in predictions['level'].unique():\n"
        "    mask = predictions['level'] == level\n"
        "    pred = predictions.loc[mask, 'pred'].values\n"
        "    actual = series_dict_test[level].iloc[:steps]\n"
        "    metrics_list.append({\n"
        '        "series": level,\n'
        '        "MAE": mean_absolute_error(actual, pred),\n'
        '        "MSE": mean_squared_error(actual, pred),\n'
        '        "MASE": mean_absolute_scaled_error(\n'
        "            actual, pred, y_train=series_dict_train[level]\n"
        "        ),\n"
        "    })\n"
        "metrics_df = pd.DataFrame(metrics_list)\n"
        "print(metrics_df.to_string(index=False))\n"
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, pass all available data as context\n"
        "# and provide future exogenous values covering the forecast horizon.\n"
    )
    assert result.full_script == expected


def test_render_forecast_foundation_output_when_multi_series_long_format_prediction_mode():
    """
    Test that in prediction mode the future exogenous variables, also in
    long format, have their dates parsed like the data and are reshaped
    into one frame per series.
    """
    result = render_forecast_foundation(plan_foundation_numeric_covariates_no_end_train, profile_multi_long_exog)

    expected = (
        "import pandas as pd\n"
        "from skforecast.preprocessing import reshape_series_long_to_dict, reshape_exog_long_to_dict\n"
        "from skforecast.foundation import FoundationModel, ForecasterFoundation\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "# Load future exogenous variables covering the forecast horizon\n"
        "exog_future = pd.read_csv('exog_future.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.sort_values('date')\n"
        "\n"
        "exog_future['date'] = pd.to_datetime(exog_future['date'])\n"
        "exog_future = exog_future.sort_values('date')\n"
        "\n"
        "# Reshape to dict format (one entry per series)\n"
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
        "# Reshape future exogenous variables to dict format\n"
        "exog_future_dict = reshape_exog_long_to_dict(\n"
        "    data      = exog_future[['series_id', 'date', 'promo']],\n"
        "    series_id = 'series_id',\n"
        "    index     = 'date',\n"
        "    freq      = 'D',\n"
        ")\n"
        "\n"
        "# Create foundation model (timesfm-3.0-pytorch)\n"
        "estimator = FoundationModel(\n"
        "    model_id       = 'google/timesfm-3.0-pytorch',\n"
        "    context_length = 2048,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=estimator)\n"
        "\n"
        "# Fit (stores context only, no training)\n"
        "forecaster.fit(series=series_dict, exog=exog_dict)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps, exog=exog_future_dict)\n"
        "print(predictions)\n"
    )
    assert result.full_script == expected


def test_render_forecast_foundation_output_when_multi_series_excludes_categorical_exog():
    """
    Test that wide multi-series data shares one exog frame across series
    and excludes, with a note, the categorical exog a model that only
    accepts numeric covariates cannot take.
    """
    result = render_forecast_foundation(plan_foundation_numeric_covariates, profile_multi_wide_exog)

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
        "# Reshape to dict format (one entry per series)\n"
        "series_dict = data[['series_a', 'series_b']].to_dict('series')\n"
        "\n"
        "# Categorical exog excluded (holiday): 'google/timesfm-3.0-pytorch' only accepts numeric covariates\n"
        "exog = data[['promo']]\n"
        "\n"
        "# Train/test split\n"
        "end_train = '2023-03-12'  # last training date, adjust to change the split point\n"
        "series_dict_train = {k: v.loc[:end_train] for k, v in series_dict.items()}\n"
        "series_dict_test  = {k: v.loc[v.index > end_train] for k, v in series_dict.items()}\n"
        "exog_train = exog.loc[:end_train]\n"
        "exog_test  = exog.loc[exog.index > end_train]\n"
        "\n"
        "# Create foundation model (timesfm-3.0-pytorch)\n"
        "estimator = FoundationModel(\n"
        "    model_id       = 'google/timesfm-3.0-pytorch',\n"
        "    context_length = 2048,\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterFoundation(estimator=estimator)\n"
        "\n"
        "# Fit (stores context only, no training)\n"
        "forecaster.fit(series=series_dict_train, exog=exog_train)\n"
        "\n"
        "# Predict\n"
        "steps = 10\n"
        "predictions = forecaster.predict(steps=steps, exog=exog_test)\n"
        "print(predictions)\n"
        "\n"
        "# Evaluate on test set (per series)\n"
        "metrics_list = []\n"
        "for level in predictions['level'].unique():\n"
        "    mask = predictions['level'] == level\n"
        "    pred = predictions.loc[mask, 'pred'].values\n"
        "    actual = series_dict_test[level].iloc[:steps]\n"
        "    metrics_list.append({\n"
        '        "series": level,\n'
        '        "MAE": mean_absolute_error(actual, pred),\n'
        '        "MSE": mean_squared_error(actual, pred),\n'
        '        "MASE": mean_absolute_scaled_error(\n'
        "            actual, pred, y_train=series_dict_train[level]\n"
        "        ),\n"
        "    })\n"
        "metrics_df = pd.DataFrame(metrics_list)\n"
        "print(metrics_df.to_string(index=False))\n"
        "\n"
        "# NOTE: This script uses a train/test split for demonstration purposes.\n"
        "# For production forecasting, pass all available data as context\n"
        "# and provide future exogenous values covering the forecast horizon.\n"
    )
    assert result.full_script == expected
