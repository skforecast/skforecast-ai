# Unit test _validation

import re
import warnings

import numpy as np
import pytest
from skforecast.preprocessing import CalendarFeatures
from skforecast.recursive import ForecasterRecursiveMultiSeries
from sklearn.linear_model import Ridge

from skforecast_ai import _utils as utils_module
from skforecast_ai import _validation as validation_module
from skforecast_ai._constants import FORECASTER_TASK_TYPES, SUPPORTED_TRANSFORMERS
from skforecast_ai.exceptions import InvalidInputError, InvalidInputTypeError
from skforecast_ai.recommendation.baseline import select_baseline_config
from skforecast_ai.recommendation.calendar import (
    CALENDAR_FEATURE_RELEVANCE,
    select_calendar_encoding,
)
from skforecast_ai.recommendation.preprocessing import build_forecaster_kwargs
from skforecast_ai.schemas import DataProfile
from skforecast_ai._validation import (
    _CALENDAR_ENCODINGS,
    _CALENDAR_FEATURES,
    _FORECASTER_KWARGS_KEYS,
    _SERIES_ENCODINGS,
    _validate_lags,
    _validate_window_features,
    check_estimator_installed,
    is_symmetric_interval,
    validate_estimator,
    validate_estimator_kwargs,
    validate_forecaster,
    validate_forecaster_kwargs,
    validate_frequency,
    validate_interval,
    validate_kwarg_names,
    validate_metrics,
    validate_preprocessing_step,
    validate_steps,
)

_SUPPORTED = (
    "['LGBMRegressor', 'Ridge', 'XGBRegressor', 'CatBoostRegressor', "
    "'RandomForestRegressor', 'HistGradientBoostingRegressor']"
)


