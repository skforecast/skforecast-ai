################################################################################
#                                  Utils                                       #
#                                                                              #
# Shared internal utilities for skforecast_ai                                  #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import numbers
import re
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import numpy as np
import pandas as pd
from pydantic import BaseModel
from skforecast.exceptions import IgnoredArgumentWarning, LongTrainingWarning
from skforecast.model_selection import TimeSeriesFold

from ._constants import (
    AUTOREG_FORECASTERS,
    DIRECT_FORECASTERS,
    LONG_TRAINING_FITS,
    MAX_FEATURE_FRACTION,
    PLACEHOLDER_DATA_PATH,
)
from ._foundation import resolve_foundation_model, validate_foundation_interval
# `_validate_lags` and `_validate_window_features` live in `_validation`,
# which the plan schema imports; they are re-exported here for the callers
# that import them from `_utils`.
from ._validation import (
    _validate_lags as _validate_lags,
    _validate_window_features as _validate_window_features,
    resolve_metric_override,
    validate_calendar_override,
    validate_interval,
)
from ._dates import is_text, parse_text_dates, training_end
from .profiling.data_profile import (
    _read_date_column,
    _try_parse_first_date_column,
    date_issue_hint,
    read_csv_file,
)
from .schemas import CVResult, DataProfile, ForecastingProfile, ForecastPlan
from .exceptions import DataNotFoundError, InvalidInputError, InvalidInputTypeError

_CODE_BLOCK_RE = re.compile(r"^```[^\n]*\n[\s\S]*?^```", re.MULTILINE)
_CODE_BLOCK_REPLACEMENT = "(See `result.code` for the validated implementation.)"


def _max_window_size(
    lags: int | list[int] | None,
    window_features: list[dict] | None,
) -> int:
    """
    Largest lag or rolling-window size implied by explicit feature overrides.

    Parameters
    ----------
    lags : int, list of int, None
        Explicit lag override. An int is interpreted as consecutive lags
        `1..lags`, so its span equals the int itself.
    window_features : list of dict, None
        Explicit window features override. Each dict carries `window_size`
        as a scalar int (a list is tolerated defensively).

    Returns
    -------
    span : int
        Maximum span across all supplied features, or 0 when none apply.
    """
    spans: list[int] = []
    if isinstance(lags, int):
        spans.append(lags)
    elif lags:
        spans.append(max(lags))
    for wf in window_features or []:
        if not isinstance(wf, dict):
            continue
        sizes = wf.get("window_size")
        if isinstance(sizes, int):
            spans.append(sizes)
        elif isinstance(sizes, (list, tuple)) and sizes:
            spans.append(max(sizes))
    return max(spans, default=0)


def _validate_max_window_size(
    lags: int | list[int] | None,
    window_features: list[dict] | None,
    span_index_length: int,
    differentiation: int | None = None,
) -> None:
    """
    Ensure explicit lags/window features fit within the available data.

    The largest lag or rolling-window size (the forecaster's effective
    `window_size`) consumes initial observations before the first training
    row can be built. When it exceeds `MAX_FEATURE_FRACTION` of the series
    length, too few rows remain to train reliably, so a `ValueError` is
    raised. Deterministic lag/window selection already respects this limit;
    this guard covers explicit (manual or LLM-supplied) overrides that
    bypass it.

    Parameters
    ----------
    lags : int, list of int, None
        Explicit lag override. An int is interpreted as consecutive lags
        `1..lags`, so its span equals the int itself.
    window_features : list of dict, None
        Explicit window features override. Each dict carries `window_size`
        as a scalar int (a list is tolerated defensively).
    span_index_length : int
        Number of observations spanned by the series index.
    differentiation : int, default None
        Differentiation order of the forecaster, which adds as many
        observations to its `window_size`.

    Returns
    -------
    None
    """
    max_span = _max_window_size(lags, window_features)
    max_allowed = int(span_index_length * MAX_FEATURE_FRACTION)
    if max_span + (differentiation or 0) > max_allowed:
        with_differentiation = (
            f" plus {differentiation} for the differentiation"
            if differentiation else ""
        )
        raise InvalidInputError(
            f"Explicit lags/window_features span up to {max_span} "
            f"observations{with_differentiation}, exceeding the maximum of "
            f"{max_allowed} ({int(MAX_FEATURE_FRACTION * 100)}% of "
            f"{span_index_length} observations). "
            f"Reduce the largest lag or window size"
            + (
                ", or pass `lags=None` (and smaller window sizes) so they "
                "leave room for the differentiation."
                if differentiation else "."
            ),
            code  = "insufficient_data",
            field = (
                "lags" if _max_window_size(lags, None) == max_span
                else "window_features"
            ),
        )


def _validate_task_input(data_profile: DataProfile, task_type: str) -> None:
    """
    Validate that the input shape is compatible with the task type.

    Single-series tasks (`single_series`, `statistical`, `baseline`) accept
    exactly one series, and the multi-series tasks (`multi_series`,
    `multivariate`) need data with several series (wide or long format):
    on a single series their script always failed. The `multivariate` task
    requires all series to share the same length, and wide-format data: on
    long-format data with several series the generated script always failed
    (its level is the target column, which is not one of the series), and
    on long-format data with one series too. `foundation` takes one or
    several series. Long-format data with several series needs its dates in
    a column, which the generated script reads to split the series; dated by
    the index, or without dates, the script always failed.

    Parameters
    ----------
    data_profile : DataProfile
        Universal data profile from Stage 1.
    task_type : str
        Forecasting task type implied by the selected forecaster.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        When the input shape is incompatible with the task type.
    """
    series_lengths = data_profile.series_lengths
    n_series = len(series_lengths)

    if (
        task_type in ("single_series", "statistical", "baseline")
        and n_series > 1
    ):
        raise InvalidInputError(
            f"Task type '{task_type}' supports a single series only, but the "
            f"input contains {n_series} series ({list(series_lengths)}). "
            f"Use a multi-series forecaster (e.g. "
            f"'ForecasterRecursiveMultiSeries') or provide a single series.",
            field = "forecaster",
        )

    if (
        task_type in ("multi_series", "multivariate")
        and data_profile.data_format == "single"
        and n_series == 1
    ):
        forecaster = (
            "ForecasterRecursiveMultiSeries" if task_type == "multi_series"
            else "ForecasterDirectMultiVariate"
        )
        raise InvalidInputError(
            f"{forecaster} forecasts several series, but the data has a single "
            f"series (target {data_profile.target!r}). Use a single-series "
            f"forecaster (e.g. 'ForecasterRecursive'), or pass several series: "
            f"a list of target columns, or `series_id_column` for long format.",
            field = "forecaster",
        )

    long_series = data_profile.data_format == "long" and n_series > 1
    if long_series and task_type == "multivariate":
        raise InvalidInputError(
            "ForecasterDirectMultiVariate cannot forecast long-format data with "
            "several series. Use 'ForecasterRecursiveMultiSeries', or pass the "
            "series as columns (wide format) with `target` naming them.",
            field = "forecaster",
        )
    if data_profile.data_format == "long" and task_type == "multivariate":
        # Its level is the target column, which is not one of the series.
        raise InvalidInputError(
            "ForecasterDirectMultiVariate cannot forecast long-format data with "
            "a single series. Use a single-series forecaster (e.g. "
            "'ForecasterRecursive').",
            field = "forecaster",
        )
    if (
        long_series
        and data_profile.date_column is None
        and task_type in ("multi_series", "foundation")
    ):
        raise InvalidInputError(
            "Long-format data with several series needs its dates in a column, "
            "named by `date_column`, which the generated script reads to split "
            "the series. With the dates in the index, move them to a column "
            "with `data.reset_index()`.",
            field = "date_column",
        )

    if task_type == "multivariate":
        lengths = {info.length for info in series_lengths.values()}
        if len(lengths) > 1:
            detail = {
                name: info.length for name, info in series_lengths.items()
            }
            raise InvalidInputError(
                f"Task type 'multivariate' (ForecasterDirectMultiVariate) "
                f"requires all series to have the same length, but got "
                f"{detail}. Align the series to a common index or use "
                f"'ForecasterRecursiveMultiSeries'.",
                field = "forecaster",
            )


