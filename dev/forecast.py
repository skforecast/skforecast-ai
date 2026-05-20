import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from lightgbm import LGBMRegressor
from skforecast.metrics import mean_absolute_scaled_error
from skforecast.preprocessing import RollingFeatures
from skforecast.recursive import ForecasterRecursiveMultiSeries

# Load data
data = pd.read_csv('https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/simulated_items_sales.csv')

data['date'] = pd.to_datetime(data['date'])
data = data.set_index('date')
data = data.asfreq('D')
data = data.sort_index()

# Reshape to dict format (optimal for ForecasterRecursiveMultiSeries)
series_dict = data[['item_1', 'item_2', 'item_3']].to_dict('series')

# Train/test split
end_train = '2014-05-26'  # 80% of data, adjust to change the split point
series_dict_train = {k: v.loc[:end_train] for k, v in series_dict.items()}
series_dict_test  = {k: v.loc[v.index > end_train] for k, v in series_dict.items()}

window_features = RollingFeatures(
    stats        = ['mean', 'std', 'mean'],
    window_sizes = [7, 7, 365],
)

# Create forecaster
forecaster = ForecasterRecursiveMultiSeries(
    estimator            = LGBMRegressor(random_state=123, verbose=-1),
    lags                 = [1, 3, 7, 8, 9, 13, 14, 15, 20, 21, 23, 27, 28, 29, 34, 36, 43, 46, 48, 49, 50, 56, 67, 320, 322, 342, 354, 364, 365, 371, 372, 377, 400],
    encoding             = 'ordinal',
    window_features      = window_features,
    categorical_features = 'auto',
    dropna_from_series   = False,
)

# Fit
forecaster.fit(series=series_dict_train)

# Predict
steps = 30
predictions = forecaster.predict(steps=steps)
print(predictions)

# Evaluate on test set (per series)
metrics_list = []
for series_name in series_dict_test:
    actual = series_dict_test[series_name].iloc[:steps]
    mask = predictions['level'] == series_name
    pred = predictions.loc[mask, 'pred'].values
    metrics_list.append({
        "series": series_name,
        "MAE": mean_absolute_error(actual, pred),
        "MSE": mean_squared_error(actual, pred),
        "MASE": mean_absolute_scaled_error(
            actual, pred, y_train=series_dict_train[series_name]
        ),
    })
metrics_df = pd.DataFrame(metrics_list)
print(metrics_df.to_string(index=False))

# NOTE: This script uses a train/test split for demonstration purposes.
# For production forecasting, retrain with all available data
# and call predict() on the desired horizon.
