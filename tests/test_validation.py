# Unit test _validation

import re
import warnings

import pytest

from skforecast_ai import _validation as validation_module
from skforecast_ai._validation import (
    check_estimator_installed,
    validate_estimator,
    validate_estimator_kwargs,
    validate_interval,
    validate_metrics,
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
        validate_estimator_kwargs("LGBMRegressor", {"n_estimatorz": 10})


def test_validate_estimator_kwargs_output_when_lightgbm_alias():
    """
    Test that LightGBM parameters and aliases accepted through `**kwargs`
    (such as `verbose` or `min_data_in_leaf`) pass without a warning.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        validate_estimator_kwargs(
            "LGBMRegressor",
            {"n_estimators": 10, "verbose": -1, "min_data_in_leaf": 5},
        )


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

    assert validate_estimator_kwargs("Ridge", {"alpah": 2.0}) is None


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


def test_check_estimator_installed_output_when_not_machine_learning(monkeypatch):
    """
    Test that estimators of other families are not checked here (the
    foundation backend has its own check).
    """
    monkeypatch.setattr(
        validation_module.importlib.util, "find_spec", lambda name: None
    )

    assert check_estimator_installed("autogluon/chronos-2-small", "foundation") is None
    assert check_estimator_installed("Arima", "statistical") is None


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