def _strip_code_blocks(text: str) -> str:
    """Replace fenced code blocks with a pointer to result.code."""
    return _CODE_BLOCK_RE.sub(_CODE_BLOCK_REPLACEMENT, text)


def _normalize_lags(lags: int | list[int] | None) -> list[int] | None:
    """Express a lag specification as the sorted list of lags it denotes."""
    if lags is None:
        return None
    if isinstance(lags, int):
        return list(range(1, lags + 1))
    return sorted(int(lag) for lag in lags)


def _check_plan_overrides(
    plan: ForecastPlan | None,
    forecaster: str | None,
    estimator: str | None,
    estimator_kwargs: dict | None,
    lags: int | list[int] | None = None,
    window_features: list[dict] | None = None,
    **overrides: object,
) -> None:
    """
    Reject plan-shaping arguments that contradict a supplied plan.

    A pre-built `plan` already fixes the forecaster, the estimator and
    its keyword arguments, the lags and the window features, and the
    planning stage that would consume these arguments is skipped. An
    argument equal to what the plan holds is redundant and accepted; a
    different value would be silently dropped, so it is rejected and the
    caller is pointed to `refine_plan()`. Mirrors the `steps` check of
    the forecasting workflows.

    Parameters
    ----------
    plan : ForecastPlan, None
        Pre-built plan supplied by the caller. When None, nothing is
        checked because the planning stage runs normally.
    forecaster : str, None
        Forecaster override.
    estimator : str, None
        Estimator override.
    estimator_kwargs : dict, None
        Estimator keyword arguments override.
    lags : int, list of int, default None
        Lag override. An integer denotes lags 1 to `lags`.
    window_features : list of dict, default None
        Window features override.
    **overrides : object
        Overrides added in 0.4.0 (`metric`, `use_exog`...), compared with
        the value the plan holds in the form `plan()` takes them
        (`plan_override_value`).

    Returns
    -------
    None
    """
    if plan is None:
        return
    kwargs = plan.forecaster_kwargs
    conflicts = [
        name
        for name, value, plan_value in (
            ("forecaster", forecaster, plan.forecaster),
            ("estimator", estimator, plan.estimator),
            ("estimator_kwargs", estimator_kwargs, plan.estimator_kwargs),
            ("lags", _normalize_lags(lags), _normalize_lags(kwargs.get("lags"))),
            ("window_features", window_features, kwargs.get("window_features")),
            *(
                (
                    name,
                    _normalize_override(name, value),
                    plan_override_value(plan, name),
                )
                for name, value in overrides.items()
            ),
        )
        if value is not None and value != plan_value
    ]
    if conflicts:
        raise InvalidInputError(
            f"A pre-built `plan` was provided and the following argument(s) "
            f"differ from what it holds: {conflicts}. Omit them to use the "
            f"plan as is, or refine the plan with `refine_plan()` first.",
            field = conflicts[0],
        )


def _normalize_override(name: str, value: object) -> object:
    """
    An override, checked, in the form `plan_override_value` reads it from
    a plan: a single metric as a list.
    """

    if name == "metric":
        return resolve_metric_override(value)
    if name == "calendar_features":
        return validate_calendar_override(value)

    return value


def plan_override_value(plan: ForecastPlan, name: str) -> object:
    """
    Value a plan holds for one of the decisions in `OVERRIDE_NAMES`, in
    the form the argument of `plan()` takes it.

    Parameters
    ----------
    plan : ForecastPlan
        Plan to read.
    name : str
        Name of the decision, one of `OVERRIDE_NAMES`.

    Returns
    -------
    value : object
        The value; None when the plan does not hold one.
    """

    kwargs = plan.forecaster_kwargs
    if name == "forecaster":
        return plan.forecaster
    if name == "estimator":
        return plan.estimator
    if name == "estimator_kwargs":
        return plan.estimator_kwargs or None
    if name == "use_exog":
        return plan.use_exog
    autoregressive = plan.forecaster in AUTOREG_FORECASTERS
    if name == "calendar_features":
        calendar = kwargs.get("calendar_features")
        if calendar:
            return list(calendar["features"])
        return [] if autoregressive else None
    if name == "target_transformer":
        transformer = kwargs.get("transformer_y") or kwargs.get("transformer_series")
        if transformer:
            return transformer
        return "none" if autoregressive else None
    if name == "metric":
        # The primary metric first, then the others computed.
        return [
            plan.metric,
            *(other for other in plan.metrics_to_compute if other != plan.metric),
        ]

    return kwargs.get(name)


# The argument of `refine_plan()` that sets each field of a plan, and each
# key of its `forecaster_kwargs`. A field without one cannot be passed, so
# an edit of it is always lost when the plan is rebuilt.
_FIELD_OVERRIDES: dict[str, str] = {
    "forecaster": "forecaster",
    "estimator": "estimator",
    "estimator_kwargs": "estimator_kwargs",
    "steps": "steps",
    "interval": "interval",
    "interval_method": "interval",
    "metric": "metric",
    "metrics_to_compute": "metric",
    "use_exog": "use_exog",
}
_FORECASTER_KWARG_OVERRIDES: dict[str, str] = {
    "lags": "lags",
    "window_features": "window_features",
    "steps": "steps",
    "differentiation": "differentiation",
    "calendar_features": "calendar_features",
    "transformer_y": "target_transformer",
    "transformer_series": "target_transformer",
    "dropna_from_series": "dropna_from_series",
}
# Fields compared by `discarded_plan_edits`: everything a plan decides, not
# the split boundary, the explanation, the warnings or the marks.
_COMPARED_PLAN_FIELDS = (
    "task_type",
    "forecaster",
    "estimator",
    "estimator_kwargs",
    "steps",
    "frequency",
    "interval",
    "interval_method",
    "metric",
    "metrics_to_compute",
    "use_exog",
    "preprocessing_steps",
)


