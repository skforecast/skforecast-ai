# Profiles

What [`profile()`][skforecast_ai.assistant.ForecastingAssistant.profile] finds in the data. [`ForecastingProfile`][skforecast_ai.schemas.profiles.ForecastingProfile] is the object you pass to `plan()`, `create_cv()` and `ask()`: it holds summary statistics of the dataset (a [`DataProfile`][skforecast_ai.schemas.profiles.DataProfile]), the significant lags of each series and the recommended forecaster and estimator, never the observations themselves.

::: skforecast_ai.schemas.profiles
