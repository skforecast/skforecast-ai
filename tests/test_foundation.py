# Unit test _foundation

import dataclasses
import re

import pytest

from skforecast.foundation import get_model_info

from skforecast_ai._foundation import (
    foundation_backend_installed,
    foundation_exog_columns,
    resolve_foundation_model,
    validate_foundation_estimator_kwargs,
    validate_foundation_interval,
    validate_foundation_plan,
)


# =============================================================================
# Tests: resolve_foundation_model
# =============================================================================
@pytest.mark.parametrize(
    "model_id, expected_adapter",
    [
        ("autogluon/chronos-2-small", "ChronosAdapter"),
        ("amazon/chronos-2", "ChronosAdapter"),
        ("google/timesfm-3.0-pytorch", "TimesFM3Adapter"),
        ("Salesforce/moirai-2.0-R-small", "MoiraiAdapter"),
    ],
    ids=lambda dt: f"model_id, expected_adapter: {dt}",
)
def test_resolve_foundation_model_output(model_id, expected_adapter):
    """
    Test that resolve_foundation_model returns the skforecast model info of
    the adapter that serves the model ID, including variants of a provider.
    """
    info = resolve_foundation_model(model_id)

    assert info.model_id == model_id
    assert info.adapter == expected_adapter


@pytest.mark.parametrize(
    "model_id",
    ["Chronos-2", "google/timesfm-1.0-200m"],
    ids=lambda dt: f"model_id: {dt}",
)
def test_resolve_foundation_model_ValueError_when_model_not_supported(model_id):
    """
    Test that an ID no skforecast adapter serves, including the former
    'Chronos-2' label, raises ValueError that shows how to pass the model ID
    and lists the supported prefixes.
    """
    err_msg = re.escape(
        f"'{model_id}' is not a foundation model supported by skforecast. "
        f"Pass its Hugging Face model ID as `estimator`, for example "
        f"'autogluon/chronos-2-small'. Supported model ID prefixes: "
        f"['amazon/chronos-2', 'autogluon/chronos-2',"
    )
    with pytest.raises(ValueError, match=err_msg):
        resolve_foundation_model(model_id)


def test_resolve_foundation_model_TypeError_when_model_id_not_str():
    """
    Test that a model ID that is not a string raises TypeError.
    """
    err_msg = re.escape(
        "The estimator of 'ForecasterFoundation' must be a Hugging Face "
        "model ID (str), got int."
    )
    with pytest.raises(TypeError, match=err_msg):
        resolve_foundation_model(1)


# =============================================================================
# Tests: foundation_backend_installed
# =============================================================================
@pytest.mark.parametrize(
    "backend_package, expected",
    [
        ("pandas", True),
        ("pandas[performance]", True),
        ("package-that-is-not-installed-abc", False),
        ("package-that-is-not-installed-abc[torch]", False),
    ],
    ids=lambda dt: f"backend_package, expected: {dt}",
)
def test_foundation_backend_installed_output(backend_package, expected):
    """
    Test that the backend check reads the installed distribution named by
    `backend_package`, ignoring the extras.
    """
    info = dataclasses.replace(
        get_model_info("autogluon/chronos-2-small"),
        backend_package=backend_package,
    )

    assert foundation_backend_installed(info) is expected


# =============================================================================
# Tests: validate_foundation_estimator_kwargs
# =============================================================================
@pytest.mark.parametrize(
    "estimator_kwargs",
    [None, {}, {"context_length": 1024}],
    ids=lambda dt: f"estimator_kwargs: {dt}",
)
def test_validate_foundation_estimator_kwargs_no_error_when_no_model_id(
    estimator_kwargs,
):
    """
    Test that estimator kwargs without a model ID are accepted.
    """
    validate_foundation_estimator_kwargs(estimator_kwargs)