def discarded_plan_edits(
    plan: ForecastPlan,
    rebuilt: ForecastPlan,
    explicit_keys: set[str],
) -> list[str]:
    """
    Fields of a plan that differ from the plan `plan()` builds from the
    decisions `refine_plan()` carries over, so `refine_plan()` loses them.

    `end_train`, `explanation`, `warnings`, `llm_refined_fields` and
    `overridden_fields` are not compared, nor the fields that an explicit
    override of the call replaces anyway.

    Parameters
    ----------
    plan : ForecastPlan
        Plan received by `refine_plan()`.
    rebuilt : ForecastPlan
        Plan that `plan()` builds from what `refine_plan()` carries over
        from `plan`, without the overrides of the call.
    explicit_keys : set of str
        Keys overridden in the call.

    Returns
    -------
    fields : list of str
        Names of the fields that differ, `forecaster_kwargs['key']` for a
        key of the `forecaster_kwargs` of `plan` that the rebuilt plan
        drops or changes, in a fixed order.
    """

    fields: list[str] = []
    for field in _COMPARED_PLAN_FIELDS:
        if _FIELD_OVERRIDES.get(field) in explicit_keys:
            continue
        value, rebuilt_value = getattr(plan, field), getattr(rebuilt, field)
        if field == "preprocessing_steps":
            value = [step.model_dump() for step in value]
            rebuilt_value = [step.model_dump() for step in rebuilt_value]
        if value != rebuilt_value:
            fields.append(field)

    # Only the keys the received plan holds: a key that only the rebuilt
    # plan has (one that `plan()` of an earlier version did not write) adds
    # a value, it does not discard one.
    kwargs, rebuilt_kwargs = plan.forecaster_kwargs, rebuilt.forecaster_kwargs
    for key in kwargs:
        if _FORECASTER_KWARG_OVERRIDES.get(key) in explicit_keys:
            continue
        if kwargs.get(key) != rebuilt_kwargs.get(key):
            fields.append(f"forecaster_kwargs['{key}']")

    return fields


def resolve_interval_method(task_type: str, interval: list[float] | None) -> str | None:
    """
    Select the prediction interval method for a task type.

    Parameters
    ----------
    task_type : str
        Task type of the plan (`'single_series'`, `'statistical'`, ...).
    interval : list of float, None
        Prediction interval quantiles. None means no intervals.

    Returns
    -------
    interval_method : str, None
        `'native'` for statistical and foundation forecasters, which
        produce their own intervals, `'conformal'` for the baseline
        (`ForecasterEquivalentDate` supports no other method),
        `'bootstrapping'` otherwise, and None when `interval` is None.
    """
    if interval is None:
        return None
    if task_type in {"statistical", "foundation"}:
        return "native"
    if task_type == "baseline":
        return "conformal"
    return "bootstrapping"


def _same_values(first: object, second: object) -> bool:
    """
    Compare two field values, types included.

    Unlike `==`, `12` and `12.0`, or a model and the dict of its fields, are
    different: `_revalidate_plan` uses it to tell whether validation
    converted a value of the plan it received.

    Parameters
    ----------
    first : object
        Value of the received plan.
    second : object
        Value of the validated plan.

    Returns
    -------
    same : bool
        Whether both values have the same type and compare equal, recursively
        for models, dicts, lists and tuples. Values that cannot be compared
        (numpy arrays) count as different.
    """
    if type(first) is not type(second):
        return False
    if isinstance(first, BaseModel):
        return _same_values(dict(first), dict(second))
    if isinstance(first, dict):
        return first.keys() == second.keys() and all(
            _same_values(first[key], second[key]) for key in first
        )
    if isinstance(first, (list, tuple)):
        return len(first) == len(second) and all(map(_same_values, first, second))
    try:
        return bool(first == second)
    except (TypeError, ValueError):
        return False


def _revalidate_plan(plan: ForecastPlan | None) -> ForecastPlan | None:
    """
    Run the validators of a received plan again before it is rendered.

    A plan edited with `model_copy(update=...)`, by assignment or built with
    `model_construct` skips the validators of `ForecastPlan`, and every one
    of its fields can reach the generated script. Validating a dump of it
    checks the plan as if it had been loaded from JSON.

    Parameters
    ----------
    plan : ForecastPlan, None
        Plan supplied by the caller. None when the plan is built here.

    Returns
    -------
    plan : ForecastPlan, None
        The plan the caller passed when it validates unchanged, so a result
        still refers to that object (`result.plan is plan`). The validated
        copy when validation converted a value (for example `steps=12.0`, or
        `interval=['0.1', '0.9']` set with `model_copy`), so the script uses
        the values that were checked. None when `plan` is None.

    Raises
    ------
    pydantic.ValidationError
        When a field of `plan` does not pass the validators (a subclass of
        `ValueError`).
    """
    if plan is None:
        return None
    # `warnings=False`: a field holding a value of the wrong type is reported
    # by the validators, not by the serializer.
    validated = ForecastPlan.model_validate(plan.model_dump(warnings=False))

    return plan if _same_values(dict(plan), dict(validated)) else validated


def _apply_interval_to_plan(plan: ForecastPlan, interval: list[float]) -> ForecastPlan:
    """
    Return a copy of `plan` that predicts the given interval.

    The interval is a prediction-time option, like `predict_interval()`
    in skforecast, not a modeling decision: changing it touches neither
    the forecaster nor its features, so a pre-built plan is updated in
    place of asking the caller to refine it. The interval method follows
    the same rule `plan()` applies.

    Parameters
    ----------
    plan : ForecastPlan
        Pre-built plan.
    interval : list of float
        Prediction interval quantiles as `[lower, upper]`.

    Returns
    -------
    plan : ForecastPlan
        The same plan when it already predicts `interval`, otherwise a
        copy with `interval`, `interval_method` and the explanation
        updated.

    Raises
    ------
    ValueError
        When the foundation model of the plan cannot predict `interval`.
    """
    if plan.interval == interval:
        return plan
    # `model_copy` skips the plan validators, so the interval is checked
    # here, against the foundation model when there is one.
    if plan.task_type == "foundation":
        validate_foundation_interval(
            info     = resolve_foundation_model(plan.estimator),
            interval = interval,
        )
    else:
        validate_interval(
            interval   = interval,
            task_type  = plan.task_type,
            forecaster = plan.forecaster,
        )
    interval_method = resolve_interval_method(plan.task_type, interval)
    explanation = plan.explanation
    if "Prediction intervals via" not in explanation:
        explanation = f"{explanation} Prediction intervals via {interval_method}."
    # A deep copy, so the lists of the new plan (its warnings, its
    # forecaster arguments) are not shared with the plan passed.
    return plan.model_copy(
        update={
            "interval": interval,
            "interval_method": interval_method,
            "explanation": explanation,
        },
        deep=True,
    )


