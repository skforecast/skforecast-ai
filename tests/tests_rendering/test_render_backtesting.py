# Unit test render_backtesting rendering

from skforecast_ai.rendering.backtesting import (
    render_backtesting_foundation,
    render_backtesting_multi_series,
    render_backtesting_multivariate,
    render_backtesting_single_series,
    render_backtesting_statistical,
)
from skforecast_ai.schemas import RenderedScript

from .fixtures_rendering import (
    cv_basic,
    plan_foundation,
    plan_multi_series,
    plan_multi_series_exog,
    plan_multivariate,
    plan_single_recursive_no_exog,
    plan_statistical,
    profile_multi_long,
    profile_multi_wide,
    profile_multi_wide_exog,
    profile_single_no_exog,
)


# =============================================================================
# Tests: render_backtesting_single_series — full script comparison
# =============================================================================
def test_render_backtesting_single_series_output_when_no_exog():
    """
    Test that render_backtesting_single_series produces the expected
    full script with TimeSeriesFold and backtesting_forecaster call.
    """
    result = render_backtesting_single_series(
        plan_single_recursive_no_exog, profile_single_no_exog, cv_basic
    )

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.recursive import ForecasterRecursive\n"
        "from skforecast.model_selection import TimeSeriesFold, backtesting_forecaster\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursive(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        ")\n"
        "\n"
        "# Time series cross-validation configuration\n"
        "cv = TimeSeriesFold(\n"
        "    steps              = 10,\n"
        "    initial_train_size = 80,\n"
        "    refit              = False,\n"
        ")\n"
        "\n"
        "# Run backtesting\n"
        "metrics, predictions = backtesting_forecaster(\n"
        "    forecaster        = forecaster,\n"
        "    y                 = data['sales'],\n"
        "    cv                = cv,\n"
        "    metric            = ['mean_absolute_error', 'mean_squared_error', 'mean_absolute_scaled_error'],\n"
        "    n_jobs            = 'auto',\n"
        "    verbose           = False,\n"
        "    show_progress     = True,\n"
        "    suppress_warnings = True,\n"
        ")\n"
        "\n"
        "print(metrics)\n"
        "print(predictions.head())"
    )
    assert result.full_script == expected


# =============================================================================
# Tests: render_backtesting_multi_series — full script comparison
# =============================================================================
def test_render_backtesting_multi_series_output_when_wide_format():
    """
    Test that render_backtesting_multi_series produces the expected
    full script with backtesting_forecaster_multiseries call.
    """
    result = render_backtesting_multi_series(plan_multi_series, profile_multi_wide, cv_basic)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.recursive import ForecasterRecursiveMultiSeries\n"
        "from skforecast.model_selection import TimeSeriesFold, backtesting_forecaster_multiseries\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursiveMultiSeries(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        "    encoding  = 'ordinal',\n"
        ")\n"
        "\n"
        "# Time series cross-validation configuration\n"
        "cv = TimeSeriesFold(\n"
        "    steps              = 10,\n"
        "    initial_train_size = 80,\n"
        "    refit              = False,\n"
        ")\n"
        "\n"
        "# Run backtesting\n"
        "metrics, predictions = backtesting_forecaster_multiseries(\n"
        "    forecaster        = forecaster,\n"
        "    series            = data[['series_a', 'series_b']],\n"
        "    cv                = cv,\n"
        "    metric            = ['mean_absolute_error', 'mean_squared_error', 'mean_absolute_scaled_error'],\n"
        "    n_jobs            = 'auto',\n"
        "    verbose           = False,\n"
        "    show_progress     = True,\n"
        "    suppress_warnings = True,\n"
        ")\n"
        "\n"
        "print(metrics)\n"
        "print(predictions.head())"
    )
    assert result.full_script == expected