# =============================================================================
# Tests: validate_estimator
# =============================================================================
@pytest.mark.parametrize(
    "task_type",
    ["single_series", "multi_series", "multivariate"],
    ids=lambda task_type: f"task_type: {task_type}",
)
def test_validate_estimator_ValueError_when_estimator_not_supported(task_type):
    """
    Test that a machine-learning estimator outside the supported list is
    rejected, since its name would be written into the generated script.
    """
    err_msg = re.escape(
        f"'LightGBM' is not a supported estimator. Supported estimators: "
        f"{_SUPPORTED}."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_estimator(
            estimator        = "LightGBM",
            estimator_kwargs = None,
            task_type        = task_type,
        )


@pytest.mark.parametrize(
    "key",
    ["1alpha", "class", "alpha beta", "alpha=1) or open('f'", 3],
    ids=lambda key: f"key: {key!r}",
)
@pytest.mark.parametrize(
    "estimator, task_type",
    [
        ("Ridge", "single_series"),
        ("Arima", "statistical"),
        ("autogluon/chronos-2-small", "foundation"),
    ],
    ids=["ml", "statistical", "foundation"],
)
def test_validate_estimator_ValueError_when_kwargs_key_not_parameter_name(
    key, estimator, task_type
):
    """
    Test that a keyword argument key that is not a valid Python parameter
    name is rejected for every family, since keys are written into the
    generated script as they are.
    """
    err_msg = re.escape(
        f"`estimator_kwargs` keys must be valid Python parameter names, got "
        f"{key!r}."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_estimator(
            estimator        = estimator,
            estimator_kwargs = {key: 1},
            task_type        = task_type,
        )


def test_validate_estimator_ValueError_when_statistical_estimator_not_arima():
    """
    Test that a statistical plan rejects an estimator other than 'Arima',
    which the generated script would ignore.
    """
    err_msg = re.escape(
        "'ForecasterStats' uses an ARIMA model, so estimator='Ridge' cannot be "
        "applied. Omit `estimator`, and set the ARIMA options through "
        "`estimator_kwargs`."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_estimator(
            estimator        = "Ridge",
            estimator_kwargs = None,
            task_type        = "statistical",
        )


@pytest.mark.parametrize(
    "estimator, estimator_kwargs, task_type",
    [
        ("LGBMRegressor", {"n_estimators": 10}, "single_series"),
        (None, None, "single_series"),
        ("Arima", {"order": [1, 0, 0]}, "statistical"),
        (None, None, "baseline"),
    ],
    ids=["supported estimator", "no estimator", "arima", "baseline"],
)
def test_validate_estimator_output_when_valid(
    estimator, estimator_kwargs, task_type
):
    """
    Test that supported estimators with valid keys pass without error.
    """
    assert validate_estimator(estimator, estimator_kwargs, task_type) is None


# =============================================================================
# Tests: validate_estimator_kwargs
# =============================================================================
def test_validate_estimator_kwargs_ValueError_when_name_unknown():
    """
    Test that an unknown keyword argument of an estimator whose constructor
    names all its parameters raises, suggesting the closest name and
    listing the valid ones.
    """
    err_msg = re.escape(
        "Ridge has no parameter 'alpah'. Did you mean 'alpha'? Valid "
        "parameters: ['alpha', 'copy_X', 'fit_intercept', 'max_iter', "
        "'positive', 'random_state', 'solver', 'tol']."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_estimator_kwargs("Ridge", {"alpha": 1.0, "alpah": 2.0})


@pytest.mark.parametrize(
    "estimator_kwargs, suggestion",
    [({"foo": 1}, ""), ({"ordr": (1, 0, 0)}, " Did you mean 'order'?")],
    ids=["no close match", "close match"],
)
def test_validate_estimator_kwargs_InvalidInputError_when_arima_name_unknown(
    estimator_kwargs, suggestion
):
    """
    Test that an unknown keyword argument of Arima (the ARIMA model of
    ForecasterStats) raises, with the closest name when there is one.
    """
    name = next(iter(estimator_kwargs))
    err_msg = re.escape(f"Arima has no parameter '{name}'.{suggestion}")
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_estimator_kwargs("Arima", estimator_kwargs)

    assert exc_info.value.field == "estimator_kwargs"


def test_validate_estimator_kwargs_output_when_arima_names_valid():
    """
    Test that the parameters of Arima pass without warnings.
    """
    messages = validate_estimator_kwargs("Arima", {"order": (1, 0, 0)})

    assert messages == []


def test_validate_estimator_kwargs_UserWarning_when_passthrough_name_unknown():
    """
    Test that an unknown keyword argument of LightGBM, which forwards
    unknown names to the library, warns instead of raising, since the
    library would ignore it without an error.
    """
    warn_msg = re.escape(
        "'n_estimatorz' is not a named parameter of LGBMRegressor. It is "
        "passed to the library as an extra parameter, which ignores it "
        "without an error if it does not exist. Did you mean 'n_estimators'?"
    )
    with pytest.warns(UserWarning, match=warn_msg):
        messages = validate_estimator_kwargs("LGBMRegressor", {"n_estimatorz": 10})

    assert messages == [
        "'n_estimatorz' is not a named parameter of LGBMRegressor. It is "
        "passed to the library as an extra parameter, which ignores it "
        "without an error if it does not exist. Did you mean 'n_estimators'?"
    ]


def test_validate_estimator_kwargs_output_when_lightgbm_alias():
    """
    Test that LightGBM parameters and aliases accepted through `**kwargs`
    (such as `verbose` or `min_data_in_leaf`) pass without a warning.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        messages = validate_estimator_kwargs(
            "LGBMRegressor",
            {"n_estimators": 10, "verbose": -1, "min_data_in_leaf": 5},
        )

    assert messages == []


def test_validate_estimator_kwargs_output_when_package_not_installed(
    monkeypatch,
):
    """
    Test that the names are not checked when the estimator package is not
    installed, since they cannot be read; running the plan reports it.
    """
    monkeypatch.setattr(
        validation_module.importlib.util, "find_spec", lambda name: None
    )

    assert validate_estimator_kwargs("Ridge", {"alpah": 2.0}) == []


# =============================================================================
# Tests: check_estimator_installed
# =============================================================================
def test_check_estimator_installed_ValueError_when_package_missing(monkeypatch):
    """
    Test that a machine-learning estimator whose package is not installed
    raises with the install command before the script runs.
    """
    monkeypatch.setattr(
        validation_module.importlib.util, "find_spec", lambda name: None
    )

    err_msg = re.escape(
        "XGBRegressor needs the 'xgboost' package, which is not installed "
        "(pip install xgboost)."
    )
    with pytest.raises(ValueError, match=err_msg):
        check_estimator_installed("XGBRegressor", "single_series")


def test_check_estimator_installed_code_and_field_when_package_missing(
    monkeypatch,
):
    """
    Test that a missing estimator package raises InvalidInputError with the
    code 'missing_dependency' and `estimator` as field.
    """
    monkeypatch.setattr(
        validation_module.importlib.util, "find_spec", lambda name: None
    )

    err_msg = re.escape(
        "XGBRegressor needs the 'xgboost' package, which is not installed "
        "(pip install xgboost)."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        check_estimator_installed("XGBRegressor", "single_series")

    assert exc_info.value.code == "missing_dependency"
    assert exc_info.value.field == "estimator"


def test_check_estimator_installed_output_when_not_machine_learning(monkeypatch):
    """
    Test that estimators of other families are not checked here (the
    foundation backend has its own check).
    """
    monkeypatch.setattr(
        validation_module.importlib.util, "find_spec", lambda name: None
    )

    assert check_estimator_installed("Arima", "statistical") is None


# =============================================================================
# Tests: check_estimator_installed, foundation models
# =============================================================================
def test_check_estimator_installed_InvalidInputError_when_foundation_backend_missing(
    monkeypatch,
):
    """
    Test that a ForecasterFoundation plan is checked through the backend of
    its model, with the code 'missing_dependency' and the field 'estimator'.
    """
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: False
    )

    err_msg = re.escape(
        "'autogluon/chronos-2-small' needs the 'chronos-forecasting' package, "
        "which is not installed (pip install \"chronos-forecasting\")."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        check_estimator_installed("autogluon/chronos-2-small", "foundation")

    assert exc_info.value.code == "missing_dependency"
    assert exc_info.value.field == "estimator"


def test_check_estimator_installed_output_when_foundation_backend_installed(
    monkeypatch,
):
    """
    Test that a ForecasterFoundation plan passes when the backend of its model
    is installed.
    """
    monkeypatch.setattr(
        "skforecast_ai._foundation.foundation_backend_installed", lambda info: True
    )

    assert check_estimator_installed("autogluon/chronos-2-small", "foundation") is None


# =============================================================================
# Tests: is_symmetric_interval
# =============================================================================
@pytest.mark.parametrize(
    "interval, expected",
    [
        ([0.1, 0.9], True),
        ([0.05, 0.95], True),
        ([0.3, 0.7], True),
        ([0.1, 0.8], False),
        ([0.2, 0.7], False),
        ([0.1, 0.95], False),
    ],
    ids=lambda value: f"interval, expected: {value}",
)
def test_is_symmetric_interval_output(interval, expected):
    """
    Test that an interval is symmetric when lower + upper is 1.
    """
    assert is_symmetric_interval(interval) is expected


# =============================================================================
# Tests: validate_interval
# =============================================================================
@pytest.mark.parametrize(
    "interval",
    [[5, 95], [0.9, 0.1], [0.1], [0.1, 0.5, 0.9], [0.0, 0.9], [0.1, 1.0], ["a", 0.9]],
    ids=lambda interval: f"interval: {interval}",
)
def test_validate_interval_ValueError_when_not_two_quantiles(interval):
    """
    Test that an interval that is not `[lower, upper]` with
    0 < lower < upper < 1 is rejected before any script runs.
    """
    err_msg = re.escape(
        f"`interval` must be `[lower, upper]` with 0 < lower < upper < 1, got "
        f"{interval}."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_interval(interval)


@pytest.mark.parametrize(
    "task_type, forecaster",
    [
        ("statistical", "ForecasterStats"),
        ("baseline", "ForecasterEquivalentDate"),
    ],
    ids=["statistical", "baseline"],
)
def test_validate_interval_ValueError_when_asymmetric_for_symmetric_method(
    task_type, forecaster
):
    """
    Test that the statistical and baseline interval methods, which only
    predict symmetric intervals, reject an asymmetric one.
    """
    err_msg = re.escape(
        f"'{forecaster}' predicts symmetric intervals only (lower + upper = 1), "
        f"e.g. [0.1, 0.9], got [0.05, 0.9]."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_interval([0.05, 0.9], task_type=task_type, forecaster=forecaster)


@pytest.mark.parametrize(
    "interval, task_type",
    [(None, None), ([0.1, 0.9], "statistical"), ([0.05, 0.9], "single_series")],
    ids=["no interval", "symmetric", "asymmetric with bootstrapping"],
)
def test_validate_interval_output_when_valid(interval, task_type):
    """
    Test that no interval, a symmetric interval, and an asymmetric interval
    for a bootstrapping method pass.
    """
    assert validate_interval(interval, task_type=task_type) is None


# =============================================================================
# Tests: validate_metrics
# =============================================================================
@pytest.mark.parametrize(
    "metric",
    ["f1_score", "mean_absolute_errorz"],
    ids=["classification score", "unknown name"],
)
def test_validate_metrics_ValueError_when_metric_not_supported(metric):
    """
    Test that names outside the regression metrics are rejected, including
    classification scores, which are higher is better while comparisons
    rank ascending.
    """
    err_msg = re.escape(f"Unknown metric {metric!r}. Supported metrics:")
    with pytest.raises(ValueError, match=err_msg):
        validate_metrics(["mean_absolute_error", metric])


# =============================================================================
# Tests: validate_kwarg_names
# =============================================================================
@pytest.mark.parametrize(
    "key",
    ["alpha=1); import os; (x", "lambda", "1alpha", "", 3],
    ids=["code", "keyword", "starts with a digit", "empty", "not a string"],
)
def test_validate_kwarg_names_ValueError_when_key_not_parameter_name(key):
    """
    Test that a key that is not a string, not an identifier or a Python
    keyword is rejected, since the keys are written into the script.
    """
    err_msg = re.escape(
        f"`estimator_kwargs` keys must be valid Python parameter names, got {key!r}."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_kwarg_names({key: 1})


@pytest.mark.parametrize(
    "estimator_kwargs, type_name",
    [([1, 2], "list"), ("alpha=1", "str"), (3, "int"), ((("alpha", 1),), "tuple")],
    ids=["list", "str", "int", "tuple"],
)
def test_validate_kwarg_names_InvalidInputTypeError_when_not_a_dict(
    estimator_kwargs, type_name
):
    """
    Test that `estimator_kwargs` that is not a dict raises
    InvalidInputTypeError (a TypeError) with the field 'estimator_kwargs'.
    """
    err_msg = re.escape(
        f"`estimator_kwargs` must be a dict of keyword arguments, such as "
        f"{{'alpha': 0.5}}, got {type_name}."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        validate_kwarg_names(estimator_kwargs)

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == "estimator_kwargs"


@pytest.mark.parametrize(
    "estimator_kwargs",
    [None, {}, {"alpha": 1.0, "max_depth": 3, "_private": True}],
    ids=["None", "empty", "parameter names"],
)
def test_validate_kwarg_names_output_when_parameter_names(estimator_kwargs):
    """
    Test that Python parameter names (and no kwargs at all) pass.
    """
    assert validate_kwarg_names(estimator_kwargs) is None


# =============================================================================
# Tests: validate_frequency
# =============================================================================
@pytest.mark.parametrize(
    "frequency",
    ["D\n", "D ", "D') or (1", "1.5h", "\u00b5s", "", ["D"]],
    ids=lambda frequency: f"frequency: {frequency!r}",
)
def test_validate_frequency_ValueError_when_not_an_alias(frequency):
    """
    Test that a frequency with anything other than letters, digits and
    hyphens is rejected, including a trailing newline or space that
    `to_offset` would accept.
    """
    err_msg = re.escape(
        f"`frequency` must be a pandas frequency alias made of letters, "
        f"digits and hyphens, for example 'D', '15min' or 'W-SUN', got "
        f"{frequency!r}."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_frequency(frequency)


@pytest.mark.parametrize(
    "frequency",
    [None, "D", "h", "15min", "MS", "W-SUN", "QS-OCT", "-1MS", "unknown"],
    ids=lambda frequency: f"frequency: {frequency!r}",
)
def test_validate_frequency_output_when_alias(frequency):
    """
    Test that pandas frequency aliases (and None) pass. The syntax is
    checked, not whether pandas knows the alias.
    """
    assert validate_frequency(frequency) is None


# =============================================================================
# Tests: validate_steps
# =============================================================================
@pytest.mark.parametrize(
    "steps",
    [True, False, 0, -3, 12.5, "12", float("nan"), None],
    ids=lambda steps: f"steps: {steps!r}",
)
def test_validate_steps_ValueError_when_not_positive_integer(steps):
    """
    Test that a bool, a non-integer (a string included) and a value lower
    than 1 are rejected instead of being coerced.
    """
    err_msg = re.escape(
        f"`steps` must be an integer greater than or equal to 1, got {steps!r}."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_steps(steps)


@pytest.mark.parametrize(
    "steps, expected",
    [(12, 12), (12.0, 12), (np.int64(5), 5), (1, 1)],
    ids=lambda steps: f"steps: {steps!r}",
)
def test_validate_steps_output_when_integral(steps, expected):
    """
    Test that an integer, a numpy integer or an integral float is returned
    as a Python int.
    """
    result = validate_steps(steps)

    assert result == expected
    assert type(result) is int


# =============================================================================
# Tests: validate_forecaster
# =============================================================================
@pytest.mark.parametrize(
    "forecaster",
    ["ForecasterAutoreg", "ForecasterRecursive\nimport os", None],
    ids=lambda forecaster: f"forecaster: {forecaster!r}",
)
def test_validate_forecaster_ValueError_when_not_supported(forecaster):
    """
    Test that a forecaster outside the supported ones is rejected.
    """
    err_msg = re.escape(
        f"{forecaster!r} is not a supported forecaster. Supported forecasters: "
        f"['ForecasterRecursive', 'ForecasterDirect', "
        f"'ForecasterRecursiveMultiSeries', 'ForecasterDirectMultiVariate', "
        f"'ForecasterStats', 'ForecasterFoundation', 'ForecasterEquivalentDate']."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_forecaster(forecaster, "single_series")


def test_validate_forecaster_ValueError_when_task_type_does_not_match():
    """
    Test that a forecaster whose task type differs from the plan's is
    rejected, since the script template follows the task type.
    """
    err_msg = re.escape(
        "'ForecasterRecursiveMultiSeries' plans have task_type 'multi_series', "
        "got task_type='single_series'."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_forecaster("ForecasterRecursiveMultiSeries", "single_series")


# =============================================================================
# Tests: validate_forecaster_kwargs
# =============================================================================
@pytest.mark.parametrize(
    "forecaster, forecaster_kwargs, err_msg",
    [
        (
            "ForecasterRecursive",
            {"lags": 3, "encoding": "ordinal"},
            "`forecaster_kwargs` of 'ForecasterRecursive' cannot contain "
            "['encoding'].",
        ),
        (
            "ForecasterStats",
            {"lags": 3},
            "`forecaster_kwargs` of 'ForecasterStats' cannot contain ['lags']. "
            "Allowed keys: [].",
        ),
        (
            "ForecasterRecursive",
            {"dropna_from_series": "False or True"},
            "`forecaster_kwargs['dropna_from_series']` must be a bool, got "
            "'False or True'.",
        ),
        (
            "ForecasterRecursive",
            {"categorical_features": ["weekday"]},
            "`forecaster_kwargs['categorical_features']` must be 'auto' or None, "
            "got ['weekday'].",
        ),
        (
            "ForecasterRecursive",
            {"differentiation": True},
            "`forecaster_kwargs['differentiation']` must be None or an integer "
            "greater than or equal to 1, got True.",
        ),
        (
            "ForecasterRecursive",
            {"transformer_y": "MinMaxScaler"},
            "`forecaster_kwargs['transformer_y']` must be None or one of "
            "['StandardScaler'], got 'MinMaxScaler'.",
        ),
        (
            "ForecasterRecursiveMultiSeries",
            {"encoding": "label"},
            "`forecaster_kwargs['encoding']` must be one of ['ordinal', "
            "'ordinal_category', 'onehot', None], got 'label'.",
        ),
        (
            "ForecasterRecursive",
            {"calendar_features": {"features": "['month']", "encoding": None}},
            "`forecaster_kwargs['calendar_features']['features']` must be a "
            "non-empty list of calendar features",
        ),
        (
            "ForecasterRecursive",
            {"calendar_features": {"features": ["month"], "encoding": "sine"}},
            "`forecaster_kwargs['calendar_features']['encoding']` must be one of "
            "['cyclical', 'onehot', 'spline', None], got 'sine'.",
        ),
        (
            "ForecasterRecursive",
            {"calendar_features": {"features": ["month"], "order": 1}},
            "`forecaster_kwargs['calendar_features']` must be None or a dict "
            "with the keys 'features' and 'encoding'",
        ),
        (
            "ForecasterRecursive",
            {"lags": "3"},
            "`lags` must be an int or a list of ints, got '3'.",
        ),
        (
            "ForecasterDirect",
            {"steps": 0},
            "`forecaster_kwargs['steps']` must be an integer greater than or "
            "equal to 1, got 0.",
        ),
        (
            "ForecasterEquivalentDate",
            {"offset": "7", "n_offsets": 1},
            "`forecaster_kwargs['offset']` must be an integer greater than or "
            "equal to 1, got '7'.",
        ),
        (
            "ForecasterRecursive",
            {"differentiation": np.int64(1)},
            "`forecaster_kwargs['differentiation']` must be None or an integer "
            "greater than or equal to 1, got np.int64(1).",
        ),
    ],
    ids=[
        "key of another forecaster",
        "key for a forecaster without arguments",
        "dropna_from_series string",
        "categorical_features list",
        "differentiation bool",
        "transformer outside the map",
        "series encoding",
        "calendar features string",
        "calendar encoding",
        "calendar extra key",
        "lags string",
        "direct steps",
        "baseline offset",
        "numpy integer",
    ],
)
def test_validate_forecaster_kwargs_ValueError_when_outside_closed_set(
    forecaster, forecaster_kwargs, err_msg
):
    """
    Test that a key that does not apply to the forecaster, or a value
    outside its closed set or type, is rejected.
    """
    with pytest.raises(ValueError, match=re.escape(err_msg)):
        validate_forecaster_kwargs(forecaster_kwargs, forecaster)


@pytest.mark.parametrize(
    "forecaster, forecaster_kwargs",
    [
        (
            "ForecasterRecursive",
            {
                "lags": [1, 2, 3, 7],
                "window_features": [{"stats": ["mean", "std"], "window_size": 7}],
                "calendar_features": {
                    "features": ["day_of_week", "month"],
                    "encoding": "cyclical",
                },
                "transformer_y": "StandardScaler",
                "transformer_exog": "StandardScaler",
                "categorical_features": "auto",
                "dropna_from_series": False,
                "differentiation": 1,
            },
        ),
        (
            "ForecasterDirect",
            {"lags": 7, "steps": 12, "calendar_features": None, "transformer_y": None},
        ),
        (
            "ForecasterRecursiveMultiSeries",
            {"lags": 7, "encoding": None, "transformer_series": "StandardScaler"},
        ),
        ("ForecasterDirectMultiVariate", {"lags": 7, "steps": 5}),
        ("ForecasterStats", {}),
        ("ForecasterFoundation", {}),
        ("ForecasterEquivalentDate", {"offset": 7, "n_offsets": 1}),
    ],
    ids=lambda x: f"{x}",
)
def test_validate_forecaster_kwargs_output_when_valid(forecaster, forecaster_kwargs):
    """
    Test that the arguments `plan()` builds for each forecaster, and the
    values skforecast accepts for them, pass.
    """
    assert validate_forecaster_kwargs(forecaster_kwargs, forecaster) is None


# =============================================================================
# Tests: validate_preprocessing_step
# =============================================================================
def test_validate_preprocessing_step_ValueError_when_blocking_snippet_unknown():
    """
    Test that a blocking step whose snippet is not one of the closed
    templates is rejected, even under a known action.
    """
    err_msg = re.escape(
        "The blocking preprocessing step 'drop_duplicates' is not one of the "
        "steps the scripts can contain: its code snippet differs from the one "
        "`plan()` generates. Build the plan with `plan()`, or remove the step."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_preprocessing_step(
            action       = "drop_duplicates",
            code_snippet = "import os",
            blocking     = True,
        )


@pytest.mark.parametrize(
    "action, code_snippet, blocking",
    [
        ("drop_duplicates", "data = data[~data.index.duplicated(keep='first')]", True),
        (
            "drop_duplicates",
            "data = data.drop_duplicates(subset=[{series_id_column}, "
            "{date_column}], keep='first')",
            True,
        ),
        (
            "provide_datetime_index",
            "# Set a DatetimeIndex:\n# data.index = pd.date_range(start=..., "
            "periods=len(data), freq=...)",
            True,
        ),
        ("encode_target", "# Convert target to numeric", True),
        ("handle_gaps", "anything, never written", False),
    ],
    ids=["dedup index", "dedup rows", "datetime index", "encode target", "non-blocking"],
)
def test_validate_preprocessing_step_output_when_template_or_not_blocking(
    action, code_snippet, blocking
):
    """
    Test that the blocking templates (those of 0.3.1 included) and any
    non-blocking step, which is never written into the script, pass.
    """
    assert validate_preprocessing_step(action, code_snippet, blocking) is None


# =============================================================================
# Tests: _validate_lags
# =============================================================================
@pytest.mark.parametrize(
    "lags",
    [None, 1, 7, [1], [1, 2, 7], [7, 2, 1]],
    ids=lambda lags: f"lags: {lags}",
)
def test_validate_lags_passes_when_valid(lags):
    """
    Test that None, a positive int and a non-empty list of unique positive
    ints (in any order) pass validation without raising.
    """
    assert _validate_lags(lags) is None


@pytest.mark.parametrize(
    "lags, match",
    [
        (0, "must be positive integers"),
        (-1, "must be positive integers"),
        (True, "must be an int or a list of ints"),
        ("3", "must be an int or a list of ints"),
        (3.0, "must be an int or a list of ints"),
        ((1, 2), "must be an int or a list of ints"),
        ([], "must not be an empty list"),
        ([0, 1], "must be positive integers"),
        ([-3], "must be positive integers"),
        ([1.5], "must contain ints only"),
        ([1, "3"], "must contain ints only"),
        ([True], "must contain ints only"),
        ([2, 2], "must not contain duplicates"),
        ([1, 2, 1], "must not contain duplicates"),
    ],
    ids=lambda value: f"{value!r}",
)
def test_validate_lags_ValueError_when_invalid(lags, match):
    """
    Test that non-positive, non-int, boolean, empty or duplicated lags
    raise ValueError with a message naming the violated rule.
    """
    with pytest.raises(ValueError, match=match):
        _validate_lags(lags)


# =============================================================================
# Tests: _validate_window_features
# =============================================================================
@pytest.mark.parametrize(
    "window_features",
    [
        None,
        [{"stats": ["mean"], "window_size": 7}],
        [{"stats": ["mean", "std"], "window_size": 3}],
        [
            {"stats": ["mean", "std"], "window_size": 3},
            {"stats": ["mean"], "window_size": 24},
            {"stats": ["ratio_min_max", "coef_variation", "ewm"], "window_size": 168},
        ],
        [
            {"stats": ["mean"], "window_size": 7},
            {"stats": ["mean"], "window_size": 14},
        ],
    ],
    ids=lambda wf: f"window_features: {wf}",
)
def test_validate_window_features_passes_when_valid(window_features):
    """
    Test that valid window_features configurations (including None,
    multi-stat scalar-window entries and the same statistic at different
    window sizes) pass validation without raising.
    """
    assert _validate_window_features(window_features) is None


@pytest.mark.parametrize(
    "window_features, match",
    [
        ({"stats": ["mean"], "window_size": 7}, "must be a list of dicts"),
        ([["mean", 7]], "must be a dict"),
        ([{"stats": ["mean"]}], "missing required key"),
        ([{"window_size": 7}], "missing required key"),
        ([{"stats": "mean", "window_size": 7}], "non-empty list"),
        ([{"stats": [], "window_size": 7}], "non-empty list"),
        ([{"stats": ["mean", "variance"], "window_size": 7}], "unsupported"),
        ([{"stats": ["mean"], "window_size": [3, 7]}], "must be a scalar int"),
        ([{"stats": ["mean"], "window_size": 7.0}], "must be a scalar int"),
        ([{"stats": ["mean"], "window_size": True}], "must be a scalar int"),
        ([{"stats": ["mean"], "window_size": 0}], "must be a positive int"),
        (
            [
                {"stats": ["mean"], "window_size": 7},
                {"stats": ["mean", "std"], "window_size": 7},
            ],
            re.escape("duplicate (stat, window_size) pairs: [('mean', 7)]"),
        ),
    ],
)
def test_validate_window_features_raises_when_invalid(window_features, match):
    """
    Test that malformed window_features (wrong container, missing keys,
    unsupported stats, non-scalar/invalid window_size, or the same statistic
    paired twice with the same window size) raise ValueError.
    """
    with pytest.raises(ValueError, match=match):
        _validate_window_features(window_features)


# =============================================================================
# Tests: closed sets of validate_forecaster_kwargs
# =============================================================================
def test_forecaster_kwargs_keys_cover_every_supported_forecaster():
    """
    Test that the allowed `forecaster_kwargs` keys are defined for exactly
    the supported forecasters, so a forecaster added to one table but not
    the other fails here instead of raising a KeyError during validation.
    """
    assert set(_FORECASTER_KWARGS_KEYS) == set(FORECASTER_TASK_TYPES)


@pytest.mark.parametrize(
    "forecaster",
    [
        "ForecasterRecursive",
        "ForecasterDirect",
        "ForecasterRecursiveMultiSeries",
        "ForecasterDirectMultiVariate",
    ],
    ids=lambda forecaster: f"forecaster: {forecaster}",
)
def test_forecaster_kwargs_keys_include_every_argument_plan_builds(forecaster):
    """
    Test that every argument the recommender builds for a forecaster, with
    every option set, is an allowed key with an accepted value, so no plan
    built by `plan()` is rejected.
    """
    kwargs = build_forecaster_kwargs(
        forecaster         = forecaster,
        task_type          = FORECASTER_TASK_TYPES[forecaster],
        steps              = 5,
        lags               = [1, 2],
        window_features    = [{"stats": ["mean", "std"], "window_size": 3}],
        calendar_features  = {"features": ["day_of_week"], "encoding": "cyclical"},
        transformer_series = "StandardScaler",
        transformer_exog   = "StandardScaler",
        dropna_from_series = False,
    )

    assert set(kwargs) <= _FORECASTER_KWARGS_KEYS[forecaster]
    validate_forecaster_kwargs(kwargs, forecaster)


def test_closed_sets_match_skforecast():
    """
    Test that the calendar features and encodings and the series encodings
    accepted by the validator are the values skforecast accepts: each one
    builds the skforecast object, and a value outside the sets is refused
    by skforecast too.
    """
    for encoding in _CALENDAR_ENCODINGS:
        CalendarFeatures(features=list(_CALENDAR_FEATURES), encoding=encoding)
    for encoding in _SERIES_ENCODINGS:
        ForecasterRecursiveMultiSeries(estimator=Ridge(), lags=3, encoding=encoding)

    with pytest.raises(ValueError, match=re.escape("are not supported")):
        CalendarFeatures(features=["fortnight"])
    with pytest.raises(ValueError, match=re.escape("Encoding must be one of")):
        CalendarFeatures(features=["month"], encoding="sine")
    with pytest.raises(ValueError, match=re.escape("`encoding` must be one of")):
        ForecasterRecursiveMultiSeries(estimator=Ridge(), lags=3, encoding="label")


def test_closed_sets_include_what_plan_builds():
    """
    Test that the calendar features and encodings `plan()` can choose and
    the arguments of the baseline are inside the closed sets, so a plan it
    builds never fails its own validator.
    """
    recommended = {
        feature
        for features in CALENDAR_FEATURE_RELEVANCE.values()
        for feature in features
    }
    assert recommended | {"month"} <= set(_CALENDAR_FEATURES)
    for estimator in [None, "Ridge", "LGBMRegressor"]:
        for task_type in ["single_series", "multi_series", "multivariate"]:
            assert select_calendar_encoding(estimator, task_type) in _CALENDAR_ENCODINGS

    profile = DataProfile(
        n_series       = 1,
        series_lengths = {"y": 100},
        target         = "y",
        index_type     = "datetime",
        frequency      = "D",
    )
    config, _ = select_baseline_config(profile)
    assert set(config) <= _FORECASTER_KWARGS_KEYS["ForecasterEquivalentDate"]
    validate_forecaster_kwargs(config, "ForecasterEquivalentDate")


def test_lag_and_window_validators_reexported_from_utils():
    """
    Test that `_utils` re-exports the validators moved to `_validation`,
    which the CLI and the assistant still import from there.
    """
    assert utils_module._validate_lags is _validate_lags
    assert utils_module._validate_window_features is _validate_window_features


def test_supported_transformers_is_standard_scaler():
    """
    Test the set of transformers a plan can name: the scripts import
    `StandardScaler` directly and always use it for the exogenous
    variables, so adding a name needs the renderers to follow.
    """
    assert SUPPORTED_TRANSFORMERS == ("StandardScaler",)