def _validate_forecast_mode(
    evaluate: bool,
    exog: pd.DataFrame | None,
    has_exog: bool,
    steps: int,
    require_exog: bool = True,
    uses_exog: bool | None = None,
) -> None:
    """
    Validate the `exog` argument against the effective forecast mode.

    Enforces the boundaries between evaluation mode and prediction mode,
    so misaligned inputs fail fast with an actionable message instead of
    surfacing deep inside skforecast. The mode is determined by the
    caller (evaluation when `test_size` is set or the supplied plan
    already carries an `end_train` boundary; prediction otherwise).

    Parameters
    ----------
    evaluate : bool
        Whether the workflow runs in evaluation mode (train/test split).
        When False, the workflow forecasts the future (prediction mode).
    exog : pandas DataFrame, None
        Future exogenous variables supplied for prediction mode.
    has_exog : bool
        Whether the profiled data contains exogenous variables.
    steps : int
        Forecast horizon.
    require_exog : bool, default True
        Whether prediction mode must be supplied with future `exog` when
        the data contains exogenous variables. `forecast()` executes the
        pipeline and needs the values, so it requires them. `forecast_code()`
        only renders a script (which loads the future values from a CSV at
        run time), so it sets this to False and validates the remaining
        rules without demanding `exog`.
    uses_exog : bool, default None
        Whether the plan uses the exogenous variables (`plan.use_exog`).
        None means it uses them whenever the data has them. A plan that
        does not use them, such as the baseline
        (`ForecasterEquivalentDate`), needs no future `exog` and rejects
        one.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        If `exog` is supplied in evaluation mode; if prediction mode is
        used but required/forbidden `exog` rules are violated; or if the
        supplied `exog` does not cover the forecast horizon.
    """
    if evaluate:
        if exog is not None:
            raise InvalidInputError(
                "`exog` is only used for future prediction (`test_size=None`). "
                "In evaluation mode the test-set exogenous values are taken "
                "from the train/test split, so `exog` must not be provided.",
                field = "exog",
            )
        return

    if uses_exog is None:
        uses_exog = has_exog

    # Prediction mode.
    if require_exog and uses_exog and exog is None:
        raise InvalidInputError(
            "`exog` is required for future prediction because the data "
            "contains exogenous variables. Provide future exogenous "
            "values covering the forecast horizon, or pass `test_size` "
            "to run in evaluation mode instead.",
            field = "exog",
        )
    if not has_exog and exog is not None:
        raise InvalidInputError(
            "`exog` was provided but the data contains no exogenous "
            "variables. Remove `exog` or add exogenous columns to the "
            "data.",
            field = "exog",
        )
    if has_exog and not uses_exog and exog is not None:
        raise InvalidInputError(
            "`exog` was provided but the plan does not use exogenous "
            "variables (`plan.use_exog` is False). Remove `exog`.",
            field = "exog",
        )
    if exog is not None and len(exog) < steps:
        raise InvalidInputError(
            f"`exog` must cover the forecast horizon: {steps} rows are "
            f"required but only {len(exog)} were provided.",
            field = "exog",
        )


def _resolve_data_and_target(
    data: pd.Series | pd.DataFrame | str | Path,
    target: str | list[str] | None,
    date_column: str | None = None,
) -> tuple[pd.DataFrame, str | list[str]]:
    """
    Coerce the input to a DataFrame and resolve the target column name.

    Centralizes the rules for accepting a `pandas Series` as input. When
    `data` is a Series, the target is derived from the Series name; for
    every other input type a `target` must be provided explicitly. CSV
    paths and URLs are loaded with `pandas.read_csv` (without `parse_dates`,
    deprecated in pandas 2.2+); date columns are detected and parsed by
    `_try_parse_first_date_column` instead, leaving every column intact so
    callers can reference a `date_column` by name.

    Parameters
    ----------
    data : pandas Series, pandas DataFrame, str, Path
        Input dataset, a single series, or a path/URL to a CSV file.
    target : str, list, None
        Name of the column(s) to forecast. Optional only when `data` is a
        Series (the name is used instead).
    date_column : str, default None
        Name of the date column, when the caller gives it. A CSV column of
        dates with empty cells, mixed time zones or more than one format
        raises an error when it is this column, or when it is not given and
        no later column holds complete dates (see
        `_try_parse_first_date_column`).

    Returns
    -------
    data : pandas DataFrame
        Coerced DataFrame.
    target : str, list
        Resolved target column name(s).

    Raises
    ------
    TypeError
        When `data` is none of the accepted types.
    ValueError
        When `data` is a Series and `target` is provided but does not
        match the Series name, when `data` is not a Series and `target` is
        None, when the dates of a CSV have empty cells, mixed time zones or
        more than one format (see `date_column`), or when a CSV file cannot
        be read as one.
    FileNotFoundError
        When `data` is a path or URL that cannot be read.
    """
    if not isinstance(data, (pd.Series, pd.DataFrame, str, Path)):
        raise InvalidInputTypeError(
            f"`data` must be a pandas DataFrame, a pandas Series, or the path "
            f"or URL of a CSV file, got {type(data).__name__}.",
            field = "data",
        )
    if isinstance(data, pd.Series):
        name = data.name
        if target is not None and target != name:
            raise InvalidInputError(
                f"When `data` is a pandas Series and `target` is provided, "
                f"`target` must match the Series name. Got target={target!r} "
                f"and series.name={name!r}. Omit `target` to use the Series "
                f"name, or rename the Series.",
                field = "target",
            )
        if name is None:
            warnings.warn(
                "The input Series has no name; using 'y' as the target name.",
                UserWarning,
                stacklevel=2,
            )
            resolved_target = "y"
        else:
            resolved_target = name
        return data.to_frame(name=resolved_target), resolved_target

    if target is None:
        raise InvalidInputError(
            "`target` is required when `data` is not a pandas Series.",
            field = "target",
        )

    if isinstance(data, (str, Path)):
        data_str = str(data)
        if data_str.startswith(("http://", "https://")):
            try:
                df = pd.read_csv(data_str)
            except Exception as e:
                # An unreachable URL is an OSError (urllib's HTTPError and
                # URLError); anything else was downloaded but is not a CSV.
                raise DataNotFoundError(
                    f"Could not read CSV from URL: '{data_str}'. {e}",
                    code  = None if isinstance(e, OSError) else "data_unreadable",
                    field = "data",
                ) from e
            return _try_parse_first_date_column(df, date_column), target
        path = Path(data_str)
        if not path.is_file():
            raise DataNotFoundError(
                f"CSV file not found: '{path}'. Please provide a valid file path.",
                field = "data",
            )
        df = read_csv_file(path)
        return _try_parse_first_date_column(df, date_column), target

    return data, target


def _match_profile_column(
    name: str,
    value: str | None,
    recorded: str | None,
) -> str | None:
    """
    Reconcile a column argument with the value recorded in a profile.

    Parameters
    ----------
    name : str
        Argument name, used in the error message.
    value : str, None
        Value passed by the caller. None means "not given".
    recorded : str, None
        Value recorded in the profile.

    Returns
    -------
    resolved : str, None
        `recorded` when `value` is None, otherwise `value`.
    """

    if value is None:
        return recorded
    if value != recorded:
        raise InvalidInputError(
            f"`{name}` {value!r} does not match the value recorded in "
            f"`profile` ({recorded!r}). Pass the value the profile was built "
            f"with, or omit it.",
            field = name,
        )
    return value


