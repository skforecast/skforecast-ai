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
    ALLOWED_WINDOW_STATS,
    BLOCKING_PREPROCESSING_TEMPLATES,
    FORECASTER_TASK_TYPES,
    ML_TASK_TYPES,
    PASSTHROUGH_KWARGS_ESTIMATORS,
    SUPPORTED_ESTIMATORS,
    SUPPORTED_TRANSFORMERS,
)
from .exceptions import InvalidInputError, InvalidInputTypeError

# Task types whose interval method (native ARIMA intervals, conformal
# intervals of the baseline) only predicts symmetric intervals.
_SYMMETRIC_INTERVAL_TASK_TYPES = ("statistical", "baseline")

# Parameter lists up to this length are quoted in full in error messages;
# longer ones (CatBoost has about a hundred) only get the closest match.
_MAX_LISTED_PARAMS = 30

# Distribution name to `pip install` when it differs from the module name.
_PIP_NAMES = {"sklearn": "scikit-learn"}

# Keys of `forecaster_kwargs` per forecaster: the arguments `plan()` builds
# (the same since 0.3.1, plus `differentiation`, which the scripts write
# when a plan carries it). The scripts write every key except `steps`, which
# the direct forecasters keep for compatibility and the scripts take from
# `ForecastPlan.steps`.
_ML_FORECASTER_KWARGS = frozenset({
    "lags",
    "window_features",
    "calendar_features",
    "transformer_exog",
    "categorical_features",
    "dropna_from_series",
    "differentiation",
})
_FORECASTER_KWARGS_KEYS: dict[str, frozenset[str]] = {
    "ForecasterRecursive": _ML_FORECASTER_KWARGS | {"transformer_y"},
    "ForecasterDirect": _ML_FORECASTER_KWARGS | {"transformer_y", "steps"},
    "ForecasterRecursiveMultiSeries": (
        _ML_FORECASTER_KWARGS | {"transformer_series", "encoding"}
    ),
    "ForecasterDirectMultiVariate": (
        _ML_FORECASTER_KWARGS | {"transformer_series", "steps"}
    ),
    "ForecasterStats": frozenset(),
    "ForecasterFoundation": frozenset(),
    "ForecasterEquivalentDate": frozenset({"offset", "n_offsets"}),
}

