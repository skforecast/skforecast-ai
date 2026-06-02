# Changelog

All significant changes to this project are documented in this release file.

| Legend                                                     |                                       |
|:-----------------------------------------------------------|:--------------------------------------|
| <span class="badge text-bg-feature">Feature</span>         | New feature                           |
| <span class="badge text-bg-enhancement">Enhancement</span> | Improvement in existing functionality |
| <span class="badge text-bg-api-change">API Change</span>   | Changes in the API                    |
| <span class="badge text-bg-danger">Fix</span>              | Bug fix                               |


## 0.1.0 <small>In development</small> { id="0.1.0" }

The main changes in this release are:

+ ......

**Added**

+ ......

**Changed**

+ ......

**Fixed**

+ ......


<!-- Links to API Reference -->
<!-- Forecasters -->
[recursive]: ../api/ForecasterRecursive.md
[ForecasterRecursive]: ../api/ForecasterRecursive.md
[ForecasterRecursiveClassifier]: ../api/ForecasterRecursiveClassifier.md
[ForecasterDirect]: ../api/ForecasterDirect.md
[ForecasterRecursiveMultiSeries]: ../api/ForecasterRecursiveMultiSeries.md
[ForecasterDirectMultiVariate]: ../api/ForecasterDirectMultiVariate.md
[ForecasterFoundation]: ../api/ForecasterFoundation.md
[ForecasterRnn]: ../api/ForecasterRnn.md
[create_and_compile_model]: ../api/ForecasterRnn.md#skforecast.deep_learning.utils.create_and_compile_model
[ForecasterStats]: ../api/ForecasterStats.md
[ForecasterEquivalentDate]: ../api/ForecasterEquivalentDate.md
[ForecasterRecursiveClassifier]: ../api/ForecasterRecursiveClassifier.md

<!-- foundation -->
[FoundationModel]: ../api/FoundationModel.md#skforecast.foundation._foundation_model.FoundationModel

<!-- stats -->
[stats]: ../api/stats.md
[Arima]: ../api/stats.md#skforecast.stats._arima.Arima
[Sarimax]: ../api/stats.md#skforecast.stats._sarimax.Sarimax
[Ets]: ../api/stats.md#skforecast.stats._ets.Ets
[Arar]: ../api/stats.md#skforecast.stats._arar.Arar
[acf]: ../api/stats.md#skforecast.stats._autocorrelation.acf
[pacf]: ../api/stats.md#skforecast.stats._autocorrelation.pacf
[calculate_lag_autocorrelation]: ../api/stats.md#skforecast.stats._autocorrelation.calculate_lag_autocorrelation

<!-- model_selection -->
[model_selection]: ../api/model_selection.md

[backtesting_forecaster]: ../api/model_selection.md#skforecast.model_selection._validation.backtesting_forecaster
[grid_search_forecaster]: ../api/model_selection.md#skforecast.model_selection._search.grid_search_forecaster
[random_search_forecaster]: ../api/model_selection.md#skforecast.model_selection._search.random_search_forecaster
[bayesian_search_forecaster]: ../api/model_selection.md#skforecast.model_selection._search.bayesian_search_forecaster

[backtesting_forecaster_multiseries]: ../api/model_selection.md#skforecast.model_selection._validation.backtesting_forecaster_multiseries
[grid_search_forecaster_multiseries]: ../api/model_selection.md#skforecast.model_selection._search.grid_search_forecaster_multiseries
[random_search_forecaster_multiseries]: ../api/model_selection.md#skforecast.model_selection._search.random_search_forecaster_multiseries
[bayesian_search_forecaster_multiseries]: ../api/model_selection.md#skforecast.model_selection._search.bayesian_search_forecaster_multiseries

[backtesting_stats]: ../api/model_selection.md#skforecast.model_selection._validation.backtesting_stats
[grid_search_stats]: ../api/model_selection.md#skforecast.model_selection._search.grid_search_stats
[random_search_stats]: ../api/model_selection.md#skforecast.model_selection._search.random_search_stats

[backtesting_foundation]: ../api/model_selection.md#skforecast.model_selection._validation.backtesting_foundation

[BaseFold]: ../api/model_selection.md#skforecast.model_selection._split.BaseFold
[TimeSeriesFold]: ../api/model_selection.md#skforecast.model_selection._split.TimeSeriesFold
[OneStepAheadFold]: ../api/model_selection.md#skforecast.model_selection._split.OneStepAheadFold

<!-- feature_selection -->
[feature_selection]: ../api/feature_selection.md
[select_features]: ../api/feature_selection.md#skforecast.feature_selection.feature_selection.select_features
[select_features_multiseries]: ../api/feature_selection.md#skforecast.feature_selection.feature_selection.select_features_multiseries