def load_exog(
    path: str | Path | None,
    date_column: str | None = None,
    series_id_column: str | None = None,
) -> pd.DataFrame | None:
    """
    Load the future exogenous variables from a CSV file.

    The dates are read as the CSV loader of the data reads them, so empty
    date cells or UTC offsets that change raise an error that says so. They
    are the `date_column` when given. Otherwise they are the first column
    when it holds dates, as `index_col=0, parse_dates=True` read it before
    (integer dates such as 20080701 too), or else the first text column that
    holds dates, as for the data (see `_try_parse_first_date_column`: a
    column with empty date cells is skipped for a later complete one, with a
    warning); a first column of row numbers or of increasing integers (row
    ids, a horizon counter) then becomes no column, as `index_col=0` made it the
    index before, except for long-format data (`series_id_column`), whose
    first column may hold the series ids. Dates in mixed formats, which the
    generated script cannot read, raise. A header one field short
    (`to_csv(index_label=False)`, R's `write.csv`) is read as before, unless
    its last column is then empty, which comes from a separator at the end
    of every row and raises; rows made only of separators (a spreadsheet
    saved as CSV) are dropped,
    as they hold no date and no value. The dates become the index, sorted.

    Parameters
    ----------
    path : str, Path, None
        Path to the CSV file. If None, returns None.
    date_column : str, default None
        Name of the column holding the dates.
    series_id_column : str, default None
        Name of the series id column of long-format data.

    Returns
    -------
    exog : pandas DataFrame, None
        Future exogenous variables indexed by their dates, or None when
        `path` is None.
    """
    if path is None:
        return None
    path = Path(path)
    if not path.is_file():
        raise DataNotFoundError(
            f"Exog CSV not found: '{path}'.",
            field = "exog",
        )

    exog = read_csv_file(path, field="exog")
    # Rows one field longer than the header shift every column; when the
    # last column is then empty, the extra field is a separator at the end
    # of each row, not the index of `to_csv(index_label=False)`.
    shifted = not isinstance(exog.index, pd.RangeIndex) and (
        len(exog.columns) and exog.iloc[:, -1].isna().all()
    )
    if isinstance(exog.index, pd.MultiIndex) or shifted:
        raise InvalidInputError(
            f"The rows of the exog CSV '{path}' have more fields than its header "
            f"(often separators at the end of the rows).",
            field = "exog",
        )
    if not isinstance(exog.index, pd.RangeIndex):
        # A header one field short: pandas reads the first field as the
        # index, as `index_col=0` read it before; with `date_column`, the
        # dates are in a named column and that index was dropped.
        if date_column is None:
            exog = exog.rename_axis("Unnamed: 0").reset_index()
        else:
            exog = exog.reset_index(drop=True)
    # Rows made only of separators (a spreadsheet saved as CSV) hold no date
    # and no value; the generated code dropped them with asfreq.
    filled = exog.notna().any(axis=1).to_numpy()
    exog = exog[filled].reset_index(drop=True)
    text = {column: exog[column].copy() for column in exog.columns}
    if date_column is not None:
        if date_column not in exog.columns:
            raise InvalidInputError(
                f"The exog CSV '{path}' has no column {date_column!r}; its "
                f"columns are {list(exog.columns)}.",
                field = "exog",
            )
        values = exog[date_column]
        parsed, issue = None, None
        if is_text(values):
            parsed, issue = _read_date_column(date_column, values, named=True)
        if issue is not None:
            raise InvalidInputError(
                f"Exog CSV '{path}': {''.join(issue)}",
                field = "exog",
                hint  = date_issue_hint(issue),
            )
        if parsed is None or parsed.isna().any():
            raise InvalidInputError(
                f"Column {date_column!r} of the exog CSV '{path}' does not hold "
                f"dates.",
                field = "exog",
            )
        exog[date_column] = parsed
        found = date_column
    else:
        first = exog.columns[0]
        found = None
        if not is_text(text[first]) and series_id_column is None:
            # The first column, read as `index_col=0, parse_dates=True` read
            # it before (integer dates such as 20080701).
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                index = pd.read_csv(path, index_col=0, parse_dates=True).index
            if isinstance(index, pd.DatetimeIndex) and len(index) == len(filled):
                exog[first] = index[filled]
                found = first
        if found is None:
            try:
                exog = _try_parse_first_date_column(exog)
            except InvalidInputError as exc:
                raise InvalidInputError(
                    f"Exog CSV '{path}': {exc}",
                    field = "exog",
                    hint  = exc.hint,
                ) from exc
            found = next(
                (
                    column for column in exog.columns
                    if is_text(text[column])
                    and pd.api.types.is_datetime64_any_dtype(exog[column])
                ),
                None,
            )
            if (
                found is not None and found != first and series_id_column is None
                and _is_row_label(first, text[first])
            ):
                # Row numbers or a horizon counter, which `index_col=0` took
                # as the index before.
                exog = exog.drop(columns=first)
    if found is not None and is_text(text[found]):
        # The generated script reads the dates with `pd.to_datetime`, which
        # fails on mixed formats that the loader of the data reads.
        try:
            with warnings.catch_warnings():
                # The dates were read already: pandas only repeats that it
                # parses each one on its own.
                warnings.simplefilter("ignore", UserWarning)
                parse_text_dates(text[found])
        except (ValueError, TypeError) as exc:
            raise InvalidInputError(
                f"Exog CSV '{path}': the dates of column {found!r} cannot be "
                f"read as the generated code reads them: {exc}",
                field = "exog",
            ) from exc
    if found is None:
        # Nothing reads as dates: the first column, as `index_col=0` read it;
        # the checks of the future exogenous variables report it.
        found = exog.columns[0]
    exog = exog.set_index(found)
    if str(found).startswith("Unnamed: "):
        exog.index.name = None

    return exog.sort_index()


def _is_row_label(name: object, values: pd.Series) -> bool:
    """
    Return whether a first column labels the rows: the row numbers that
    `to_csv()` writes ('Unnamed: 0') or increasing integers (row ids, a
    horizon counter).
    """
    if str(name).startswith("Unnamed: "):
        return True
    if not pd.api.types.is_integer_dtype(values) or values.isna().any():
        return False

    return bool((np.diff(values.to_numpy()) > 0).all())


def _resolve_inputs_with_profile(
    data: pd.Series | pd.DataFrame | str | Path,
    target: str | list[str] | None,
    date_column: str | None,
    series_id_column: str | None,
    profile: ForecastingProfile | None,
) -> tuple[pd.DataFrame, str | list[str], str | None, str | None]:
    """
    Resolve the data inputs of a workflow, filling them from a profile.

    Without a profile this is `_resolve_data_and_target`. With a profile,
    the profile is what the script is rendered from, so `target`,
    `date_column` and `series_id_column` become optional: a None is taken
    from the profile, and a value that is given must match the profile.
    The columns the profile was built from must be present in `data`, so
    a mismatched dataset fails here with a readable message instead of
    inside the executed script.

    Parameters
    ----------
    data : pandas Series, pandas DataFrame, str, Path
        Input dataset, a single series, or a path/URL to a CSV file.
    target : str, list, None
        Name of the column(s) to forecast.
    date_column : str, None
        Name of the column containing timestamps.
    series_id_column : str, None
        Name of the column identifying individual series.
    profile : ForecastingProfile, None
        Pre-computed profile, when the caller supplied one.

    Returns
    -------
    data : pandas DataFrame
        Coerced DataFrame.
    target : str, list
        Resolved target column name(s).
    date_column : str, None
        Resolved date column name.
    series_id_column : str, None
        Resolved series identifier column name.
    """

    if profile is None:
        data_df, target = _resolve_data_and_target(data, target, date_column)
        return data_df, target, date_column, series_id_column

    dp = profile.data_profile

    # A Series carries its own name, which is the target the profile was
    # built with; `_resolve_data_and_target` already reconciles it with an
    # explicit `target`. For any other input the profile fills the gap.
    if not isinstance(data, pd.Series) and target is None:
        target = dp.target
    # The CSV loader checks the date column of the profile, which the script
    # reads, and reports it when its dates cannot be used.
    data_df, target = _resolve_data_and_target(
                          data        = data,
                          target      = target,
                          date_column = dp.date_column,
                      )
    if target != dp.target:
        raise InvalidInputError(
            f"`target` {target!r} does not match the target recorded in "
            f"`profile` ({dp.target!r}). Pass the target the profile was "
            f"built with, or omit it.",
            field = "target",
        )

    date_column = _match_profile_column("date_column", date_column, dp.date_column)
    series_id_column = _match_profile_column(
        "series_id_column", series_id_column, dp.series_id_column
    )

    required = list(target) if isinstance(target, list) else [target]
    required += [col for col in (date_column, series_id_column) if col is not None]
    # A MultiIndex input keeps the date and series identifier as index
    # levels; the profiler flattens them into columns of the same name.
    available = set(data_df.columns) | {
        name for name in data_df.index.names if name is not None
    }
    missing = [col for col in required if col not in available]
    if missing:
        raise InvalidInputError(
            f"`data` does not contain the column(s) {missing} recorded in "
            f"`profile`. Available columns: {list(data_df.columns)}. Pass the "
            f"dataset the profile was built from.",
            field = "data",
        )

    return data_df, target, date_column, series_id_column


