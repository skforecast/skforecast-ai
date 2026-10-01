################################################################################
#                               Validation                                     #
#                                                                              #
# Checks of the user inputs that end up in a plan and in its generated script #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

# The checks only depend on the constants and the standard library, so the
# plan schema can call them from its model validator without importing the
# assistant helpers (which import the schemas themselves).

from __future__ import annotations
import difflib
import importlib
import importlib.util
import inspect
import keyword
import numbers
import re
import warnings
from ._constants import (
    ALLOWED_METRICS,
    PASSTHROUGH_KWARGS_ESTIMATORS,
    SUPPORTED_ESTIMATORS,
)

# Task types whose estimator is a scikit-learn compatible regressor.
_ML_TASK_TYPES = ("single_series", "multi_series", "multivariate")

# Task types whose interval method (native ARIMA intervals, conformal
# intervals of the baseline) only predicts symmetric intervals.
_SYMMETRIC_INTERVAL_TASK_TYPES = ("statistical", "baseline")

# Parameter lists up to this length are quoted in full in error messages;
# longer ones (CatBoost has about a hundred) only get the closest match.
_MAX_LISTED_PARAMS = 30

# Distribution name to `pip install` when it differs from the module name.
_PIP_NAMES = {"sklearn": "scikit-learn"}

# A pandas frequency alias is made of letters, digits and hyphens ('D',
# '15min', 'W-SUN', 'QS-OCT'), as is everything `pd.infer_freq` returns,
# including '-1MS' for a descending index. `to_offset` is not used for the
# check: it accepts trailing whitespace and newlines ('D\n') and emits a
# FutureWarning for deprecated aliases.
_FREQUENCY_PATTERN = re.compile(r"[A-Za-z0-9-]+")


def validate_frequency(frequency: str | None) -> None:
    """
    Check the syntax of a pandas frequency alias.

    The frequency of a profile is written into the generated script
    (`asfreq()`, `reshape_series_long_to_dict(freq=...)`), so a profile
    loaded from JSON must hold an alias and nothing else.

    Parameters
    ----------
    frequency : str, None
        Frequency of the profile. None means unknown, which is always valid.

    Returns
    -------
    None

    Notes
    -----
    A `ValueError` is raised unless `frequency` is made only of letters,
    digits and hyphens. Whether pandas knows the alias is not checked here.
    """

    if frequency is None:
        return
    if not isinstance(frequency, str) or not _FREQUENCY_PATTERN.fullmatch(frequency):
        raise ValueError(
            f"`frequency` must be a pandas frequency alias made of letters, "
            f"digits and hyphens, for example 'D', '15min' or 'W-SUN', got "
            f"{frequency!r}."
        )


def validate_kwarg_names(estimator_kwargs: dict | None) -> None:
    """
    Check that every key of `estimator_kwargs` is a Python parameter name.

    The keys are written into the generated script as `key=value`, so this
    runs in the plan validator and again when the script is rendered, for a
    plan that skipped the validator.

    Parameters
    ----------
    estimator_kwargs : dict, None
        Keyword arguments for the estimator.

    Returns
    -------
    None

    Notes
    -----
    A `ValueError` is raised for a key that is not a string, not an
    identifier, or a Python keyword.
    """

    for key in estimator_kwargs or {}:
        if (
            not isinstance(key, str)
            or not key.isidentifier()
            or keyword.iskeyword(key)
        ):
            raise ValueError(
                f"`estimator_kwargs` keys must be valid Python parameter "
                f"names, got {key!r}."
            )