<!-- preprocessing -->
[preprocessing]: ../api/preprocessing.md
[RollingFeatures]: ../api/preprocessing.md#skforecast.preprocessing._preprocessing.RollingFeatures
[RollingFeaturesClassification]: ../api/preprocessing.md#skforecast.preprocessing._preprocessing.RollingFeaturesClassification
[reshape_series_wide_to_long]: ../api/preprocessing.md#skforecast.preprocessing._preprocessing.reshape_series_wide_to_long
[reshape_series_long_to_dict]: ../api/preprocessing.md#skforecast.preprocessing._preprocessing.reshape_series_long_to_dict
[reshape_exog_long_to_dict]: ../api/preprocessing.md#skforecast.preprocessing._preprocessing.reshape_exog_long_to_dict
[reshape_series_exog_dict_to_long]: ../api/preprocessing.md#skforecast.preprocessing._preprocessing.reshape_series_exog_dict_to_long
[TimeSeriesDifferentiator]: ../api/preprocessing.md#skforecast.preprocessing._preprocessing.TimeSeriesDifferentiator
[QuantileBinner]: ../api/preprocessing.md#skforecast.preprocessing._preprocessing.QuantileBinner
[ConformalIntervalCalibrator]: ../api/preprocessing.md#skforecast.preprocessing._preprocessing.ConformalIntervalCalibrator
[create_datetime_features]: ../api/preprocessing.md#skforecast.preprocessing._calendar.create_datetime_features
[DateTimeFeatureTransformer]: ../api/preprocessing.md#skforecast.preprocessing._calendar.DateTimeFeatureTransformer
[calculate_distance_from_holiday]: ../api/preprocessing.md#skforecast.preprocessing._calendar.calculate_distance_from_holiday

<!-- drift_detection -->
[drift_detection]: ../api/drift_detection.md
[RangeDriftDetector]: ../api/drift_detection.md#skforecast.drift_detection._range_drift.RangeDriftDetector
[PopulationDriftDetector]: ../api/drift_detection.md#skforecast.drift_detection._population_drift.PopulationDriftDetector

<!-- metrics -->
[metrics]: ../api/metrics.md
[mean_absolute_scaled_error]: ../api/metrics.md#skforecast.metrics.mean_absolute_scaled_error
[root_mean_squared_scaled_error]: ../api/metrics.md#skforecast.metrics.root_mean_squared_scaled_error
[symmetric_mean_absolute_percentage_error]: ../api/metrics.md#skforecast.metrics.symmetric_mean_absolute_percentage_error
[add_y_train_argument]: ../api/metrics.md#skforecast.metrics.add_y_train_argument

<!-- plot -->
[plot]: ../api/plot.md
[set_dark_theme]: ../api/plot.md#skforecast.plot.plot.set_dark_theme
[plot_residuals]: ../api/plot.md#skforecast.plot.plot.plot_residuals
[plot_prediction_distribution]: ../api/plot.md#skforecast.plot.plot.plot_prediction_distribution
[plot_prediction_intervals]: ../api/plot.md#skforecast.plot.plot.plot_prediction_intervals
[backtesting_gif_creator]: ../api/plot.md#skforecast.plot.plot.backtesting_gif_creator
[plot_multivariate_time_series_corr]: ../api/plot.md#skforecast.plot.plot.plot_multivariate_time_series_corr

<!-- utils -->
[utils]: ../api/utils.md
[save_forecaster]: ../api/utils.md#skforecast.utils.utils.save_forecaster
[load_forecaster]: ../api/utils.md#skforecast.utils.utils.load_forecaster

<!-- experimental -->
[experimental]: ../api/experimental.md
[TimeSeriesSplitter]: ../api/experimental.md#skforecast.experimental._splitter.TimeSeriesSplitter

<!-- datasets -->
[datasets]: ../api/datasets.md
[fetch_dataset]: ../api/datasets.md#skforecast.datasets.fetch_dataset
[load_demo_dataset]: ../api/datasets.md#skforecast.datasets.load_demo_dataset
[show_datasets_info]: ../api/datasets.md#skforecast.datasets.show_datasets_info

<!-- exceptions -->
[exceptions]: ../api/exceptions.md
[IgnoredArgumentWarning]: ../api/exceptions.md#skforecast.exceptions.exceptions.IgnoredArgumentWarning

<!-- OLD -->
[ForecasterAutoreg]: https://skforecast.org/0.13.0/api/forecasterautoreg
[ForecasterAutoregCustom]: https://skforecast.org/0.13.0/api/forecasterautoregcustom
[ForecasterAutoregDirect]: https://skforecast.org/0.13.0/api/forecasterautoregdirect
[ForecasterAutoregMultiSeries]: https://skforecast.org/0.13.0/api/forecastermultiseries
[ForecasterAutoregMultiSeriesCustom]: https://skforecast.org/0.13.0/api/forecastermultiseriescustom
[ForecasterAutoregMultiVariate]: https://skforecast.org/0.13.0/api/forecastermultivariate
[model_selection_multiseries]: https://skforecast.org/0.13.0/api/model_selection_multiseries
[model_selection_sarimax]: https://skforecast.org/0.13.0/api/model_selection_sarimax
[series_long_to_dict]: https://skforecast.org/0.16.0/api/preprocessing.html#skforecast.preprocessing.preprocessing.series_long_to_dict
[exog_long_to_dict]: https://skforecast.org/0.16.0/api/preprocessing.html#skforecast.preprocessing.preprocessing.exog_long_to_dict
[ForecasterSarimax]: https://skforecast.org/0.19.0/api/forecastersarimax.html
[backtesting_sarimax]: https://skforecast.org/0.19.0/api/model_selection.html#skforecast.model_selection._validation.backtesting_sarimax
[grid_search_sarimax]: https://skforecast.org/0.19.0/api/model_selection.html#skforecast.model_selection._search.grid_search_sarimax
[random_search_sarimax]: https://skforecast.org/0.19.0/api/model_selection.html#skforecast.model_selection._search.random_search_sarimax
