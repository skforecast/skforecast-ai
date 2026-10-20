# Fixtures for the interval coverage tests (execution/interval_coverage)
#
# Metrics and predictions shaped like those of the backtesting of skforecast
# 0.27 with a prediction interval: the `coverage` and `interval_width`
# columns come after the requested metric, and multi-series metrics add the
# aggregated rows `average`, `weighted_average` and `pooling`.

import numpy as np
import pandas as pd


# Prediction interval of the plan (nominal coverage 0.8)
interval = [0.1, 0.9]


# --- Single series ---------------------------------------------------------

predictions_single_20 = pd.DataFrame({
    "pred": np.ones(20),
    "lower_bound": np.zeros(20),
    "upper_bound": np.full(20, 2.0),
})
predictions_single_200 = pd.DataFrame({
    "pred": np.ones(200),
    "lower_bound": np.zeros(200),
    "upper_bound": np.full(200, 2.0),
})
predictions_single_400 = pd.DataFrame({
    "pred": np.ones(400),
    "lower_bound": np.zeros(400),
    "upper_bound": np.full(400, 2.0),
})

# Same as `predictions_single_200` but the lower bound of 3 predictions and
# the upper bound of 2 others are missing (195 predictions with both bounds)
predictions_single_200_nan = predictions_single_200.copy()
predictions_single_200_nan.loc[[0, 1, 2], "lower_bound"] = np.nan
predictions_single_200_nan.loc[[3, 4], "upper_bound"] = np.nan

# Foundation model: quantile columns instead of lower_bound / upper_bound.
# 50 predictions, the upper quantile of one of them is missing.
predictions_foundation_50 = pd.DataFrame({
    "pred": np.ones(50),
    "q_0.1": np.zeros(50),
    "q_0.9": np.full(50, 2.0),
})
predictions_foundation_50.loc[7, "q_0.9"] = np.nan

metrics_single_06 = pd.DataFrame({
    "mean_absolute_error": [1.5],
    "coverage": [0.6],
    "interval_width": [4.0],
})
metrics_single_07 = pd.DataFrame({
    "mean_absolute_error": [1.5],
    "coverage": [0.7],
    "interval_width": [4.0],
})
metrics_single_078 = pd.DataFrame({
    "mean_absolute_error": [1.5],
    "coverage": [0.78],
    "interval_width": [4.0],
})
metrics_single_084 = pd.DataFrame({
    "mean_absolute_error": [1.5],
    "coverage": [0.84],
    "interval_width": [3.0],
})
metrics_single_no_interval = pd.DataFrame({
    "mean_absolute_error": [1.5],
})
metrics_single_nan_coverage = pd.DataFrame({
    "mean_absolute_error": [1.5],
    "coverage": [np.nan],
    "interval_width": [np.nan],
})


# --- Multi series: 3 series of 100 predictions -----------------------------

predictions_multi_3 = pd.DataFrame({
    "level": np.repeat(["a", "b", "c"], 100),
    "pred": np.ones(300),
    "lower_bound": np.zeros(300),
    "upper_bound": np.full(300, 2.0),
})

# Only series 'b' is clearly below 0.8 (threshold with n=100 is 0.72)
metrics_multi_3 = pd.DataFrame({
    "levels": ["a", "b", "c", "average", "weighted_average", "pooling"],
    "mean_absolute_error": [1.0, 2.0, 3.0, 2.0, 2.0, 2.0],
    "coverage": [0.8, 0.5, 0.82, 0.7067, 0.7067, 0.7067],
    "interval_width": [4.0, 3.0, 5.0, 4.0, 4.0, 4.0],
})

# Same series with a NaN coverage in 'c'
metrics_multi_3_nan_coverage = pd.DataFrame({
    "levels": ["a", "b", "c", "average", "weighted_average", "pooling"],
    "mean_absolute_error": [1.0, 2.0, 3.0, 2.0, 2.0, 2.0],
    "coverage": [0.8, 0.5, np.nan, 0.65, 0.65, 0.65],
    "interval_width": [4.0, 3.0, np.nan, 3.5, 3.5, 3.5],
})

# Two series of 100 predictions
predictions_multi_2 = predictions_multi_3[
    predictions_multi_3["level"].isin(["a", "b"])
].reset_index(drop=True)
metrics_multi_2 = pd.DataFrame({
    "levels": ["a", "b", "average", "weighted_average", "pooling"],
    "mean_absolute_error": [1.0, 2.0, 1.5, 1.5, 1.5],
    "coverage": [0.8, 0.5, 0.65, 0.65, 0.65],
    "interval_width": [4.0, 3.0, 3.5, 3.5, 3.5],
})

# Series 'a' has 5 predictions, one with a missing lower bound (4 with both
# bounds); series 'b' has 3 predictions, all with a missing upper bound.
predictions_multi_nan_bounds = pd.DataFrame({
    "level": ["a", "a", "a", "a", "a", "b", "b", "b"],
    "pred": np.ones(8),
    "lower_bound": [0.0, 0.0, np.nan, 0.0, 0.0, 0.0, 0.0, 0.0],
    "upper_bound": [2.0, 2.0, 2.0, 2.0, 2.0, np.nan, np.nan, np.nan],
})
metrics_multi_nan_bounds = pd.DataFrame({
    "levels": ["a", "b", "average", "weighted_average", "pooling"],
    "mean_absolute_error": [1.0, 2.0, 1.5, 1.5, 1.5],
    "coverage": [0.75, 0.5, 0.625, 0.625, 0.625],
    "interval_width": [4.0, 3.0, 3.5, 3.5, 3.5],
})


# --- Multi series: 7 series, all clearly below 0.8 -------------------------

_levels_7 = ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]
predictions_multi_7 = pd.DataFrame({
    "level": np.repeat(_levels_7, 100),
    "pred": np.ones(700),
    "lower_bound": np.zeros(700),
    "upper_bound": np.full(700, 2.0),
})
metrics_multi_7 = pd.DataFrame({
    "levels": _levels_7 + ["average", "weighted_average", "pooling"],
    "mean_absolute_error": [1.0] * 10,
    "coverage": [0.55, 0.30, 0.60, 0.40, 0.35, 0.50, 0.45, 0.45, 0.45, 0.45],
    "interval_width": [2.0] * 10,
})


# --- Multi series: 12 series of 100 predictions ----------------------------

_levels_12 = [f"s{i:02d}" for i in range(1, 13)]
predictions_multi_12 = pd.DataFrame({
    "level": np.repeat(_levels_12, 100),
    "pred": np.ones(1200),
    "lower_bound": np.zeros(1200),
    "upper_bound": np.full(1200, 2.0),
})
metrics_multi_12 = pd.DataFrame({
    "levels": _levels_12 + ["average", "weighted_average", "pooling"],
    "mean_absolute_error": [1.0] * 15,
    "coverage": [
        0.90, 0.55, 0.85, 0.60, 0.80, 0.65, 0.78, 0.70, 0.82, 0.75, 0.88, 0.72,
        0.75, 0.75, 0.75,
    ],
    "interval_width": [2.0] * 15,
})