def validate_estimator(
    estimator: str | None,
    estimator_kwargs: dict | None,
    task_type: str,
) -> None:
    """
    Check the estimator name and the keys of its keyword arguments.

    The name and the keys are written into the generated script, so they are
    checked before anything is rendered: the name against the estimators the
    script can import, and every key as a valid Python parameter name. The
    check imports nothing, so it is also cheap enough for the model
    validator of `ForecastPlan`.

    Parameters
    ----------
    estimator : str, None
        Estimator name of the plan.
    estimator_kwargs : dict, None
        Keyword arguments for the estimator.
    task_type : str
        Forecasting task category of the plan.

    Returns
    -------
    None

    Notes
    -----
    A `ValueError` is raised for a machine-learning estimator outside
    `SUPPORTED_ESTIMATORS`, for an estimator other than `'Arima'` in a
    statistical plan (the script always builds an ARIMA model), and for a
    key that is not a valid Python parameter name. Foundation and baseline
    estimators are validated elsewhere.
    """

    validate_kwarg_names(estimator_kwargs)

    # None reaches here only from a plan built by hand, never from `plan()`;
    # rendering such a plan raises instead of writing a name into the script.
    if (
        task_type in _ML_TASK_TYPES
        and estimator is not None
        and estimator not in SUPPORTED_ESTIMATORS
    ):
        raise ValueError(
            f"{estimator!r} is not a supported estimator. Supported "
            f"estimators: {list(SUPPORTED_ESTIMATORS)}."
        )

    if task_type == "statistical" and estimator not in (None, "Arima"):
        raise ValueError(
            f"'ForecasterStats' uses an ARIMA model, so estimator={estimator!r} "
            f"cannot be applied. Omit `estimator`, and set the ARIMA options "
            f"through `estimator_kwargs`."
        )


def _estimator_param_names(cls: type) -> set[str]:
    """
    Collect the parameter names an estimator constructor accepts.

    Walks the class hierarchy while the constructors forward `**kwargs` to
    their parent, as XGBoost does (`XGBRegressor` only names `objective`
    and passes the rest to `XGBModel`), so the named parameters of the
    whole chain are collected.

    Parameters
    ----------
    cls : type
        Estimator class.

    Returns
    -------
    names : set of str
        Named parameters of the constructor chain.
    """

    names: set[str] = set()
    variadic = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    for klass in cls.__mro__:
        init = klass.__dict__.get("__init__")
        if init is None:
            continue
        try:
            params = list(inspect.signature(init).parameters.values())
        except (TypeError, ValueError):
            break
        names.update(
            p.name for p in params if p.name != "self" and p.kind not in variadic
        )
        if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
            break

    return names


def _library_param_names(estimator: str) -> set[str]:
    """
    Collect the extra parameter names a library accepts through `**kwargs`.

    LightGBM publishes every parameter and alias it accepts (for example
    `verbose` or `min_data_in_leaf`), which are valid although they are not
    named in the constructor. The list comes from a private helper, so any
    failure falls back to the constructor names alone.

    Parameters
    ----------
    estimator : str
        Name of a supported estimator.

    Returns
    -------
    names : set of str
        Extra parameter names, empty when the library publishes none.
    """

    if estimator != "LGBMRegressor":
        return set()
    try:
        from lightgbm.basic import _ConfigAliases

        aliases = _ConfigAliases._get_all_param_aliases()
    except Exception:
        return set()

    return {name for names in aliases.values() for name in names}


def validate_estimator_kwargs(
    estimator: str,
    estimator_kwargs: dict | None,
) -> None:
    """
    Check the keyword argument names against the estimator constructor.

    Only for the supported machine-learning estimators, and only when their
    package is installed; otherwise the names cannot be read and the check
    is skipped (running the plan then fails with an install message). The
    class is imported but not instantiated.

    Parameters
    ----------
    estimator : str
        Name of a supported estimator.
    estimator_kwargs : dict, None
        Keyword arguments for the estimator.

    Returns
    -------
    None

    Notes
    -----
    An unknown name raises a `ValueError`, except for the estimators in
    `PASSTHROUGH_KWARGS_ESTIMATORS` (LightGBM, XGBoost), which forward
    unknown names to the library as extra parameters and accept parameter
    aliases: they get a `UserWarning`, since the library ignores a name
    that does not exist without an error.
    """

    if not estimator_kwargs or estimator not in SUPPORTED_ESTIMATORS:
        return
    module_name = SUPPORTED_ESTIMATORS[estimator]
    if importlib.util.find_spec(module_name.split(".")[0]) is None:
        return
    cls = getattr(importlib.import_module(module_name), estimator)
    names = _estimator_param_names(cls)
    extra_names = _library_param_names(estimator)

    for key in estimator_kwargs:
        if key in names or key in extra_names:
            continue
        match = difflib.get_close_matches(key, sorted(names | extra_names), n=1)
        hint = f" Did you mean {match[0]!r}?" if match else ""
        if estimator in PASSTHROUGH_KWARGS_ESTIMATORS:
            warnings.warn(
                f"{key!r} is not a named parameter of {estimator}. It is "
                f"passed to the library as an extra parameter, which ignores "
                f"it without an error if it does not exist.{hint}",
                UserWarning,
                stacklevel=3,
            )
            continue
        listed = (
            f" Valid parameters: {sorted(names)}."
            if len(names) <= _MAX_LISTED_PARAMS else ""
        )
        raise ValueError(
            f"{estimator} has no parameter {key!r}.{hint}{listed}"
        )


