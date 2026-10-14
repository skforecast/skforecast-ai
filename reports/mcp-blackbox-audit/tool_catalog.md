# Tool catalog as seen by a client

## Server instructions

```
Deterministic time series forecasting with skforecast. Every decision (forecaster, estimator, lags, metric, cross-validation) comes from rules, never from a language model, and is reproducible.

The server reads CSV files ('.csv', '.tsv', '.csv.gz', '.tsv.gz'; separated by ',', ';' or tabulators, which `profile` detects) only inside '<ALLOW_DIR>' (subdirectories included). Tools take absolute paths: a file the user names by a relative path or by its name is looked for there, so build the path from that directory instead of searching the file system. When the file is outside it, stop and answer the user: only they can copy it there or restart the server with another `--allow-dir`. Never copy, move or rewrite it into that directory yourself (no `cp`, no reading it and writing it again).

Workflow: `profile` a CSV file (absolute path inside that directory) -> `plan` with a horizon (`steps`) -> optionally `refine_plan` -> `create_cv` (check its `cost`) -> `backtest` -> optionally `compare` -> `forecast`. Each tool returns an `id`; later tools take ids, never objects. Every response has a plain-text `summary` and the warnings of the call in `notices`; it never holds rows of data, which go to CSV files (`files`). What you do see of the data: the messages of errors and warnings can name columns and series and quote up to 5 values, a traceback of `get_failure` can quote values, and scripts and plan summaries name the path of the file. `get_code` returns the script that ran, `get_failure` the traceback of a failure, `describe_object` the response that created an object, `list_objects` the ids registered now.

Errors are JSON objects with `code`, `message`, `field`, `hint` and `details`. Dates are ISO 8601 text ('2012-01-01'); counts are numbers.

Rules (the skforecast-ai-forecasting skill has the rest):
1. Trust: a `compare` whose winner beats the baseline > a `backtest` > a `forecast` with `test_size` (one window) > a `forecast` of the future (no error measure). Without a baseline (several series, or a target with gaps), judge each series by `mean_absolute_scaled_error` in the CSV of metrics and name the worst one: the summary only has the average. Below 1 it beats the one-step naive forecast (repeat the previous value) on the training data, which is not a seasonal naive forecast nor the baseline of `compare`. Never invent a number, nor derive one: no percentage, ratio or difference that a response does not give.
2. Cost: read `cost` of `create_cv` before running. Before a run above 50 estimator fits, stop: tell the user the number of fits and the cheaper strategies (an integer `refit`, fewer folds, `refit=false`) and run the expensive one only if they choose it. Asking to retrain is not that choice.
3. Read `notices` before reporting and tell the user about data problems (missing dates, rows without target) and plan warnings.
4. `compare` without `interval` uses the interval of the plan of the strategy; with an asymmetric one there is no baseline ([0.1, 0.9] is symmetric).
5. Never modify the user's data, nor write data for them: future values of exogenous variables come from the user, or the plan leaves them out (`use_exog: false`) and you say so. If the CSV has a problem, tell the user; only with their permission write a corrected copy inside the allowed directory under a new name and profile it.
6. Foundation models other than the default (Chronos-2) have their own license and size: tell the user before choosing one. State the license of a model only as a notice or an error gives it.
7. Report what was measured, never why: give no cause, even hedged, for a ranking, a metric or the shape of a forecast. `compare` says which candidate has the lowest error over the folds, not what makes it better.
8. The server does not search hyperparameters (it compares the candidates you list), detect anomalies or select features. Say so and stop there: do not do them another way (your own script, reading the file) unless the user then asks.
```

## profile

Profile a CSV file: frequency, series, exogenous columns and the recommended forecaster and estimator. Returns a profile id.

