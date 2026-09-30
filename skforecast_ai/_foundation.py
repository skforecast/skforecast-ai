################################################################################
#                           Foundation models                                  #
#                                                                              #
# Validation of foundation model plans against the capabilities that          #
# skforecast declares for each adapter                                         #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from importlib.metadata import PackageNotFoundError, distribution
from skforecast.foundation import FoundationModelInfo, get_model_info, list_adapters

from ._constants import DEFAULT_FOUNDATION_MODEL_ID
from ._validation import validate_interval

# Same tolerance skforecast uses to match a quantile level against the grid
# of a backend, so a level accepted here is never rejected at prediction.
_QUANTILE_TOLERANCE = 1e-9


def resolve_foundation_model(model_id: str) -> FoundationModelInfo:
    """
    Resolve the capabilities of a foundation model from its model ID.

    The adapter is resolved by skforecast from the prefix of `model_id`,
    without importing the backend library or loading the weights, so every
    capability of the plan comes from skforecast and none is duplicated
    here.

    Parameters
    ----------
    model_id : str
        Hugging Face model ID, e.g. `'autogluon/chronos-2-small'`.

    Returns
    -------
    info : FoundationModelInfo
        Capabilities and requirements of `model_id`.

    Raises
    ------
    TypeError
        When `model_id` is not a string.
    ValueError
        When no skforecast adapter serves `model_id`.
    """
    if not isinstance(model_id, str):
        raise TypeError(
            f"The estimator of 'ForecasterFoundation' must be a Hugging Face "
            f"model ID (str), got {type(model_id).__name__}."
        )
    try:
        return get_model_info(model_id)
    except ValueError:
        prefixes = [
            prefix
            for adapter in list_adapters()
            for prefix in adapter.model_id_prefixes
        ]
        raise ValueError(
            f"'{model_id}' is not a foundation model supported by skforecast. "
            f"Pass its Hugging Face model ID as `estimator`, for example "
            f"'{DEFAULT_FOUNDATION_MODEL_ID}'. Supported model ID prefixes: "
            f"{prefixes}."
        ) from None


def foundation_backend_installed(info: FoundationModelInfo) -> bool:
    """
    Check whether the backend package of a foundation model is installed.

    The check reads the installed distributions and imports nothing, so it
    is cheap and never loads a deep learning framework. Only the package
    is checked: extras such as `timesfm[torch]` are not.

    Parameters
    ----------
    info : FoundationModelInfo
        Capabilities of the foundation model; `info.backend_package` is the
        name passed to `pip install`.

    Returns
    -------
    installed : bool
        Whether the distribution of `info.backend_package` is installed.
    """
    package = info.backend_package.split("[", 1)[0]
    try:
        distribution(package)
    except PackageNotFoundError:
        return False
    return True


def validate_foundation_estimator_kwargs(estimator_kwargs: dict | None) -> None:
    """
    Reject a model ID given in the estimator keyword arguments.

    The model ID is the `estimator` of a foundation plan. Accepting it in
    `estimator_kwargs` as well would let the plan name one model and the
    script load another.

    Parameters
    ----------
    estimator_kwargs : dict, None
        Keyword arguments for `FoundationModel`.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        When `estimator_kwargs` contains `'model_id'`.
    """
    if estimator_kwargs and "model_id" in estimator_kwargs:
        raise ValueError(
            f"`estimator_kwargs` cannot contain 'model_id' for "
            f"'ForecasterFoundation'. Pass the model ID as `estimator` "
            f"instead, e.g. estimator='{estimator_kwargs['model_id']}'."
        )


def validate_foundation_interval(
    info: FoundationModelInfo,
    interval: list[float] | None,
) -> None:
    """
    Check that a foundation model can predict the requested interval.

    Foundation models predict the interval bounds as quantiles, together
    with the median. Backends with a fixed quantile grid only predict the
    levels of that grid, so the bounds must belong to it.

    Parameters
    ----------
    info : FoundationModelInfo
        Capabilities of the foundation model.
    interval : list of float, None
        Prediction interval quantiles as `[lower, upper]`. None means no
        interval, which is always valid.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        When `interval` is not `[lower, upper]` with `0 < lower < upper < 1`,
        or when a bound is not in the quantile grid of the backend.
    """
    if interval is None:
        return
    validate_interval(interval)
    grid = info.supported_quantiles
    if grid is None:
        return
    unsupported = [
        bound
        for bound in interval
        if not any(abs(bound - level) < _QUANTILE_TOLERANCE for level in grid)
    ]
    if unsupported:
        raise ValueError(
            f"'{info.model_id}' ({info.adapter}) only predicts the quantile "
            f"levels {list(grid)}, so `interval` {interval} cannot be "
            f"computed: {unsupported} not in that list. Choose both bounds "
            f"from it, e.g. [0.1, 0.9]."
        )


def foundation_exog_columns(
    info: FoundationModelInfo,
    exog_columns: list[str],
    categorical_exog: list[str],
) -> list[str]:
    """
    Exogenous columns a foundation model can use.

    Parameters
    ----------
    info : FoundationModelInfo
        Capabilities of the foundation model.
    exog_columns : list of str
        Exogenous columns of the data.
    categorical_exog : list of str
        Exogenous columns with a non-numeric dtype.

    Returns
    -------
    columns : list of str
        No column when the backend does not accept covariates; the numeric
        columns when it does not accept categorical covariates natively;
        otherwise every exogenous column.
    """
    if not info.allow_exog:
        return []
    if not info.supports_categorical_covariates:
        return [col for col in exog_columns if col not in categorical_exog]
    return list(exog_columns)


def validate_foundation_plan(
    estimator: str | None,
    estimator_kwargs: dict | None,
    interval: list[float] | None,
) -> FoundationModelInfo:
    """
    Validate the model and options of a `ForecasterFoundation` plan.

    Parameters
    ----------
    estimator : str, None
        Hugging Face model ID of the foundation model.
    estimator_kwargs : dict, None
        Keyword arguments for `FoundationModel`.
    interval : list of float, None
        Prediction interval quantiles as `[lower, upper]`.

    Returns
    -------
    info : FoundationModelInfo
        Capabilities and requirements of `estimator`.

    Raises
    ------
    ValueError
        When `estimator` is missing or unsupported, when `estimator_kwargs`
        contains `'model_id'`, or when the backend cannot predict
        `interval`.
    """
    if estimator is None:
        raise ValueError(
            f"A 'ForecasterFoundation' plan needs the Hugging Face model ID "
            f"of the foundation model as `estimator`, e.g. "
            f"'{DEFAULT_FOUNDATION_MODEL_ID}'."
        )
    info = resolve_foundation_model(estimator)
    validate_foundation_estimator_kwargs(estimator_kwargs)
    validate_foundation_interval(info, interval)

    return info