# =============================================================================
# Tests: render_backtesting_multivariate — full script comparison
# =============================================================================
def test_render_backtesting_multivariate_output_when_wide_format():
    """
    Test that render_backtesting_multivariate produces the expected full
    script with ForecasterDirectMultiVariate (level, steps) and the
    backtesting_forecaster_multiseries call.
    """
    result = render_backtesting_multivariate(plan_multivariate, profile_multi_wide, cv_basic)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.direct import ForecasterDirectMultiVariate\n"
        "from skforecast.model_selection import TimeSeriesFold, backtesting_forecaster_multiseries\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterDirectMultiVariate(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    level     = 'series_a',\n"
        "    steps     = 5,\n"
        "    lags      = 7,\n"
        ")\n"
        "\n"
        "# Time series cross-validation configuration\n"
        "cv = TimeSeriesFold(\n"
        "    steps              = 10,\n"
        "    initial_train_size = 80,\n"
        "    refit              = False,\n"
        ")\n"
        "\n"
        "# Run backtesting\n"
        "metrics, predictions = backtesting_forecaster_multiseries(\n"
        "    forecaster        = forecaster,\n"
        "    series            = data[['series_a', 'series_b']],\n"
        "    cv                = cv,\n"
        "    metric            = ['mean_absolute_error', 'mean_squared_error', 'mean_absolute_scaled_error'],\n"
        "    n_jobs            = 'auto',\n"
        "    verbose           = False,\n"
        "    show_progress     = True,\n"
        "    suppress_warnings = True,\n"
        ")\n"
        "\n"
        "print(metrics)\n"
        "print(predictions.head())"
    )
    assert result.full_script == expected


# =============================================================================
# Tests: render_backtesting_statistical — full script comparison
# =============================================================================
def test_render_backtesting_statistical_output_when_auto_arima():
    """
    Test that render_backtesting_statistical produces the expected
    full script with backtesting_stats call and freeze_params.
    """
    result = render_backtesting_statistical(plan_statistical, profile_single_no_exog, cv_basic)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from skforecast.stats import Arima\n"
        "from skforecast.recursive import ForecasterStats\n"
        "from skforecast.model_selection import TimeSeriesFold, backtesting_stats\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "# Create forecaster (Auto-ARIMA)\n"
        "forecaster = ForecasterStats(\n"
        "    estimator = Arima(order=None, seasonal_order=None, m=7),\n"
        ")\n"
        "\n"
        "# Time series cross-validation configuration\n"
        "cv = TimeSeriesFold(\n"
        "    steps              = 10,\n"
        "    initial_train_size = 80,\n"
        "    refit              = False,\n"
        ")\n"
        "\n"
        "# Run backtesting\n"
        "metrics, predictions = backtesting_stats(\n"
        "    forecaster        = forecaster,\n"
        "    y                 = data['sales'],\n"
        "    cv                = cv,\n"
        "    metric            = ['mean_absolute_error', 'mean_squared_error', 'mean_absolute_scaled_error'],\n"
        "    freeze_params     = True,\n"
        "    n_jobs            = 'auto',\n"
        "    verbose           = False,\n"
        "    show_progress     = True,\n"
        "    suppress_warnings = True,\n"
        ")\n"
        "\n"
        "print(metrics)\n"
        "print(predictions.head())"
    )
    assert result.full_script == expected


# =============================================================================
# Tests: render_backtesting_foundation — full script comparison
# =============================================================================
def test_render_backtesting_foundation_output_when_chronos():
    """
    Test that render_backtesting_foundation produces the expected
    full script with backtesting_foundation call.
    """
    result = render_backtesting_foundation(plan_foundation, profile_single_no_exog, cv_basic)

    assert isinstance(result, RenderedScript)

    expected = (
        "import pandas as pd\n"
        "from skforecast.foundation import FoundationModel, ForecasterFoundation\n"
        "from skforecast.model_selection import TimeSeriesFold, backtesting_foundation\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
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
        "# Time series cross-validation configuration\n"
        "cv = TimeSeriesFold(\n"
        "    steps              = 10,\n"
        "    initial_train_size = 80,\n"
        "    refit              = False,\n"
        ")\n"
        "\n"
        "# Run backtesting\n"
        "metrics, predictions = backtesting_foundation(\n"
        "    forecaster        = forecaster,\n"
        "    series            = data['sales'],\n"
        "    cv                = cv,\n"
        "    metric            = ['mean_absolute_error', 'mean_squared_error', 'mean_absolute_scaled_error'],\n"
        "    verbose           = False,\n"
        "    show_progress     = True,\n"
        "    suppress_warnings = True,\n"
        ")\n"
        "\n"
        "print(metrics)\n"
        "print(predictions.head())"
    )
    assert result.full_script == expected


