import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_absolute_percentage_error
from skforecast.metrics import mean_absolute_scaled_error
from sklearn.linear_model import Ridge
from skforecast.preprocessing import RollingFeatures
from skforecast.recursive import ForecasterRecursive

# Load data
data = pd.read_csv('https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/h2o_exog.csv')

data['fecha'] = pd.to_datetime(data['fecha'])
data = data.set_index('fecha')
data = data.asfreq('MS')
data = data.sort_index()

# Train/test split
end_train = '2005-03-01'  # 80% of data, adjust to change the split point
data_train = data.loc[:end_train]
data_test  = data.loc[data.index > end_train]
exog_features = ['exog_1', 'exog_2']

print(
    f"Train dates : {data_train.index.min()} --- {data_train.index.max()}  (n={len(data_train)})"
)
print(
    f"Test dates  : {data_test.index.min()} --- {data_test.index.max()}  (n={len(data_test)})"
)

window_features = RollingFeatures(
    stats        = ['mean', 'std', 'mean'],
    window_sizes = [12, 12, 24],
)

transformer_exog = StandardScaler()

# Create forecaster
forecaster = ForecasterRecursive(
    estimator            = Ridge(),
    lags                 = [1, 8, 9, 10, 11, 12, 13, 14],
    window_features      = window_features,
    transformer_y        = StandardScaler(),
    transformer_exog     = transformer_exog,
    categorical_features = 'auto',
    dropna_from_series   = False,
)

# Fit
forecaster.fit(
    y                         = data_train['y'],
    exog                      = data_train[exog_features],
    store_in_sample_residuals = True,
)

# Predict intervals
steps = 24
predictions = forecaster.predict_interval(
    steps    = steps,
    exog     = data_test[exog_features],
    method   = 'bootstrapping',
    interval = [10, 90],
)
print(predictions)

# Evaluate on test set
actual = data_test['y'].iloc[:steps]
mae = mean_absolute_error(actual, predictions['pred'])
mse = mean_squared_error(actual, predictions['pred'])
mase = mean_absolute_scaled_error(
    y_true  = actual,
    y_pred  = predictions['pred'],
    y_train = data_train['y'],
)
mape = mean_absolute_percentage_error(actual, predictions['pred'])

print(f"MAE  : {mae:.4f}")
print(f"MSE  : {mse:.4f}")
print(f"MASE : {mase:.4f}")
print(f"MAPE : {mape:.4f}")

# NOTE: This script uses a train/test split for demonstration purposes.
# For production forecasting, retrain with all available data
# and provide future exogenous values covering the forecast horizon.