# The CSV path or URL that `compare()` read, while it runs its candidates on
# the DataFrame already read: their scripts load that file, not the
# placeholder of data passed in memory.
_RUN_DATA_PATH: ContextVar[str | None] = ContextVar("_RUN_DATA_PATH", default=None)


@contextmanager
def _data_path_of_run(data_path: str | None) -> Iterator[None]:
    """
    Within the block, record `data_path` for the data passed in memory to
    `_with_data_path`. None leaves it as it is.
    """
    token = _RUN_DATA_PATH.set(data_path)
    try:
        yield
    finally:
        _RUN_DATA_PATH.reset(token)


def recorded_data_path(data: object) -> str:
    """
    Return the path a profile records for `data`, which the script loads.

    A CSV path or URL is recorded as given, except a path written exactly
    as the placeholder of data passed in memory (`'data.csv'`), which is
    recorded as `'./data.csv'`: the same file, without being taken for
    data passed in memory, which the script reads with its index. Data
    passed in memory records the placeholder.

    Parameters
    ----------
    data : object
        Data as the caller passed it.

    Returns
    -------
    data_path : str
        Path the script loads.
    """

    if not isinstance(data, (str, Path)):
        return PLACEHOLDER_DATA_PATH
    data_path = str(data)
    if data_path == PLACEHOLDER_DATA_PATH:
        return f"./{PLACEHOLDER_DATA_PATH}"
    return data_path


def _with_data_path(
    profile: ForecastingProfile,
    data: object,
) -> ForecastingProfile:
    """
    Record in the profile the data the workflow ran on, so the script
    loads the file that ran.

    The workflows that execute a script profile the DataFrame already read
    from the path, so `profile()` records its placeholder, and a saved
    profile keeps the path it was built from. With a CSV path or URL, the
    profile records it; with data passed in memory, the placeholder
    `'data.csv'`, so the script never loads the file a saved profile was
    built from instead of the data that ran (it fails loudly when the data
    is not saved there). The path is set with `model_copy`, without reading
    the file again; it reaches the script through `repr()`.

    Parameters
    ----------
    profile : ForecastingProfile
        Profile the script is rendered from.
    data : object
        Data as the caller passed it. None keeps the path of the profile.

    Returns
    -------
    profile : ForecastingProfile
        The same profile when `data` is None or the profile already records
        it; otherwise a copy that records it.
    """

    if data is None:
        return profile
    data_path = recorded_data_path(data)
    if data_path == PLACEHOLDER_DATA_PATH and _RUN_DATA_PATH.get() is not None:
        data_path = _RUN_DATA_PATH.get()
    if profile.data_profile.data_path == data_path:
        return profile
    data_profile = profile.data_profile.model_copy(update={"data_path": data_path})
    return profile.model_copy(update={"data_profile": data_profile})


def _check_feature_name_collisions(
    plan: ForecastPlan,
    data_profile: DataProfile,
) -> None:
    """
    Reject exogenous columns named like a predictor the forecaster creates.

    skforecast names the lags `lag_k` and the window features after their
    statistic and window (`roll_mean_7`); `ForecasterDirectMultiVariate`
    prefixes both with the series. An exogenous column with one of those
    names made the script fail with "Duplicated feature names detected".
    Calendar features are handled by `plan()` (the data column is kept).

    Parameters
    ----------
    plan : ForecastPlan
        Plan just built.
    data_profile : DataProfile
        Profile of the data.

    Returns
    -------
    None
    """
    from skforecast.preprocessing import RollingFeatures

    if plan.task_type not in ("single_series", "multi_series", "multivariate"):
        return
    if not plan.use_exog or not data_profile.exog_columns:
        return
    kwargs = plan.forecaster_kwargs
    lags = _normalize_lags(kwargs.get("lags")) or []
    names = [f"lag_{lag}" for lag in lags]
    window_features = kwargs.get("window_features") or []
    stats = [stat for entry in window_features for stat in entry["stats"]]
    sizes = [
        entry["window_size"] for entry in window_features for _ in entry["stats"]
    ]
    if stats:
        names += RollingFeatures(stats=stats, window_sizes=sizes).features_names
    if plan.task_type == "multivariate":
        targets = data_profile.target
        targets = targets if isinstance(targets, list) else [targets]
        names = [f"{series}_{name}" for series in targets for name in names]

    clashes = [column for column in data_profile.exog_columns if column in set(names)]
    if clashes:
        shown = ", ".join(repr(column) for column in clashes[:5])
        if len(clashes) > 5:
            shown += f" and {len(clashes) - 5} more"
        raise InvalidInputError(
            f"Exogenous column(s) {shown} have the name of a predictor "
            f"that {plan.forecaster} creates (a lag or a window feature), so "
            f"the script would fail with duplicated feature names. Rename "
            f"them in the data.",
            field = "data",
            hint  = (
                "Rename the exogenous columns named like lags ('lag_1') or "
                "window features ('roll_mean_7')."
            ),
        )


def profile_structure(data_profile: DataProfile) -> dict:
    """
    Return what a profile says about the structure of the data.

    The structure is what a plan, a cross-validation strategy and the
    generated script are built on: the format, the target, the date and
    series id columns, the type and frequency of the index, and the
    exogenous columns. Two profiles of the same structure differ only in
    their values (statistics, missing values, warnings), in the series of
    data in long format (a product that appears or disappears) or in the
    path of the data.

    Parameters
    ----------
    data_profile : DataProfile
        Profile of the data.

    Returns
    -------
    structure : dict
        Structural fields of the profile.
    """
    target = data_profile.target
    # The order of the columns does not change what the data holds.
    return {
        "data_format": data_profile.data_format,
        "target": sorted(map(str, target)) if isinstance(target, list) else target,
        "date_column": data_profile.date_column,
        "series_id_column": data_profile.series_id_column,
        "index_type": data_profile.index_type,
        "frequency": data_profile.frequency,
        "exog_columns": sorted(map(str, data_profile.exog_columns)),
        "categorical_exog": sorted(map(str, data_profile.categorical_exog)),
    }


def structure_differences(first: DataProfile, second: DataProfile) -> list[str]:
    """
    Return the structural fields in which two profiles differ.

    Parameters
    ----------
    first : DataProfile
        First profile.
    second : DataProfile
        Second profile.

    Returns
    -------
    differences : list of str
        One `'name: first != second'` per field of `profile_structure` that
        differs, with lists cut at 5 items. Empty when the structure is the
        same. Two frequencies of the same period (`same_period`) are not a
        difference.
    """
    a, b = profile_structure(first), profile_structure(second)
    return [
        f"{name}: {_short(a[name])} != {_short(b[name])}"
        for name in a
        if a[name] != b[name]
        and not (name == "frequency" and same_period(a[name], b[name]))
    ]