# =============================================================================
# Tests: render_backtesting_multi_series — long format
# =============================================================================
def test_render_backtesting_multi_series_output_when_long_format():
    """
    Test that render_backtesting_multi_series produces correct
    reshape_series_long_to_dict call for long-format data.
    """
    result = render_backtesting_multi_series(plan_multi_series, profile_multi_long, cv_basic)

    expected = (
        "import pandas as pd\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.preprocessing import reshape_series_long_to_dict\n"
        "from skforecast.recursive import ForecasterRecursiveMultiSeries\n"
        "from skforecast.model_selection import TimeSeriesFold, backtesting_forecaster_multiseries\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.sort_values('date')\n"
        "\n"
        "# Reshape to dict format (required for backtesting multi-series)\n"
        "series_dict = reshape_series_long_to_dict(\n"
        "    data      = data,\n"
        "    series_id = 'series_id',\n"
        "    index     = 'date',\n"
        "    values    = 'value',\n"
        "    freq      = 'D',\n"
        ")\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursiveMultiSeries(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        "    encoding  = 'ordinal',\n"
        ")\n"
        "\n"
        "# Time series cross-validation configuration\n"
        "cv = TimeSeriesFold(\n"
        "    steps              = 10,\n"
        "    initial_train_size = 80,\n"
        "    refit              = False,\n"
        ")\n"
        "\n"
        "# Run backtesting\n"
        "metrics, predictions = backtesting_forecaster_multiseries(\n"
        "    forecaster        = forecaster,\n"
        "    series            = series_dict,\n"
        "    cv                = cv,\n"
        "    metric            = ['mean_absolute_error', 'mean_squared_error', 'mean_absolute_scaled_error'],\n"
        "    n_jobs            = 'auto',\n"
        "    verbose           = False,\n"
        "    show_progress     = True,\n"
        "    suppress_warnings = True,\n"
        ")\n"
        "\n"
        "print(metrics)\n"
        "print(predictions.head())"
    )
    assert result.full_script == expected


# =============================================================================
# Tests: render_backtesting_multi_series — exog enabled
# =============================================================================
def test_render_backtesting_multi_series_output_when_wide_format_with_exog():
    """
    Test that render_backtesting_multi_series produces correct exog
    handling for wide-format data with exogenous variables.
    """
    result = render_backtesting_multi_series(
        plan_multi_series_exog, profile_multi_wide_exog, cv_basic
    )

    expected = (
        "import pandas as pd\n"
        "from lightgbm import LGBMRegressor\n"
        "from skforecast.recursive import ForecasterRecursiveMultiSeries\n"
        "from skforecast.model_selection import TimeSeriesFold, backtesting_forecaster_multiseries\n"
        "\n"
        "# Load data\n"
        "data = pd.read_csv('data.csv')\n"
        "\n"
        "data['date'] = pd.to_datetime(data['date'])\n"
        "data = data.set_index('date')\n"
        "data = data.asfreq('D')\n"
        "data = data.sort_index()\n"
        "\n"
        "exog_features = ['promo', 'holiday']\n"
        "\n"
        "# Create forecaster\n"
        "forecaster = ForecasterRecursiveMultiSeries(\n"
        "    estimator = LGBMRegressor(random_state=123, verbose=-1),\n"
        "    lags      = 7,\n"
        "    encoding  = 'ordinal',\n"
        ")\n"
        "\n"
        "# Time series cross-validation configuration\n"
        "cv = TimeSeriesFold(\n"
        "    steps              = 10,\n"
        "    initial_train_size = 80,\n"
        "    refit              = False,\n"
        ")\n"
        "\n"
        "# Run backtesting\n"
        "metrics, predictions = backtesting_forecaster_multiseries(\n"
        "    forecaster        = forecaster,\n"
        "    series            = data[['series_a', 'series_b']],\n"
        "    exog              = data[exog_features],\n"
        "    cv                = cv,\n"
        "    metric            = ['mean_absolute_error', 'mean_squared_error', 'mean_absolute_scaled_error'],\n"
        "    n_jobs            = 'auto',\n"
        "    verbose           = False,\n"
        "    show_progress     = True,\n"
        "    suppress_warnings = True,\n"
        ")\n"
        "\n"
        "print(metrics)\n"
        "print(predictions.head())"
    )
    assert result.full_script == expected


# =============================================================================
# Tests: backtesting does not require a train/test split boundary
# =============================================================================
def test_render_backtesting_single_series_output_when_no_end_train_needed():
    """
    Test that render_backtesting_single_series renders successfully without
    a train/test split boundary. Backtesting renderers use CV folds and do
    not emit `end_train`, so they never require it on the plan or profile.
    """
    result = render_backtesting_single_series(
        plan_single_recursive_no_exog, profile_single_no_exog, cv_basic
    )
    assert isinstance(result, RenderedScript)
