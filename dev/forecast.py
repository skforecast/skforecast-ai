import pandas as pd
from skforecast.datasets import fetch_dataset
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_absolute_percentage_error
from skforecast.metrics import mean_absolute_scaled_error
from lightgbm import LGBMRegressor
from skforecast.preprocessing import RollingFeatures, CalendarFeatures
from skforecast.recursive import ForecasterRecursive

# Load data
data = fetch_dataset('bike_sharing', raw=True)
data = data[['date_time', 'users', 'holiday', 'weather', 'temp']]
data['date_time'] = pd.to_datetime(data['date_time'], format='%Y-%m-%d %H:%M:%S')
data = data.set_index('date_time')

data = data.asfreq('h')
data = data.sort_index()

# Train/test split
end_train = '2012-08-07 18:00:00'  # 80% of data, adjust to change the split point
data_train = data.loc[:end_train]
data_test  = data.loc[data.index > end_train]
exog_features = ['holiday', 'weather', 'temp']

print(
    f"Train dates : {data_train.index.min()} --- {data_train.index.max()}  (n={len(data_train)})"
)
print(
    f"Test dates  : {data_test.index.min()} --- {data_test.index.max()}  (n={len(data_test)})"
)

window_features = RollingFeatures(
    stats        = ['mean', 'std', 'mean', 'mean', 'mean'],
    window_sizes = [22, 22, 24, 48, 72],
)

calendar_features = CalendarFeatures(
    features = ['hour', 'day_of_week', 'weekend', 'month'],
    encoding = None,
)

# Create forecaster
forecaster = ForecasterRecursive(
    estimator            = LGBMRegressor(random_state=123, verbose=-1),
    lags                 = [1, 2, 3, 4, 5, 6, 8, 9, 10, 12, 13, 15, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 39, 41, 43, 48, 50, 57, 63, 64, 66, 69, 70, 71, 73, 74, 94, 95, 96, 97, 98, 111, 112, 115, 117, 118, 119, 120, 121, 122, 132, 135, 136, 137, 140, 141, 142, 143, 144, 145, 147, 152, 159, 160, 161, 165, 166, 167, 168, 169, 176, 179, 192, 193, 217, 303, 309, 310, 311, 313, 327, 328, 329, 333, 334, 335, 336, 337, 344, 383, 385, 481, 496, 502, 503, 504],
    window_features      = window_features,
    calendar_features    = calendar_features,
    categorical_features = 'auto',
    dropna_from_series   = False,
)

# Fit
forecaster.fit(y=data_train['users'], exog=data_train[exog_features])

# Predict
steps = 36
predictions = forecaster.predict(steps=steps, exog=data_test[exog_features])
print(predictions)

# Evaluate on test set
actual = data_test['users'].iloc[:steps]
mae = mean_absolute_error(actual, predictions)
mse = mean_squared_error(actual, predictions)
mase = mean_absolute_scaled_error(
    y_true  = actual,
    y_pred  = predictions,
    y_train = data_train['users'],
)
mape = mean_absolute_percentage_error(actual, predictions)

print(f"MAE  : {mae:.4f}")
print(f"MSE  : {mse:.4f}")
print(f"MASE : {mase:.4f}")
print(f"MAPE : {mape:.4f}")