# Values skforecast accepts for the series encoding of
# `ForecasterRecursiveMultiSeries`, and for the features and the encoding of
# `CalendarFeatures`.
_SERIES_ENCODINGS = ("ordinal", "ordinal_category", "onehot", None)
_CALENDAR_FEATURES = (
    "year", "month", "week", "day_of_week", "day_of_month", "day_of_year",
    "weekend", "hour", "minute", "second", "quarter",
)
_CALENDAR_ENCODINGS = ("cyclical", "onehot", "spline", None)

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
        raise InvalidInputError(
            f"`frequency` must be a pandas frequency alias made of letters, "
            f"digits and hyphens, for example 'D', '15min' or 'W-SUN', got "
            f"{frequency!r}.",
            field = "frequency",
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
    A `TypeError` is raised when `estimator_kwargs` is not a dict, and a
    `ValueError` for a key that is not a string, not an identifier, or a
    Python keyword.
    """

    if estimator_kwargs is not None and not isinstance(estimator_kwargs, dict):
        raise InvalidInputTypeError(
            f"`estimator_kwargs` must be a dict of keyword arguments, such as "
            f"{{'alpha': 0.5}}, got {type(estimator_kwargs).__name__}.",
            field = "estimator_kwargs",
        )
    for key in estimator_kwargs or {}:
        if (
            not isinstance(key, str)
            or not key.isidentifier()
            or keyword.iskeyword(key)
        ):
            raise InvalidInputError(
                f"`estimator_kwargs` keys must be valid Python parameter "
                f"names, got {key!r}.",
                field = "estimator_kwargs",
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
        task_type in ML_TASK_TYPES
        and estimator is not None
        and estimator not in SUPPORTED_ESTIMATORS
    ):
        raise InvalidInputError(
            f"{estimator!r} is not a supported estimator. Supported "
            f"estimators: {list(SUPPORTED_ESTIMATORS)}.",
            field = "estimator",
        )

    if task_type == "statistical" and estimator not in (None, "Arima"):
        raise InvalidInputError(
            f"'ForecasterStats' uses an ARIMA model, so estimator={estimator!r} "
            f"cannot be applied. Omit `estimator`, and set the ARIMA options "
            f"through `estimator_kwargs`.",
            field = "estimator",
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
) -> list[str]:
    """
    Check the keyword argument names against the estimator constructor.

    Only for the supported machine-learning estimators, when their package
    is installed (otherwise the names cannot be read and the check is
    skipped: running the plan then fails with an install message), and for
    the `Arima` model of `ForecasterStats`. The class is imported but not
    instantiated.

    Parameters
    ----------
    estimator : str
        Name of a supported estimator.
    estimator_kwargs : dict, None
        Keyword arguments for the estimator.

    Returns
    -------
    warning_messages : list of str
        Text of each warning emitted, in order, so the caller can keep it
        with the plan. Empty when every name is known or nothing is checked.

    Notes
    -----
    An unknown name raises a `ValueError`, except for the estimators in
    `PASSTHROUGH_KWARGS_ESTIMATORS` (LightGBM, XGBoost), which forward
    unknown names to the library as extra parameters and accept parameter
    aliases: they get a `UserWarning`, since the library ignores a name
    that does not exist without an error.
    """

    warning_messages: list[str] = []
    if not estimator_kwargs:
        return warning_messages
    if estimator == "Arima":
        # The ARIMA model of ForecasterStats, which skforecast ships.
        from skforecast.stats import Arima

        cls = Arima
    elif estimator in SUPPORTED_ESTIMATORS:
        module_name = SUPPORTED_ESTIMATORS[estimator]
        if importlib.util.find_spec(module_name.split(".")[0]) is None:
            return warning_messages
        cls = getattr(importlib.import_module(module_name), estimator)
    else:
        return warning_messages
    names = _estimator_param_names(cls)
    extra_names = _library_param_names(estimator)

    for key in estimator_kwargs:
        if key in names or key in extra_names:
            continue
        match = difflib.get_close_matches(key, sorted(names | extra_names), n=1)
        hint = f" Did you mean {match[0]!r}?" if match else ""
        if estimator in PASSTHROUGH_KWARGS_ESTIMATORS:
            message = (
                f"{key!r} is not a named parameter of {estimator}. It is "
                f"passed to the library as an extra parameter, which ignores "
                f"it without an error if it does not exist.{hint}"
            )
            warnings.warn(message, UserWarning, stacklevel=3)
            warning_messages.append(message)
            continue
        listed = (
            f" Valid parameters: {sorted(names)}."
            if len(names) <= _MAX_LISTED_PARAMS else ""
        )
        raise InvalidInputError(
            f"{estimator} has no parameter {key!r}.{hint}{listed}",
            field = "estimator_kwargs",
        )

    return warning_messages


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
    is missing, instead of an `ImportError` inside the executed script. For
    a `ForecasterFoundation` plan, `estimator` is the model ID and the
    backend package of the model is checked (`check_foundation_backend`).
    """

    if task_type == "foundation":
        # Imported here: `_foundation` imports this module.
        from ._foundation import check_foundation_backend

        check_foundation_backend(estimator)
        return
    if task_type not in ML_TASK_TYPES or estimator not in SUPPORTED_ESTIMATORS:
        return
    package = SUPPORTED_ESTIMATORS[estimator].split(".")[0]
    if importlib.util.find_spec(package) is None:
        pip_name = _PIP_NAMES.get(package, package)
        raise InvalidInputError(
            f"{estimator} needs the '{pip_name}' package, which is not "
            f"installed (pip install {pip_name}).",
            code  = "missing_dependency",
            field = "estimator",
        )


def is_symmetric_interval(interval: list[float]) -> bool:
    """
    Tell whether `[lower, upper]` quantiles are symmetric (`lower + upper`
    is 1), as the statistical and baseline interval methods need.

    Parameters
    ----------
    interval : list of float
        Prediction interval quantiles, already validated.

    Returns
    -------
    symmetric : bool
        Whether `lower + upper` is 1.
    """
    return abs(interval[0] + interval[1] - 1) <= 1e-9


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
        raise InvalidInputError(
            f"`interval` must be `[lower, upper]` with "
            f"0 < lower < upper < 1, got {interval}.",
            field = "interval",
        )
    if (
        task_type in _SYMMETRIC_INTERVAL_TASK_TYPES
        and not is_symmetric_interval(interval)
    ):
        raise InvalidInputError(
            f"'{forecaster}' predicts symmetric intervals only "
            f"(lower + upper = 1), e.g. [0.1, 0.9], got {interval}.",
            field = "interval",
        )


def validate_metrics(metrics: list[str], field: str = "metric") -> None:
    """
    Check metric names against the regression metrics skforecast computes.

    Parameters
    ----------
    metrics : list of str
        Metric names.
    field : str, default 'metric'
        Name of the argument or plan field reported as `field` of the error.

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
            raise InvalidInputError(
                f"Unknown metric {metric!r}. Supported metrics: "
                f"{list(ALLOWED_METRICS)}.",
                field = field,
            )


def resolve_metric_override(metric: object) -> list[str] | None:
    """
    Check a `metric` argument and return it as the list of metrics to
    compute, the first one being the primary metric.

    Parameters
    ----------
    metric : str, list of str, None
        A metric name, or a list of them whose first one ranks (as in
        `compare()`). None asks for the deterministic selection.

    Returns
    -------
    metrics : list of str, None
        The metrics, in the order given; None when `metric` is None.

    Notes
    -----
    A `TypeError` is raised when `metric` is not a str or a list of str,
    and a `ValueError` for an empty list, a repeated metric or a name
    outside `ALLOWED_METRICS`.
    """

    if metric is None:
        return None
    metrics = [metric] if isinstance(metric, str) else metric
    if not isinstance(metrics, (list, tuple)) or not all(
        isinstance(name, str) for name in metrics
    ):
        raise InvalidInputTypeError(
            f"`metric` must be a metric name or a list of metric names, got "
            f"{metric!r}.",
            field = "metric",
        )
    if not metrics:
        raise InvalidInputError(
            "`metric` must not be an empty list.",
            field = "metric",
        )
    repeated = sorted({name for name in metrics if metrics.count(name) > 1})
    if repeated:
        raise InvalidInputError(
            f"`metric` repeats {repeated}: list each metric once.",
            field = "metric",
        )
    validate_metrics(list(metrics))

    return list(metrics)


def validate_calendar_override(features: object) -> list[str] | None:
    """
    Check the `calendar_features` argument of `plan()`.

    Parameters
    ----------
    features : list of str, None
        Calendar features to generate; an empty list for none, None for
        the deterministic selection.

    Returns
    -------
    features : list of str, None
        The features as a list, in the order given.

    Notes
    -----
    A `TypeError` is raised when `features` is not a list of str (a single
    str included), and a `ValueError` for a name outside the features of
    skforecast's `CalendarFeatures` or a repeated one.
    """

    if features is None:
        return None
    if not isinstance(features, (list, tuple)) or not all(
        isinstance(feature, str) for feature in features
    ):
        raise InvalidInputTypeError(
            f"`calendar_features` must be a list of calendar feature names "
            f"(an empty list for none), got {features!r}.",
            field = "calendar_features",
        )
    unknown = [feature for feature in features if feature not in _CALENDAR_FEATURES]
    if unknown:
        raise InvalidInputError(
            f"Unknown calendar features {unknown}. Supported: "
            f"{list(_CALENDAR_FEATURES)}.",
            field = "calendar_features",
        )
    repeated = sorted({f for f in features if list(features).count(f) > 1})
    if repeated:
        raise InvalidInputError(
            f"`calendar_features` repeats {repeated}: list each feature once.",
            field = "calendar_features",
        )

    return list(features)


def validate_steps(steps: object) -> int:
    """
    Check a forecast horizon and return it as an int.

    Parameters
    ----------
    steps : int
        Forecast horizon. An integral float (`12.0`) is accepted.

    Returns
    -------
    steps : int
        The horizon as a Python int.

    Notes
    -----
    A `ValueError` is raised for a bool, a value that is not an integer
    (`12.5`, `'12'`) and a value lower than 1. The horizon is written into
    the generated script.
    """

    is_integral = (
        not isinstance(steps, bool)
        and isinstance(steps, numbers.Real)
        and (isinstance(steps, numbers.Integral) or float(steps).is_integer())
    )
    if not is_integral or steps < 1:
        raise InvalidInputError(
            f"`steps` must be an integer greater than or equal to 1, got "
            f"{steps!r}.",
            field = "steps",
        )

    return int(steps)


def validate_forecaster(forecaster: str, task_type: str) -> None:
    """
    Check the forecaster of a plan against the supported forecasters.

    Parameters
    ----------
    forecaster : str
        Forecaster class name of the plan.
    task_type : str
        Forecasting task category of the plan.

    Returns
    -------
    None

    Notes
    -----
    A `ValueError` is raised for a forecaster that is not supported and for
    a forecaster whose task type is not `task_type`: the script imports the
    forecaster and is rendered by the template of the task type.
    """

    if not isinstance(forecaster, str) or forecaster not in FORECASTER_TASK_TYPES:
        raise InvalidInputError(
            f"{forecaster!r} is not a supported forecaster. Supported "
            f"forecasters: {list(FORECASTER_TASK_TYPES)}.",
            field = "forecaster",
        )
    expected = FORECASTER_TASK_TYPES[forecaster]
    if task_type != expected:
        raise InvalidInputError(
            f"'{forecaster}' plans have task_type '{expected}', got "
            f"task_type={task_type!r}.",
            field = "task_type",
        )


def _is_positive_int(value: object) -> bool:
    """
    Whether `value` is a Python int (not a bool) greater than or equal to 1.
    A numpy integer is not accepted: its `repr()` in the script would need
    numpy, and the plan could not be saved as JSON.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _validate_calendar_features(value: object) -> None:
    """
    Check the `calendar_features` entry of `forecaster_kwargs`.

    Parameters
    ----------
    value : dict
        Calendar features configuration: `'features'` (list of feature
        names) and, optionally, `'encoding'`.

    Returns
    -------
    None
    """

    if not isinstance(value, dict) or not set(value) <= {"features", "encoding"}:
        raise InvalidInputError(
            f"`forecaster_kwargs['calendar_features']` must be None or a dict "
            f"with the keys 'features' and 'encoding', got {value!r}.",
            field = "forecaster_kwargs",
        )
    features = value.get("features")
    if (
        not isinstance(features, list)
        or not features
        or any(feature not in _CALENDAR_FEATURES for feature in features)
    ):
        raise InvalidInputError(
            f"`forecaster_kwargs['calendar_features']['features']` must be a "
            f"non-empty list of calendar features among {list(_CALENDAR_FEATURES)}, "
            f"got {features!r}.",
            field = "forecaster_kwargs",
        )
    if value.get("encoding") not in _CALENDAR_ENCODINGS:
        raise InvalidInputError(
            f"`forecaster_kwargs['calendar_features']['encoding']` must be one "
            f"of {list(_CALENDAR_ENCODINGS)}, got {value.get('encoding')!r}.",
            field = "forecaster_kwargs",
        )


def validate_forecaster_kwargs(forecaster_kwargs: dict, forecaster: str) -> None:
    """
    Check the keys and values of `forecaster_kwargs` against a closed set.

    Every entry is written into the generated script, so a plan loaded from
    JSON may only hold the arguments `plan()` builds for its forecaster,
    with values of the types and in the sets skforecast accepts.

    Parameters
    ----------
    forecaster_kwargs : dict
        Keyword arguments of the forecaster constructor.
    forecaster : str
        Supported forecaster class name of the plan.

    Returns
    -------
    None

    Notes
    -----
    A `ValueError` is raised for a key that does not apply to `forecaster`
    and for a value outside its set: `lags` and `window_features` as in
    `plan()`; `calendar_features` with the features and encodings of
    skforecast's `CalendarFeatures`; `encoding` among skforecast's series
    encodings; transformers among `SUPPORTED_TRANSFORMERS`;
    `categorical_features` `'auto'`; `dropna_from_series` a bool;
    `differentiation`, `steps`, `offset` and `n_offsets` integers greater
    than or equal to 1. None is accepted wherever the script leaves the
    argument out.
    """

    allowed = _FORECASTER_KWARGS_KEYS[forecaster]
    unknown = [key for key in forecaster_kwargs if key not in allowed]
    if unknown:
        raise InvalidInputError(
            f"`forecaster_kwargs` of '{forecaster}' cannot contain "
            f"{unknown}. Allowed keys: {sorted(allowed)}.",
            field = "forecaster_kwargs",
        )

    for key, value in forecaster_kwargs.items():
        if key == "lags":
            _validate_lags(value, field="forecaster_kwargs")
            continue
        if key == "window_features":
            _validate_window_features(value, field="forecaster_kwargs")
            continue
        if key == "calendar_features":
            if value is not None:
                _validate_calendar_features(value)
            continue
        if key in ("transformer_y", "transformer_series", "transformer_exog"):
            valid = value is None or value in SUPPORTED_TRANSFORMERS
            expected = f"None or one of {list(SUPPORTED_TRANSFORMERS)}"
        elif key == "encoding":
            valid = value in _SERIES_ENCODINGS
            expected = f"one of {list(_SERIES_ENCODINGS)}"
        elif key == "categorical_features":
            valid = value is None or value == "auto"
            expected = "'auto' or None"
        elif key == "dropna_from_series":
            valid = value is None or isinstance(value, bool)
            expected = "a bool"
        elif key == "differentiation":
            valid = value is None or _is_positive_int(value)
            expected = "None or an integer greater than or equal to 1"
        else:
            # `steps`, `offset` and `n_offsets`.
            valid = _is_positive_int(value)
            expected = "an integer greater than or equal to 1"
        if not valid:
            raise InvalidInputError(
                f"`forecaster_kwargs['{key}']` must be {expected}, got {value!r}.",
                field = "forecaster_kwargs",
            )


def validate_preprocessing_step(
    action: str,
    code_snippet: str,
    blocking: bool,
) -> None:
    """
    Check that a blocking preprocessing step is one the scripts can contain.

    Blocking steps are written into the generated script, so their
    `(action, code_snippet)` pair must be one of
    `BLOCKING_PREPROCESSING_TEMPLATES`, the steps `plan()` generates (those
    of 0.3.1 included). Non-blocking steps are informational and never
    written, so they are not checked.

    Parameters
    ----------
    action : str
        Identifier of the step.
    code_snippet : str
        Code template of the step.
    blocking : bool
        Whether the step is written into the script.

    Returns
    -------
    None

    Notes
    -----
    A `ValueError` is raised for a blocking step outside the templates.
    """

    if blocking and (action, code_snippet) not in BLOCKING_PREPROCESSING_TEMPLATES:
        raise InvalidInputError(
            f"The blocking preprocessing step {action!r} is not one of the "
            f"steps the scripts can contain: its code snippet differs from "
            f"the one `plan()` generates. Build the plan with `plan()`, or "
            f"remove the step.",
            field = "preprocessing_steps",
        )


def _validate_lags(lags: int | list[int] | None, field: str = "lags") -> None:
    """
    Validate the structure of an explicit `lags` override.

    `lags` must be a positive int (consecutive lags `1..lags`) or a
    non-empty list of unique positive ints. The rules mirror what
    skforecast's `initialize_lags` requires, with two additions that
    skforecast accepts silently: an empty list, which skforecast treats as
    `lags=None` and trains without lag features, and duplicated lags, which
    produce repeated feature columns. A `bool` is rejected explicitly
    because it subclasses `int`. A `ValueError` is raised on the first
    violation.

    Parameters
    ----------
    lags : int, list of int, None
        Explicit lags override. When None, no validation is performed.
    field : str, default 'lags'
        Name of the argument or plan field reported as `field` of the error.

    Returns
    -------
    None
    """
    if lags is None:
        return

    # `bool` is a subclass of `int`; reject it explicitly.
    if isinstance(lags, bool) or not isinstance(lags, (int, list)):
        raise InvalidInputError(
            f"`lags` must be an int or a list of ints, got {lags!r}.",
            field = field,
        )

    if isinstance(lags, int):
        if lags < 1:
            raise InvalidInputError(
                f"`lags` must be positive integers (>= 1), got {lags!r}.",
                field = field,
            )
        return

    if not lags:
        raise InvalidInputError(
            "`lags` must not be an empty list; pass None to keep the "
            "deterministic lag selection.",
            field = field,
        )

    if any(isinstance(lag, bool) or not isinstance(lag, int) for lag in lags):
        raise InvalidInputError(
            f"`lags` must contain ints only, got {lags!r}.",
            field = field,
        )

    if any(lag < 1 for lag in lags):
        raise InvalidInputError(
            f"`lags` must be positive integers (>= 1), got {lags!r}.",
            field = field,
        )

    if len(set(lags)) != len(lags):
        raise InvalidInputError(
            f"`lags` must not contain duplicates, got {lags!r}.",
            field = field,
        )


def _validate_window_features(
    window_features: list[dict] | None,
    field: str = "window_features",
) -> None:
    """
    Validate the structure of an explicit `window_features` override.

    Each entry must be a dict with a `'stats'` key (a non-empty list whose
    members are all in `ALLOWED_WINDOW_STATS`) and a `'window_size'` key
    holding a scalar positive int. A scalar is required because the code
    generator pairs every statistic in an entry with that entry's single
    window size; a list would be emitted as a nested list and rejected by
    `RollingFeatures`. To combine several window sizes, add one entry per
    size. The same statistic must not be paired with the same window size
    in two entries: the code generator flattens the entries into a single
    `RollingFeatures`, which rejects duplicate pairs. A `ValueError` is
    raised on the first violation.

    Parameters
    ----------
    window_features : list of dict, None
        Explicit window features override. When None, no validation is
        performed.
    field : str, default 'window_features'
        Name of the argument or plan field reported as `field` of the error.

    Returns
    -------
    None
    """
    if window_features is None:
        return

    if not isinstance(window_features, list):
        raise InvalidInputError(
            f"`window_features` must be a list of dicts, got "
            f"{type(window_features).__name__}.",
            field = field,
        )

    for i, wf in enumerate(window_features):
        if not isinstance(wf, dict):
            raise InvalidInputError(
                f"`window_features[{i}]` must be a dict with keys 'stats' "
                f"and 'window_size', got {type(wf).__name__}.",
                field = field,
            )

        missing = {"stats", "window_size"} - wf.keys()
        if missing:
            raise InvalidInputError(
                f"`window_features[{i}]` is missing required key(s): "
                f"{sorted(missing)}. Each entry must have 'stats' and "
                f"'window_size'.",
                field = field,
            )

        stats = wf["stats"]
        if not isinstance(stats, list) or not stats:
            raise InvalidInputError(
                f"`window_features[{i}]['stats']` must be a non-empty list "
                f"of statistic names, got {stats!r}.",
                field = field,
            )
        invalid_stats = [s for s in stats if s not in ALLOWED_WINDOW_STATS]
        if invalid_stats:
            raise InvalidInputError(
                f"`window_features[{i}]['stats']` contains unsupported "
                f"statistic(s): {invalid_stats}. Allowed statistics are: "
                f"{sorted(ALLOWED_WINDOW_STATS)}.",
                field = field,
            )

        window_size = wf["window_size"]
        # `bool` is a subclass of `int`; reject it explicitly.
        if not isinstance(window_size, int) or isinstance(window_size, bool):
            raise InvalidInputError(
                f"`window_features[{i}]['window_size']` must be a scalar "
                f"int, got {window_size!r}. Within a single entry 'stats' "
                f"may be a list but 'window_size' must be a scalar applied "
                f"to all of them; add one entry per window size to use "
                f"several sizes.",
                field = field,
            )
        if window_size < 1:
            raise InvalidInputError(
                f"`window_features[{i}]['window_size']` must be a positive "
                f"int, got {window_size}.",
                field = field,
            )

    pairs = [
        (stat, wf["window_size"]) for wf in window_features for stat in wf["stats"]
    ]
    duplicates = sorted({pair for pair in pairs if pairs.count(pair) > 1})
    if duplicates:
        raise InvalidInputError(
            f"`window_features` contains duplicate (stat, window_size) "
            f"pairs: {duplicates}. Merge the entries or change the window "
            f"size.",
            field = field,
        )