Annotations: {"read_only_hint": false, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "data_path": {
   "description": "Absolute path of a CSV file ('.csv', '.tsv', '.csv.gz' or '.tsv.gz') inside the directory the server may read. URLs are not accepted.",
   "type": "string"
  },
  "target": {
   "anyOf": [
    {
     "type": "string"
    },
    {
     "items": {
      "type": "string"
     },
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Column to forecast, or a list of columns (one series each) for wide multi-series data. Null when it is not known: the error lists the columns of the file."
  },
  "date_column": {
   "anyOf": [
    {
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Column with the dates. When null, the first column holding dates is used."
  },
  "series_id_column": {
   "anyOf": [
    {
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Column with the series ids of long multi-series data."
  },
  "exog_columns": {
   "anyOf": [
    {
     "items": {
      "type": "string"
     },
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Columns to use as exogenous variables, an empty list for none. When null, every column that is not the target, the date or the series ids. The other columns are not used."
  },
  "sep": {
   "anyOf": [
    {
     "enum": [
      ",",
      ";",
      "\t"
     ],
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Separator of the fields of the file: ',', ';' or a tabulator. When null, it is detected from the file; pass it only when an error says it cannot be told."
  },
  "decimal": {
   "anyOf": [
    {
     "enum": [
      ".",
      ","
     ],
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Decimal mark of the file: '.' or ',' (only when the separator is not ','). When null, it is detected from the file."
  }
 },
 "required": [
  "data_path"
 ]
}
```

## plan

Build a forecasting plan (lags, window features, metric, preprocessing, interval) from a profile and a horizon. Returns a plan id.

Annotations: {"read_only_hint": false, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "profile_id": {
   "description": "Id returned by `profile`.",
   "type": "string"
  },
  "steps": {
   "description": "Forecast horizon: number of steps ahead to predict, from 1 to the length of the longest series (12 for a year of monthly data).",
   "minimum": 1,
   "type": "integer"
  },
  "interval": {
   "anyOf": [
    {
     "items": {
      "type": "number"
     },
     "maxItems": 2,
     "minItems": 2,
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Prediction interval as two quantiles [lower, upper] with 0 < lower < upper < 1, e.g. [0.1, 0.9] for 80 %. The baseline and ForecasterStats only take symmetric ones (lower + upper = 1). Null for no interval."
  },
  "forecaster": {
   "anyOf": [
    {
     "enum": [
      "ForecasterRecursive",
      "ForecasterDirect",
      "ForecasterRecursiveMultiSeries",
      "ForecasterDirectMultiVariate",
      "ForecasterStats",
      "ForecasterFoundation",
      "ForecasterEquivalentDate"
     ],
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "skforecast forecaster class: ForecasterRecursive or ForecasterDirect (one series, machine learning), ForecasterRecursiveMultiSeries (several series), ForecasterDirectMultiVariate (one series predicted from several), ForecasterStats (Auto-ARIMA), ForecasterFoundation (pre-trained foundation model, no training) or ForecasterEquivalentDate (seasonal naive baseline). Null for the recommendation of the profile."
  },
  "estimator": {
   "anyOf": [
    {
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Estimator: one of ['CatBoostRegressor', 'HistGradientBoostingRegressor', 'LGBMRegressor', 'RandomForestRegressor', 'Ridge', 'XGBRegressor'] for the machine learning forecasters, 'Arima' for ForecasterStats, or the Hugging Face model id of a foundation model for ForecasterFoundation (default 'autogluon/chronos-2-small'; model id prefixes: ['amazon/chronos-2', 'autogluon/chronos-2', 'google/timesfm-2.5', 'google/timesfm-3.0', 'Salesforce/moirai-2', 'soda-inria/tabicl', 'priorlabs/tabpfn', 'theforecastingcompany/t0', 'Synthefy/Nori', 'taharnbl/TS-ICL']). ForecasterEquivalentDate takes none. Null for the recommendation."
  },
  "estimator_kwargs": {
   "anyOf": [
    {
     "additionalProperties": true,
     "type": "object"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Keyword arguments of the estimator, e.g. {'n_estimators': 200}. A foundation model only takes context_length, cross_learning, point_estimate, max_horizon, add_calendar_features and n_fourier_terms. Null for the defaults."
  },
  "lags": {
   "anyOf": [
    {
     "type": "integer"
    },
    {
     "items": {
      "type": "integer"
     },
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Lags: an integer n for 1..n, or a list of distinct positive integers. Null for the selection from the partial autocorrelation."
  },
  "window_features": {
   "anyOf": [
    {
     "items": {
      "additionalProperties": {
       "anyOf": [
        {
         "items": {
          "type": "string"
         },
         "type": "array"
        },
        {
         "type": "integer"
        }
       ]
      },
      "type": "object"
     },
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Rolling features, one entry per window size: {'stats': [...], 'window_size': n}, with stats among ['mean', 'std', 'min', 'max', 'sum', 'median', 'ratio_min_max', 'coef_variation', 'ewm'], e.g. [{'stats': ['mean', 'std'], 'window_size': 7}]. Null for the deterministic selection."
  },
  "metric": {
   "anyOf": [
    {
     "$ref": "#/$defs/Metric"
    },
    {
     "items": {
      "$ref": "#/$defs/Metric"
     },
     "minItems": 1,
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Metric, or list of metrics whose first one is the primary metric (the one that ranks); only the ones given are computed. Null for the metric selected from the data (MAE for one series, MASE for several) and its default panel."
  },
  "use_exog": {
   "anyOf": [
    {
     "type": "boolean"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Whether to use the exogenous columns of the data: false leaves them out (forecast then takes no exog_path); true fails when the data has none or the forecaster cannot use them. Null uses them whenever the forecaster can."
  },
  "differentiation": {
   "anyOf": [
    {
     "minimum": 1,
     "type": "integer"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Order of differencing of the target before training (an integer of at least 1, usually 1 for a trend); predictions are integrated back. Machine learning forecasters only. Null for none."
  },
  "calendar_features": {
   "anyOf": [
    {
     "items": {
      "enum": [
       "year",
       "month",
       "week",
       "day_of_week",
       "day_of_month",
       "day_of_year",
       "weekend",
       "hour",
       "minute",
       "second",
       "quarter"
      ],
      "type": "string"
     },
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Calendar features generated from the dates (an empty list for none); the encoding follows the estimator. A feature whose column is already an exogenous column used by the plan is rejected. Machine learning forecasters with a datetime index only. Null for those selected from the frequency."
  },
  "target_transformer": {
   "anyOf": [
    {
     "enum": [
      "StandardScaler",
      "none"
     ],
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Scaler of the target: 'StandardScaler', or 'none' for no scaling. Machine learning forecasters only. Null for the rule."
  },
  "dropna_from_series": {
   "anyOf": [
    {
     "type": "boolean"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Whether to drop the training rows with missing values; false fails when the data has missing values and the estimator does not accept them. Machine learning forecasters only. Null for the rule."
  }
 },
 "required": [
  "profile_id",
  "steps"
 ],
 "$defs": {
  "Metric": {
   "enum": [
    "mean_squared_error",
    "mean_absolute_error",
    "mean_absolute_percentage_error",
    "mean_squared_log_error",
    "mean_absolute_scaled_error",
    "root_mean_squared_scaled_error",
    "median_absolute_error",
    "symmetric_mean_absolute_percentage_error"
   ],
   "type": "string"
  }
 }
}
```

## refine_plan

Build a new plan from an existing one, changing some of its decisions. Returns a new plan id; the original plan is kept.

Annotations: {"read_only_hint": false, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "plan_id": {
   "description": "Id of the plan to refine.",
   "type": "string"
  },
  "overrides": {
   "$ref": "#/$defs/RefinePlanArgs",
   "description": "Values to change, e.g. {'estimator': 'Ridge', 'lags': 12}. An omitted key keeps the value of the plan; {'lags': null} selects the lags again and {'interval': null} removes the interval."
  }
 },
 "required": [
  "plan_id",
  "overrides"
 ],
 "$defs": {
  "RefinePlanArgs": {
   "additionalProperties": false,
   "description": "Decisions of the plan to change. An omitted key keeps the value of the plan; every key but forecaster, estimator and steps set to null asks for the deterministic default.",
   "properties": {
    "forecaster": {
     "description": "skforecast forecaster class: ForecasterRecursive or ForecasterDirect (one series, machine learning), ForecasterRecursiveMultiSeries (several series), ForecasterDirectMultiVariate (one series predicted from several), ForecasterStats (Auto-ARIMA), ForecasterFoundation (pre-trained foundation model, no training) or ForecasterEquivalentDate (seasonal naive baseline).",
     "enum": [
      "ForecasterRecursive",
      "ForecasterDirect",
      "ForecasterRecursiveMultiSeries",
      "ForecasterDirectMultiVariate",
      "ForecasterStats",
      "ForecasterFoundation",
      "ForecasterEquivalentDate"
     ],
     "type": "string"
    },
    "estimator": {
     "description": "Estimator: one of ['CatBoostRegressor', 'HistGradientBoostingRegressor', 'LGBMRegressor', 'RandomForestRegressor', 'Ridge', 'XGBRegressor'] for the machine learning forecasters, 'Arima' for ForecasterStats, or the Hugging Face model id of a foundation model for ForecasterFoundation (default 'autogluon/chronos-2-small'; model id prefixes: ['amazon/chronos-2', 'autogluon/chronos-2', 'google/timesfm-2.5', 'google/timesfm-3.0', 'Salesforce/moirai-2', 'soda-inria/tabicl', 'priorlabs/tabpfn', 'theforecastingcompany/t0', 'Synthefy/Nori', 'taharnbl/TS-ICL']). ForecasterEquivalentDate takes none.",
     "type": "string"
    },
    "estimator_kwargs": {
     "anyOf": [
      {
       "additionalProperties": true,
       "type": "object"
      },
      {
       "type": "null"
      }
     ],
     "description": "Keyword arguments of the estimator, e.g. {'n_estimators': 200}. A foundation model only takes context_length, cross_learning, point_estimate, max_horizon, add_calendar_features and n_fourier_terms. Null for the defaults of the estimator."
    },
    "steps": {
     "description": "Forecast horizon: number of steps ahead to predict, from 1 to the length of the longest series (12 for a year of monthly data).",
     "minimum": 1,
     "type": "integer"
    },
    "interval": {
     "anyOf": [
      {
       "items": {
        "type": "number"
       },
       "maxItems": 2,
       "minItems": 2,
       "type": "array"
      },
      {
       "type": "null"
      }
     ],
     "description": "Prediction interval as two quantiles [lower, upper] with 0 < lower < upper < 1, e.g. [0.1, 0.9] for 80 %. The baseline and ForecasterStats only take symmetric ones (lower + upper = 1). Null removes the interval."
    },
    "lags": {
     "anyOf": [
      {
       "type": "integer"
      },
      {
       "items": {
        "type": "integer"
       },
       "type": "array"
      },
      {
       "type": "null"
      }
     ],
     "description": "Lags: an integer n for 1..n, or a list of distinct positive integers. Null selects them again from the partial autocorrelation."
    },
    "window_features": {
     "anyOf": [
      {
       "items": {
        "additionalProperties": {
         "anyOf": [
          {
           "items": {
            "type": "string"
           },
           "type": "array"
          },
          {
           "type": "integer"
          }
         ]
        },
        "type": "object"
       },
       "type": "array"
      },
      {
       "type": "null"
      }
     ],
     "description": "Rolling features, one entry per window size: {'stats': [...], 'window_size': n}, with stats among ['mean', 'std', 'min', 'max', 'sum', 'median', 'ratio_min_max', 'coef_variation', 'ewm'], e.g. [{'stats': ['mean', 'std'], 'window_size': 7}]. Null selects them again with the deterministic rules."
    },
    "metric": {
     "anyOf": [
      {
       "$ref": "#/$defs/Metric"
      },
      {
       "items": {
        "$ref": "#/$defs/Metric"
       },
       "minItems": 1,
       "type": "array"
      },
      {
       "type": "null"
      }
     ],
     "description": "Metric, or list of metrics whose first one is the primary metric (the one that ranks); only the ones given are computed. Null selects them again from the data. Omitted, a metric chosen before is kept."
    },
    "use_exog": {
     "anyOf": [
      {
       "type": "boolean"
      },
      {
       "type": "null"
      }
     ],
     "description": "Whether to use the exogenous columns of the data: false leaves them out (forecast then takes no exog_path); true fails when the data has none or the forecaster cannot use them. Null lets the rule decide again. Omitted, a choice made before is kept."
    },
    "differentiation": {
     "anyOf": [
      {
       "minimum": 1,
       "type": "integer"
      },
      {
       "type": "null"
      }
     ],
     "description": "Order of differencing of the target before training (an integer of at least 1, usually 1 for a trend); predictions are integrated back. Machine learning forecasters only. Null removes it. Omitted, an order chosen before is kept."
    },
    "calendar_features": {
     "anyOf": [
      {
       "items": {
        "enum": [
         "year",
         "month",
         "week",
         "day_of_week",
         "day_of_month",
         "day_of_year",
         "weekend",
         "hour",
         "minute",
         "second",
         "quarter"
        ],
        "type": "string"
       },
       "type": "array"
      },
      {
       "type": "null"
      }
     ],
     "description": "Calendar features generated from the dates (an empty list for none); the encoding follows the estimator. A feature whose column is already an exogenous column used by the plan is rejected. Machine learning forecasters with a datetime index only. Null selects them again from the frequency. Omitted, a choice made before is kept."
    },
    "target_transformer": {
     "anyOf": [
      {
       "enum": [
        "StandardScaler",
        "none"
       ],
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "description": "Scaler of the target: 'StandardScaler', or 'none' for no scaling. Machine learning forecasters only. Null lets the rule decide again. Omitted, a choice made before is kept."
    },
    "dropna_from_series": {
     "anyOf": [
      {
       "type": "boolean"
      },
      {
       "type": "null"
      }
     ],
     "description": "Whether to drop the training rows with missing values; false fails when the data has missing values and the estimator does not accept them. Machine learning forecasters only. Null lets the rule decide again. Omitted, a choice made before is kept."
    }
   },
   "type": "object"
  },
  "Metric": {
   "enum": [
    "mean_squared_error",
    "mean_absolute_error",
    "mean_absolute_percentage_error",
    "mean_squared_log_error",
    "mean_absolute_scaled_error",
    "root_mean_squared_scaled_error",
    "median_absolute_error",
    "symmetric_mean_absolute_percentage_error"
   ],
   "type": "string"
  }
 }
}
```

## create_cv

Build a time series cross-validation strategy (TimeSeriesFold) for a plan. The response states its cost in `cost`. Returns a cv id.

Annotations: {"read_only_hint": false, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "plan_id": {
   "description": "Id of the plan to backtest (from `plan` or `refine_plan`).",
   "type": "string"
  },
  "initial_train_size": {
   "anyOf": [
    {
     "minimum": 1,
     "type": "integer"
    },
    {
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Observations of the first training set (a number), or the ISO 8601 date that ends it ('2005-06-01'). Null for the default: 70 % of the series, at least what the lags need and leaving room for two folds, written as a date when the data has dates."
  },
  "fold_stride": {
   "anyOf": [
    {
     "minimum": 1,
     "type": "integer"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Observations the test set advances between folds. Null for `steps` (back-to-back folds); a larger value means fewer folds."
  },
  "refit": {
   "anyOf": [
    {
     "type": "boolean"
    },
    {
     "minimum": 0,
     "type": "integer"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Whether to train again in every fold (true), never (false) or every n folds (an integer). Null for false: train once. Refitting multiplies the cost; ForecasterStats is refitted in every fold whatever it says."
  },
  "fixed_train_size": {
   "anyOf": [
    {
     "type": "boolean"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Whether the training window keeps its size when refitting (true) or grows (false). Null for false. Only with `refit` true or an integer: with `refit` false or null it is an error, as it would not run (ForecasterStats aside)."
  },
  "gap": {
   "anyOf": [
    {
     "minimum": 0,
     "type": "integer"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Observations between the end of training and the test set. Null for 0. A direct forecaster (ForecasterDirect, ForecasterDirectMultiVariate) cannot be backtested with a gap."
  },
  "skip_folds": {
   "anyOf": [
    {
     "minimum": 1,
     "type": "integer"
    },
    {
     "items": {
      "minimum": 1,
      "type": "integer"
     },
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Folds are numbered from 0, and fold 0 always runs. An integer n keeps folds 0, n, 2n, ...; a list skips the folds at those numbers (each at least 1 and below the number of folds). Null for every fold."
  },
  "allow_incomplete_fold": {
   "anyOf": [
    {
     "type": "boolean"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Whether the last fold may have fewer than `steps` observations. Null for true."
  }
 },
 "required": [
  "plan_id"
 ]
}
```

## backtest

Backtest a plan with a cross-validation strategy: metrics over the folds, with the predictions and metrics in CSV files. Returns a backtest id.

Annotations: {"read_only_hint": false, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "cv_id": {
   "description": "Id returned by `create_cv`.",
   "type": "string"
  },
  "plan_id": {
   "anyOf": [
    {
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Plan to backtest, built from the same profile. Null for the plan the cross-validation strategy was built for."
  }
 },
 "required": [
  "cv_id"
 ]
}
```

## compare

Backtest several configurations on the same folds and rank them by `metric`. Reports progress per candidate and can be cancelled between candidates. Returns a comparison id and the plan of the winner in `links.best_plan_id`.

Annotations: {"read_only_hint": false, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "cv_id": {
   "description": "Id returned by `create_cv`: every candidate is backtested on its folds.",
   "type": "string"
  },
  "candidates": {
   "anyOf": [
    {
     "items": {
      "$ref": "#/$defs/CandidateArg"
     },
     "minItems": 1,
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Configurations to compare, each {'name': ..., 'config': {...}}, e.g. [{'name': 'ridge', 'config': {'estimator': 'Ridge'}}]. Null for the candidates recommended by the profile: the forecasters of its family (with several series, ForecasterRecursiveMultiSeries and ForecasterFoundation), or the estimators of the recommended forecaster when that leaves one, without those above 500 estimator fits; plus the plan the strategy was built for, in the row 'Strategy plan', when it is none of them. The summary names the row of that plan. A candidate that fails is ranked last with its error."
  },
  "interval": {
   "anyOf": [
    {
     "items": {
      "type": "number"
     },
     "maxItems": 2,
     "minItems": 2,
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Prediction interval computed for every candidate. Prediction interval as two quantiles [lower, upper] with 0 < lower < upper < 1, e.g. [0.1, 0.9] for 80 %. The baseline and ForecasterStats only take symmetric ones (lower + upper = 1). Null for the interval of the plan the strategy was built for."
  },
  "metric": {
   "anyOf": [
    {
     "$ref": "#/$defs/Metric"
    },
    {
     "items": {
      "$ref": "#/$defs/Metric"
     },
     "minItems": 1,
     "type": "array"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Metric of every candidate. Metric, or list of metrics whose first one is the primary metric (the one that ranks); only the ones given are computed. Null for the metric chosen for the plan the strategy was built for, if one was chosen, else the one selected from the data."
  },
  "baseline": {
   "default": true,
   "description": "Whether to add a seasonal naive baseline (ForecasterEquivalentDate) to the ranking.",
   "type": "boolean"
  }
 },
 "required": [
  "cv_id"
 ],
 "$defs": {
  "CandidateArg": {
   "additionalProperties": false,
   "description": "A configuration to compare, with a unique name.",
   "properties": {
    "name": {
     "description": "Unique name of the candidate, which labels its row of the leaderboard. 'Baseline (seasonal naive)' and 'Baseline (naive)' are reserved for the baseline.",
     "type": "string"
    },
    "config": {
     "$ref": "#/$defs/CandidateArgs",
     "description": "Its configuration; empty for the recommendation."
    }
   },
   "required": [
    "name"
   ],
   "type": "object"
  },
  "CandidateArgs": {
   "additionalProperties": false,
   "description": "Configuration of one candidate. An omitted key keeps the recommendation of the profile.",
   "properties": {
    "forecaster": {
     "description": "skforecast forecaster class: ForecasterRecursive or ForecasterDirect (one series, machine learning), ForecasterRecursiveMultiSeries (several series), ForecasterDirectMultiVariate (one series predicted from several), ForecasterStats (Auto-ARIMA), ForecasterFoundation (pre-trained foundation model, no training) or ForecasterEquivalentDate (seasonal naive baseline).",
     "enum": [
      "ForecasterRecursive",
      "ForecasterDirect",
      "ForecasterRecursiveMultiSeries",
      "ForecasterDirectMultiVariate",
      "ForecasterStats",
      "ForecasterFoundation",
      "ForecasterEquivalentDate"
     ],
     "type": "string"
    },
    "estimator": {
     "description": "Estimator: one of ['CatBoostRegressor', 'HistGradientBoostingRegressor', 'LGBMRegressor', 'RandomForestRegressor', 'Ridge', 'XGBRegressor'] for the machine learning forecasters, 'Arima' for ForecasterStats, or the Hugging Face model id of a foundation model for ForecasterFoundation (default 'autogluon/chronos-2-small'; model id prefixes: ['amazon/chronos-2', 'autogluon/chronos-2', 'google/timesfm-2.5', 'google/timesfm-3.0', 'Salesforce/moirai-2', 'soda-inria/tabicl', 'priorlabs/tabpfn', 'theforecastingcompany/t0', 'Synthefy/Nori', 'taharnbl/TS-ICL']). ForecasterEquivalentDate takes none.",
     "type": "string"
    },
    "estimator_kwargs": {
     "anyOf": [
      {
       "additionalProperties": true,
       "type": "object"
      },
      {
       "type": "null"
      }
     ],
     "description": "Keyword arguments of the estimator, e.g. {'n_estimators': 200}. A foundation model only takes context_length, cross_learning, point_estimate, max_horizon, add_calendar_features and n_fourier_terms."
    },
    "lags": {
     "anyOf": [
      {
       "type": "integer"
      },
      {
       "items": {
        "type": "integer"
       },
       "type": "array"
      },
      {
       "type": "null"
      }
     ],
     "description": "Lags: an integer n for 1..n, or a list of distinct positive integers. Null selects them from the partial autocorrelation."
    },
    "window_features": {
     "anyOf": [
      {
       "items": {
        "additionalProperties": {
         "anyOf": [
          {
           "items": {
            "type": "string"
           },
           "type": "array"
          },
          {
           "type": "integer"
          }
         ]
        },
        "type": "object"
       },
       "type": "array"
      },
      {
       "type": "null"
      }
     ],
     "description": "Rolling features, one entry per window size: {'stats': [...], 'window_size': n}, with stats among ['mean', 'std', 'min', 'max', 'sum', 'median', 'ratio_min_max', 'coef_variation', 'ewm'], e.g. [{'stats': ['mean', 'std'], 'window_size': 7}]. Null selects them with the deterministic rules."
    },
    "use_exog": {
     "anyOf": [
      {
       "type": "boolean"
      },
      {
       "type": "null"
      }
     ],
     "description": "Whether to use the exogenous columns of the data: false leaves them out (forecast then takes no exog_path); true fails when the data has none or the forecaster cannot use them. Null uses them whenever the forecaster can."
    },
    "differentiation": {
     "anyOf": [
      {
       "minimum": 1,
       "type": "integer"
      },
      {
       "type": "null"
      }
     ],
     "description": "Order of differencing of the target before training (an integer of at least 1, usually 1 for a trend); predictions are integrated back. Machine learning forecasters only. The candidate runs on a copy of the strategy with this order."
    },
    "calendar_features": {
     "anyOf": [
      {
       "items": {
        "enum": [
         "year",
         "month",
         "week",
         "day_of_week",
         "day_of_month",
         "day_of_year",
         "weekend",
         "hour",
         "minute",
         "second",
         "quarter"
        ],
        "type": "string"
       },
       "type": "array"
      },
      {
       "type": "null"
      }
     ],
     "description": "Calendar features generated from the dates (an empty list for none); the encoding follows the estimator. A feature whose column is already an exogenous column used by the plan is rejected. Machine learning forecasters with a datetime index only. Null selects them from the frequency."
    },
    "target_transformer": {
     "anyOf": [
      {
       "enum": [
        "StandardScaler",
        "none"
       ],
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "description": "Scaler of the target: 'StandardScaler', or 'none' for no scaling. Machine learning forecasters only. Null for the rule."
    },
    "dropna_from_series": {
     "anyOf": [
      {
       "type": "boolean"
      },
      {
       "type": "null"
      }
     ],
     "description": "Whether to drop the training rows with missing values; false fails when the data has missing values and the estimator does not accept them. Machine learning forecasters only. Null for the rule."
    }
   },
   "type": "object"
  },
  "Metric": {
   "enum": [
    "mean_squared_error",
    "mean_absolute_error",
    "mean_absolute_percentage_error",
    "mean_squared_log_error",
    "mean_absolute_scaled_error",
    "root_mean_squared_scaled_error",
    "median_absolute_error",
    "symmetric_mean_absolute_percentage_error"
   ],
   "type": "string"
  }
 }
}
```

## forecast

Run a plan: forecast the future, or evaluate on a test set with `test_size`. Predictions and metrics go to CSV files. Returns a forecast id.

Annotations: {"read_only_hint": false, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "plan_id": {
   "description": "Id of the plan to run (from `plan`, `refine_plan` or `links.best_plan_id` of `compare`).",
   "type": "string"
  },
  "test_size": {
   "anyOf": [
    {
     "type": "integer"
    },
    {
     "type": "number"
    },
    {
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Null to forecast the future. To evaluate instead, the test set: the last n observations (an integer, which must equal `steps`) or the ISO 8601 date it starts at. A fraction in (0, 1) only works when it gives exactly `steps` observations."
  },
  "exog_path": {
   "anyOf": [
    {
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Absolute path of a CSV file with the future values of the exogenous variables, one row per date (and series) of the horizon. Required to forecast the future when the plan uses exogenous variables. The script of `get_code` reads them from 'exog_future.csv' in its working directory."
  }
 },
 "required": [
  "plan_id"
 ]
}
```

## get_code

Return the Python script of an object: the one that ran, or that would run for a plan.

Annotations: {"read_only_hint": true, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "object_id": {
   "description": "Id of a plan (its forecasting script), a cross-validation strategy (the code that builds it), a backtest, a forecast or a comparison (the script that ran).",
   "type": "string"
  },
  "candidate": {
   "anyOf": [
    {
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "For a comparison, the candidate whose script to return. Null for the best one."
  }
 },
 "required": [
  "object_id"
 ]
}
```

## get_failure

Return the traceback and the code of a failed run or of a failed candidate of a comparison.

Annotations: {"read_only_hint": true, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "object_id": {
   "description": "`details.failure_id` of an error, or the id of a comparison whose candidate failed.",
   "type": "string"
  },
  "candidate": {
   "anyOf": [
    {
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Name of the failed candidate of a comparison."
  }
 },
 "required": [
  "object_id"
 ]
}
```

## list_objects

List the ids of the objects the server keeps.

Annotations: {"read_only_hint": true, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "kind": {
   "anyOf": [
    {
     "enum": [
      "profile",
      "plan",
      "cv",
      "backtest",
      "comparison",
      "forecast"
     ],
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "description": "Only the objects of this kind. Null for every kind."
  }
 }
}
```

## describe_object

Return the response that created an object (summary, links, notices, files).

Annotations: {"read_only_hint": true, "destructive_hint": false, "open_world_hint": false}

```json
{
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "object_id": {
   "description": "Id of a registered object.",
   "type": "string"
  }
 },
 "required": [
  "object_id"
 ]
}
```