def _period(frequency: str | None) -> object:
    """
    Return the period a frequency counts in, whatever the date each
    observation is stamped with: `'MS'` and `'ME'` are both months,
    `'W-SUN'` and `'W-MON'` weeks, `'QS-JAN'` and `'QE-DEC'` quarters. A
    frequency pandas cannot read is returned as it is.
    """
    if frequency is None:
        return None
    try:
        offset = pd.tseries.frequencies.to_offset(frequency)
    except (ValueError, TypeError):
        return frequency
    # 'W-SUN' -> 'W', 'QS-JAN' -> 'QS': the anchor is the stamp, not the
    # period. Then the start and end variants: 'QS' and 'QE' -> 'Q'. The
    # units of time ('s', 'ms') are lower case and stay as they are.
    name = offset.name.split("-")[0]
    if len(name) > 1 and name[-1] in "SE":
        name = name[:-1]

    return (offset.n, name)


def same_period(first: str | None, second: str | None) -> bool:
    """
    Tell whether two frequencies count the same period.

    Monthly data stamped on the first day of the month (`'MS'`) and on the
    last (`'ME'`) have the same observations, seasonality and lags, and so
    have weekly data stamped on another weekday: a plan built for one runs
    unchanged on the other.

    Parameters
    ----------
    first : str, None
        First frequency.
    second : str, None
        Second frequency.

    Returns
    -------
    same : bool
        Whether both are the same multiple of the same period.
    """

    return first == second or _period(first) == _period(second)


def _short(value: object) -> str:
    """Quote a structural value, listing at most 5 items of a list."""
    if isinstance(value, list) and len(value) > 5:
        return f"{value[:5]} (first 5 of {len(value)})"
    return repr(value)


def _check_plan_matches_profile(plan: ForecastPlan, data_profile: DataProfile) -> None:
    """
    Reject a plan received for data of another structure.

    A plan is built from a profile (`plan()`); used with the profile of
    other data, the script ran with lags, features and a frequency that do
    not fit it, without an error. Checked: the frequency the plan was built
    for (when it has one; another stamp of the same period, `'ME'` for
    `'MS'`, is accepted, see `same_period`), that its task type fits the shape of the data
    (`_validate_task_input`), that the data has exogenous variables when the
    plan uses them, and a datetime index for its calendar features. Which
    columns are exogenous is not compared: a plan reads the exogenous
    columns of the profile it runs with.

    Parameters
    ----------
    plan : ForecastPlan
        Plan received.
    data_profile : DataProfile
        Profile of the data it runs on.

    Returns
    -------
    None
    """
    # A plan built by hand may have no frequency: the script reads the one
    # of the profile, so there is nothing to compare.
    if plan.frequency is not None and not same_period(
        plan.frequency, data_profile.frequency
    ):
        raise InvalidInputError(
            f"The plan was built for data of frequency {plan.frequency!r}, "
            f"and the data has frequency {data_profile.frequency!r}. Build "
            f"the plan from the profile of these data with `plan()`.",
            field = "plan",
        )
    _validate_task_input(data_profile, plan.task_type)
    if plan.use_exog and not data_profile.exog_columns:
        raise InvalidInputError(
            "The plan uses exogenous variables and the data has none. Build "
            "the plan from the profile of these data with `plan()`.",
            field = "plan",
        )
    if (
        plan.forecaster_kwargs.get("calendar_features")
        and data_profile.index_type != "datetime"
    ):
        raise InvalidInputError(
            "The plan has calendar features, which need dates, and the data "
            "has no datetime index. Build the plan from the profile of these "
            "data with `plan()`.",
            field = "plan",
        )


def _check_cv_matches_profile(cv: CVResult, data_profile: DataProfile) -> None:
    """
    Reject the `CVResult` of a profile of another structure.

    Its strategy (the first training window, a date or a size) was derived
    from that profile; with data of another shape it failed inside the
    script or split other dates.

    Parameters
    ----------
    cv : CVResult
        Result of `create_cv()`.
    data_profile : DataProfile
        Profile of the data it runs on.

    Returns
    -------
    None
    """
    differences = structure_differences(cv.profile.data_profile, data_profile)
    if differences:
        raise InvalidInputError(
            f"The CVResult was created for data of another structure "
            f"({'; '.join(differences)}). Create the strategy from the "
            f"profile of these data with `create_cv()`, or pass its "
            f"TimeSeriesFold (`cv.cv`).",
            field = "cv",
        )


def _warn_window_without_refit(
    fixed_train_size: bool | None,
    refit: object,
    forecaster: str,
) -> None:
    """
    Warn about a `fixed_train_size` passed for a forecaster trained once.

    A forecaster trained once has one training window, so the window type
    has no effect on its backtest: the strategy runs as without it, and the
    caller is told so. `ForecasterStats`, which skforecast refits in every
    fold, has its own warning in `create_cv()`.

    Parameters
    ----------
    fixed_train_size : bool, None
        Value passed by the caller; None when not passed.
    refit : bool, int
        Resolved `refit` of the strategy.
    forecaster : str
        Forecaster of the plan.

    Returns
    -------
    None
    """
    if fixed_train_size is None or forecaster == "ForecasterStats":
        return
    refits = refit is True or (
        isinstance(refit, numbers.Integral)
        and not isinstance(refit, bool)
        and refit > 0
    )
    if not refits:
        warnings.warn(
            f"`fixed_train_size={fixed_train_size!r}` has no effect: with "
            f"`refit={refit!r}` the forecaster is trained once, on a single "
            f"training window. Pass `refit=True` (or an integer) to refit "
            f"it, or omit `fixed_train_size` to avoid this warning.",
            IgnoredArgumentWarning,
            stacklevel = 3,
        )


def _direct_gap_issue(plan: ForecastPlan, gap: int) -> str | None:
    """
    Say why a direct forecaster cannot be backtested with a strategy that
    has a gap, or return None when it can.

    A direct forecaster predicts the `steps` it was built for, and a fold
    with a gap asks it for `steps + gap`, which skforecast rejects.

    Parameters
    ----------
    plan : ForecastPlan
        Plan to backtest.
    gap : int
        `gap` of the strategy.

    Returns
    -------
    issue : str, None
        What fails, or None when the plan is not direct or there is no gap.
    """
    if plan.forecaster not in DIRECT_FORECASTERS or not gap:
        return None

    return (
        f"{plan.forecaster} is trained to predict {plan.steps} steps, and "
        f"with `gap={gap}` each fold needs steps + gap = {plan.steps + gap} "
        f"steps ahead, so skforecast would fail"
    )


def _check_direct_gap(plan: ForecastPlan, cv: TimeSeriesFold) -> None:
    """
    Raise when a direct forecaster is backtested with a strategy that has a
    gap (see `_direct_gap_issue`).

    Parameters
    ----------
    plan : ForecastPlan
        Plan to backtest.
    cv : TimeSeriesFold
        Strategy of the backtest.

    Returns
    -------
    None
    """
    issue = _direct_gap_issue(plan, cv.gap)
    if issue is not None:
        raise InvalidInputError(
            f"{issue}. Use a strategy without gap, or a recursive forecaster.",
            field = "cv",
        )