def test_validate_foundation_estimator_kwargs_ValueError_when_model_id():
    """
    Test that a model ID in the estimator kwargs raises ValueError that
    points to `estimator`.
    """
    err_msg = re.escape(
        "`estimator_kwargs` cannot contain 'model_id' for "
        "'ForecasterFoundation'. Pass the model ID as `estimator` instead, "
        "e.g. estimator='google/timesfm-3.0-pytorch'."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_foundation_estimator_kwargs(
            {"model_id": "google/timesfm-3.0-pytorch", "context_length": 512}
        )


# =============================================================================
# Tests: validate_foundation_interval
# =============================================================================
@pytest.mark.parametrize(
    "model_id, interval",
    [
        ("autogluon/chronos-2-small", None),
        ("autogluon/chronos-2-small", [0.025, 0.975]),
        ("google/timesfm-3.0-pytorch", [0.1, 0.9]),
        ("google/timesfm-3.0-pytorch", [0.2, 0.7]),
        ("taharnbl/TS-ICL", [0.05, 0.95]),
    ],
    ids=lambda dt: f"model_id, interval: {dt}",
)
def test_validate_foundation_interval_no_error_when_interval_supported(
    model_id, interval
):
    """
    Test that an interval is accepted when the model predicts any quantile
    level, or when both bounds are in its quantile grid (0.1 steps for
    TimesFM, 0.01 steps for TS-ICL).
    """
    validate_foundation_interval(get_model_info(model_id), interval)


def test_validate_foundation_interval_ValueError_when_bound_not_in_grid():
    """
    Test that an interval with a bound outside the quantile grid of the
    model raises ValueError listing the grid and the unsupported bounds.
    """
    err_msg = re.escape(
        "'google/timesfm-3.0-pytorch' (TimesFM3Adapter) only predicts the "
        "quantile levels [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9], so "
        "`interval` [0.05, 0.9] cannot be computed: [0.05] not in that list. "
        "Choose both bounds from it, e.g. [0.1, 0.9]."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_foundation_interval(
            get_model_info("google/timesfm-3.0-pytorch"), [0.05, 0.9]
        )


@pytest.mark.parametrize(
    "interval",
    [[0.9, 0.1], [0.0, 0.9], [0.1, 1.0], [0.1], [0.1, 0.5, 0.9]],
    ids=lambda dt: f"interval: {dt}",
)
def test_validate_foundation_interval_ValueError_when_interval_malformed(interval):
    """
    Test that an interval that is not `[lower, upper]` with
    0 < lower < upper < 1 raises ValueError, even for a model that predicts
    any quantile level.
    """
    err_msg = re.escape(
        f"`interval` must be `[lower, upper]` with 0 < lower < upper < 1, "
        f"got {interval}."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_foundation_interval(
            get_model_info("autogluon/chronos-2-small"), interval
        )


# =============================================================================
# Tests: foundation_exog_columns
# =============================================================================
@pytest.mark.parametrize(
    "model_id, expected",
    [
        ("autogluon/chronos-2-small", ["promo", "weekday"]),
        ("google/timesfm-3.0-pytorch", ["promo"]),
        ("Salesforce/moirai-2.0-R-small", []),
    ],
    ids=lambda dt: f"model_id, expected: {dt}",
)
def test_foundation_exog_columns_output(model_id, expected):
    """
    Test that every exog column is used by a model that accepts categorical
    covariates, only the numeric ones by a model that does not, and none by
    a model without covariate support.
    """
    columns = foundation_exog_columns(
        info             = get_model_info(model_id),
        exog_columns     = ["promo", "weekday"],
        categorical_exog = ["weekday"],
    )

    assert columns == expected


# =============================================================================
# Tests: validate_foundation_plan
# =============================================================================
def test_validate_foundation_plan_output():
    """
    Test that validate_foundation_plan returns the model info of a valid
    foundation plan.
    """
    info = validate_foundation_plan(
        estimator        = "google/timesfm-3.0-pytorch",
        estimator_kwargs = {"context_length": 1024},
        interval         = [0.1, 0.9],
    )

    assert info.adapter == "TimesFM3Adapter"
    assert info.default_context_length == 2048


def test_validate_foundation_plan_ValueError_when_estimator_is_None():
    """
    Test that a foundation plan without an estimator raises ValueError.
    """
    err_msg = re.escape(
        "A 'ForecasterFoundation' plan needs the Hugging Face model ID of "
        "the foundation model as `estimator`, e.g. 'autogluon/chronos-2-small'."
    )
    with pytest.raises(ValueError, match=err_msg):
        validate_foundation_plan(
            estimator        = None,
            estimator_kwargs = {},
            interval         = None,
        )