def check_estimator_installed(
    estimator: str | None,
    task_type: str,
) -> None:
    """
    Check that the package of a machine-learning estimator is installed.

    Called before a plan is executed, not when a script is only rendered:
    a script may run on another machine. The check imports nothing.

    Parameters
    ----------
    estimator : str, None
        Estimator name of the plan.
    task_type : str
        Forecasting task category of the plan.

    Returns
    -------
    None

    Notes
    -----
    A `ValueError` with the `pip install` command is raised when the package
    is missing, instead of an `ImportError` inside the executed script.
    """

    if task_type not in _ML_TASK_TYPES or estimator not in SUPPORTED_ESTIMATORS:
        return
    package = SUPPORTED_ESTIMATORS[estimator].split(".")[0]
    if importlib.util.find_spec(package) is None:
        pip_name = _PIP_NAMES.get(package, package)
        raise ValueError(
            f"{estimator} needs the '{pip_name}' package, which is not "
            f"installed (pip install {pip_name})."
        )


def validate_interval(
    interval: list[float] | None,
    task_type: str | None = None,
    forecaster: str | None = None,
) -> None:
    """
    Check a prediction interval given as `[lower, upper]` quantiles.

    Parameters
    ----------
    interval : list of float, None
        Prediction interval quantiles. None means no interval, which is
        always valid.
    task_type : str, default None
        Forecasting task category of the plan. The statistical and baseline
        interval methods only predict symmetric intervals, which is checked
        when it is given.
    forecaster : str, default None
        Forecaster class name, quoted in the symmetry message.

    Returns
    -------
    None

    Notes
    -----
    A `ValueError` is raised unless `interval` holds exactly two numbers
    with `0 < lower < upper < 1`, and, for statistical and baseline plans,
    unless `lower + upper = 1`.
    """

    if interval is None:
        return
    valid = (
        isinstance(interval, (list, tuple))
        and len(interval) == 2
        and all(
            isinstance(bound, numbers.Real) and not isinstance(bound, bool)
            for bound in interval
        )
        and 0 < interval[0] < interval[1] < 1
    )
    if not valid:
        raise ValueError(
            f"`interval` must be `[lower, upper]` with "
            f"0 < lower < upper < 1, got {interval}."
        )
    if (
        task_type in _SYMMETRIC_INTERVAL_TASK_TYPES
        and abs(interval[0] + interval[1] - 1) > 1e-9
    ):
        raise ValueError(
            f"'{forecaster}' predicts symmetric intervals only "
            f"(lower + upper = 1), e.g. [0.1, 0.9], got {interval}."
        )


def validate_metrics(metrics: list[str]) -> None:
    """
    Check metric names against the regression metrics skforecast computes.

    Parameters
    ----------
    metrics : list of str
        Metric names.

    Returns
    -------
    None

    Notes
    -----
    A `ValueError` listing `ALLOWED_METRICS` is raised for any other name,
    including skforecast's classification scores, which are higher is
    better while `compare()` ranks ascending.
    """

    for metric in metrics:
        if metric not in ALLOWED_METRICS:
            raise ValueError(
                f"Unknown metric {metric!r}. Supported metrics: "
                f"{list(ALLOWED_METRICS)}."
            )