def _warn_direct_gap(plan: ForecastPlan, gap: int) -> None:
    """
    Warn when a strategy with a gap is built for a direct forecaster: its
    backtest raises (see `_check_direct_gap`), but the strategy can still
    serve the candidates of `compare()` that are not direct.

    Parameters
    ----------
    plan : ForecastPlan
        Plan the strategy is built for.
    gap : int
        `gap` of the strategy.

    Returns
    -------
    None
    """
    issue = _direct_gap_issue(plan, gap)
    if issue is not None:
        warnings.warn(
            f"{issue}: `backtest()` and `backtest_code()` of this plan with "
            f"this strategy raise. The strategy can still serve the "
            f"candidates of `compare()` that are not direct; use a strategy "
            f"without gap to backtest this plan.",
            UserWarning,
            stacklevel = 3,
        )


def _unwrap_cv(cv: TimeSeriesFold | CVResult) -> TimeSeriesFold:
    """
    Return the `TimeSeriesFold` behind a `cv` argument.

    The backtesting workflows accept either a bare splitter or the
    `CVResult` produced by `create_cv()`.

    Parameters
    ----------
    cv : TimeSeriesFold, CVResult
        Cross-validation strategy as passed by the caller.

    Returns
    -------
    cv : TimeSeriesFold
        The splitter itself.
    """

    if isinstance(cv, CVResult):
        return cv.cv
    if not isinstance(cv, TimeSeriesFold):
        raise InvalidInputTypeError(
            f"`cv` must be a skforecast TimeSeriesFold or the CVResult of "
            f"create_cv(), got {type(cv).__name__}.",
            field = "cv",
        )
    return cv


def _check_evaluated_target(
    data: pd.DataFrame,
    data_profile: DataProfile,
    cv: TimeSeriesFold | None = None,
    end_train: str | None = None,
    steps: int | None = None,
    level: str | None = None,
) -> None:
    """
    Reject an evaluation whose test dates have missing target values.

    For a single series, skforecast computes the backtesting metrics on the
    raw target of the test folds without dropping missing values, so one
    missing value (or one missing timestamp, which `asfreq()` restores as a
    missing value) in a test fold makes every metric fail with "Input
    contains NaN", whatever the estimator. The generated evaluation script
    fails the same way on the test split. This check names the dates up
    front. Multi-series backtesting drops them per series and is not
    checked. `end_train` is read in the time zone of the dates; a date of
    the strategy that cannot be compared with them (a naive date on a time
    zone aware index) skips the check, and the generated script reports it.

    Parameters
    ----------
    data : pandas DataFrame
        Dataset the script runs on.
    data_profile : DataProfile
        Profile of `data`.
    cv : TimeSeriesFold, default None
        Cross-validation of a backtest. Its test folds are checked.
    end_train : str, default None
        Last training date of an evaluation-mode forecast. The `steps`
        dates after it are checked. Ignored when `cv` is given.
    steps : int, default None
        Forecast horizon of an evaluation-mode forecast.
    level : str, default None
        Series of wide-format data whose test dates are checked: the level
        that `ForecasterDirectMultiVariate` predicts, the series its
        metrics are computed on. None checks the target of a single series.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        If a checked date has a missing target value.
    """

    if level is None and (
        data_profile.n_series != 1 or not isinstance(data_profile.target, str)
    ):
        return
    target = data_profile.target if level is None else level
    if not data_profile.missing_target and not data_profile.has_gaps:
        return

    # Rebuild the target as the generated script does: datetime index,
    # sorted, and on its regular grid when the frequency is known.
    if data_profile.date_column is not None and data_profile.date_column in data:
        index = pd.to_datetime(data[data_profile.date_column])
    else:
        index = data.index
    if target not in data:
        return
    y = pd.Series(data[target].to_numpy(), index=index).sort_index()
    if y.index.has_duplicates:
        return
    if data_profile.frequency is not None and isinstance(y.index, pd.DatetimeIndex):
        y = y.asfreq(data_profile.frequency)

    if cv is not None:
        original_verbose = cv.verbose
        cv.verbose = False
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                folds = cv.split(X=y, as_pandas=True)
        except TypeError:
            # A date of the strategy without the time zone of the index: the
            # generated script fails on it with its own error.
            return
        finally:
            cv.verbose = original_verbose
        positions = sorted({
            position
            for start, end in zip(
                folds["test_start_with_gap"], folds["test_end_with_gap"]
            )
            for position in range(int(start), int(end))
        })
        evaluated = y.iloc[positions]
        where = "in the test folds"
    elif end_train is not None and steps is not None:
        end = training_end(end_train, getattr(y.index, "tz", None))
        evaluated = y.loc[y.index > end].iloc[:steps]
        where = "in the test split"
    else:
        return

    missing = evaluated.index[evaluated.isna()]
    if len(missing) == 0:
        return

    shown = ", ".join(str(date) for date in missing[:5])
    if len(missing) > 5:
        shown += f" and {len(missing) - 5} more"
    raise InvalidInputError(
        f"The target has {len(missing)} missing value(s) {where} ({shown}), "
        f"counting the missing timestamps that asfreq() restores. skforecast "
        f"cannot compute the metrics on them, whatever the estimator. Impute "
        f"the target, or evaluate on dates without missing values.",
        field = "data",
    )


def long_training_message(
    estimator_fits: int,
    n_fits: int,
    forecaster: str,
    steps: int,
) -> str:
    """
    Describe the cost of a backtest in estimator fits.

    Parameters
    ----------
    estimator_fits : int
        Number of estimator fits of the backtest.
    n_fits : int
        Number of folds in which the forecaster is trained.
    forecaster : str
        Name of the skforecast forecaster class.
    steps : int
        Forecast horizon of each fold.

    Returns
    -------
    message : str
        Sentence with the number of fits, broken down into trainings and
        estimators for a direct forecaster.
    """

    breakdown = (
        f" ({n_fits} trainings x {steps} estimators)"
        if forecaster in DIRECT_FORECASTERS else ""
    )

    return f"{forecaster} will be fit {estimator_fits} times{breakdown}"


def warn_long_training(
    estimator_fits: int,
    n_fits: int,
    forecaster: str,
    steps: int,
) -> None:
    """
    Warn before a backtest that fits the estimator many times.

    skforecast emits `LongTrainingWarning` from the same threshold, but the
    generated scripts pass `suppress_warnings=True`, so the assistant warns
    itself, before anything runs.

    Parameters
    ----------
    estimator_fits : int
        Number of estimator fits of the backtest.
    n_fits : int
        Number of folds in which the forecaster is trained.
    forecaster : str
        Name of the skforecast forecaster class.
    steps : int
        Forecast horizon of each fold.

    Returns
    -------
    None
    """

    if estimator_fits <= LONG_TRAINING_FITS:
        return

    # skforecast refits ForecasterStats in every fold whatever `refit`
    # says, so only fewer folds make its backtest shorter.
    if forecaster == "ForecasterStats":
        remedy = (
            "skforecast refits it in every fold whatever `refit` says, so use "
            "a cross-validation strategy with fewer folds (a later "
            "`initial_train_size` or a larger `fold_stride`; `skip_folds` is "
            "not allowed for it)"
        )
    else:
        remedy = (
            "use a cross-validation strategy with `refit=False` (train once) "
            "or an integer `refit` (retrain every n folds)"
        )
    warnings.warn(
        f"{long_training_message(estimator_fits, n_fits, forecaster, steps)}. "
        f"This can take substantial amounts of time. If not feasible, "
        f"{remedy}.",
        LongTrainingWarning,
        stacklevel=3,
    )
