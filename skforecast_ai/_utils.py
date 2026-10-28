################################################################################
#                                  Utils                                       #
#                                                                              #
# Shared internal utilities for skforecast_ai                                  #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import copy
import numbers
import re
import warnings
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Literal, NamedTuple
import numpy as np
import pandas as pd
from pydantic import BaseModel
from skforecast.exceptions import IgnoredArgumentWarning, LongTrainingWarning
from skforecast.model_selection import TimeSeriesFold

from ._constants import (
    AUTOREG_FORECASTERS,
    CATEGORICAL_FORECASTERS,
    DIRECT_FORECASTERS,
    LONG_INFERENCE_WINDOWS,
    LONG_TRAINING_FITS,
    MAX_FEATURE_FRACTION,
    ML_TASK_TYPES,
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
from ._dates import (
    is_text,
    parse_text_dates,
    row_dates,
    training_end,
)
from .recommendation.backtesting import count_estimator_fits, count_inference_windows
from .recommendation.missing_values import closed_days_remedy
from .profiling.data_profile import (
    COMPACT_DATE_FORMAT,
    _caller_stacklevel,
    _compact_dates,
    _normalize_multiindex,
    _read_date_column,
    _try_parse_first_date_column,
    _validate_target_format,
    check_csv_fields,
    csv_read_kwargs,
    closed_weekdays,
    date_issue_hint,
    decimal_after_sample,
    frame_date_column,
    frame_date_format,
    read_csv_with_dialect,
    series_ids_as_text,
    thousands_after_sample,
    weekday_names,
    without_series_ids,
)
from .profiling.csv_dialect import (
    CP1252,
    CSV_SEPARATORS,
    CsvDialectError,
    DEFAULT_CSV_DECIMAL,
    DEFAULT_CSV_ENCODING,
    DEFAULT_CSV_SEP,
    check_csv_dialect,
    cp1252_note,
    detect_csv_dialect,
    read_url_sample,
    sample_date_column,
    undefined_byte_error,
)
from .schemas import (
    ComparisonCost,
    CVResult,
    DataProfile,
    ForecastingProfile,
    ForecastPlan,
    FutureExogFile,
    OVERRIDE_NAMES,
)
from .exceptions import (
    CostNotConfirmedError,
    DataContentError,
    DataNotFoundError,
    InvalidInputError,
    InvalidInputTypeError,
)

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
    # Lags and windows that fit on their own, with an order larger than
    # them: the order is what does not fit.
    if (
        differentiation
        and differentiation > max_span
        and max_span <= max_allowed < max_span + differentiation
    ):
        raise InvalidInputError(
            f"`differentiation={differentiation}` plus the largest lag or "
            f"window size ({max_span}) exceeds the maximum of {max_allowed} "
            f"({int(MAX_FEATURE_FRACTION * 100)}% of {span_index_length} "
            f"observations). Use a smaller order (1 or 2 remove a trend), or "
            f"fewer lags and smaller window sizes.",
            code  = "insufficient_data",
            field = "differentiation",
        )
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

    # Wide series share the rows of the frame: their lengths, from the first
    # to the last value, differ by the missing values at the ends of a
    # column, which the forecaster reads as missing values.
    if task_type == "multivariate" and data_profile.data_format != "wide":
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
# the split boundary, the explanation, the warnings, the marks or the
# exogenous columns, which the plan records from its profile.
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
    "exog_columns",
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

    `end_train`, `explanation`, `warnings`, `llm_refined_fields`,
    `overridden_fields` and `exog_columns` (recorded from the profile) are
    not compared, nor the fields that an explicit override of the call
    replaces anyway.

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


# Decisions about the data rather than about the forecaster: one the rules
# made is named by `dropped_plan_decisions` when the refined forecaster
# cannot take it. Lags, window features and the estimator belong to the
# forecaster being replaced, and are named only when the user chose them.
_DATA_DECISIONS = (
    "use_exog",
    "differentiation",
    "calendar_features",
    "target_transformer",
    "dropna_from_series",
)


def _is_neutral(value: object) -> bool:
    """
    Whether the value of a decision, as `plan_override_value` returns it,
    leaves the plan as if the decision did not exist: no differencing, no
    calendar features, no transformer, no exogenous variables, no dropped
    rows, no keyword arguments.
    """
    return value is None or value is False or value == "none" or value in ([], {})


def dropped_plan_decisions(
    plan: ForecastPlan,
    refined: ForecastPlan,
    explicit_keys: set[str],
    discarded: list[str],
    data_profile: DataProfile,
) -> str | None:
    """
    Text of the warning that names the decisions of a plan that
    `refine_plan()` leaves out of the refined plan, and why.

    A decision is named when the plan holds a value with an effect (not
    None, `False`, `'none'` or an empty list or dict) that the refined plan
    does not hold, and either the user chose it (`plan.overridden_fields`),
    the LLM refined it (`lags` and `window_features` in
    `plan.llm_refined_fields`, which count as chosen by the user) or the
    rules made a decision about the data (`use_exog`, `differentiation`,
    `calendar_features`, `target_transformer`, `dropna_from_series`) that
    the refined forecaster cannot take. A value that the rules decide again
    for the refined forecaster is not named, nor a key overridden in the
    call, nor one already named as an edit by hand in `discarded`.

    `transformer_exog` and `categorical_features`, which the rules set in
    `forecaster_kwargs` and `plan()` does not take, are named the same way
    when they had an effect (the plan read numeric or categorical exogenous
    columns) and the refined forecaster does not use them: one that is not
    autoregressive, or for `categorical_features` one that does not take
    categorical features either, nor reads those columns itself (a
    foundation model with categorical covariates does).

    Parameters
    ----------
    plan : ForecastPlan
        Plan received by `refine_plan()`.
    refined : ForecastPlan
        Plan returned by `refine_plan()`.
    explicit_keys : set of str
        Keys overridden in the call.
    discarded : list of str
        Fields of `plan` named as edited by hand (`discarded_plan_edits`).
    data_profile : DataProfile
        Profile of the data both plans are built from, which says which
        exogenous columns are categorical.

    Returns
    -------
    message : str, None
        Text of the warning, or None when nothing is left out.
    """

    edited = {
        _FIELD_OVERRIDES.get(field)
        or _FORECASTER_KWARG_OVERRIDES.get(field[len("forecaster_kwargs['"):-2])
        for field in discarded
    }
    not_taken: list[str] = []
    kwargs_text = None
    for name in OVERRIDE_NAMES:
        if name in ("forecaster", "metric") or name in explicit_keys or name in edited:
            continue
        value = plan_override_value(plan, name)
        if _is_neutral(value) or value == plan_override_value(refined, name):
            continue
        chosen = name in plan.overridden_fields
        # Lags and window features the LLM refined at the request of the
        # user are the choice of the user, not of the rules.
        refined_by_llm = not chosen and name in plan.llm_refined_fields
        if not chosen and not refined_by_llm:
            # A decision of the rules is decided again when the refined
            # forecaster takes it; it is left out only when it cannot.
            takes = (
                refined.task_type != "baseline"
                if name == "use_exog"
                else refined.forecaster in AUTOREG_FORECASTERS
            )
            if name not in _DATA_DECISIONS or takes:
                continue
        chosen_by = (
            "(refined by the LLM)" if refined_by_llm
            else f"(chosen by the {'user' if chosen else 'rules'})"
        )
        if name == "estimator_kwargs" and refined.estimator is not None:
            kwargs_text = (
                f"refine_plan() left out the estimator_kwargs of the plan, "
                f"{value!r} {chosen_by}, written for {plan.estimator}: "
                f"{refined.estimator} starts from its defaults; pass "
                f"`estimator_kwargs` to set its own."
            )
        else:
            not_taken.append(f"{name}={value!r} {chosen_by}")
    if "use_exog" not in explicit_keys:
        not_taken += _dropped_exog_settings(plan, refined, discarded, data_profile)

    texts = []
    if not_taken:
        texts.append(
            f"refine_plan() left out the values of the plan that "
            f"{refined.forecaster} does not take: {', '.join(not_taken)}."
        )
    if kwargs_text is not None:
        texts.append(kwargs_text)

    return " ".join(texts) or None


def _dropped_exog_settings(
    plan: ForecastPlan,
    refined: ForecastPlan,
    discarded: list[str],
    data_profile: DataProfile,
) -> list[str]:
    """
    The `transformer_exog` and `categorical_features` of a plan that had an
    effect and that the refined forecaster does not use, as
    `dropped_plan_decisions` names them (see there).
    """
    from ._future_exog import used_exog_columns

    if not plan.use_exog:
        return []
    used = used_exog_columns(plan, data_profile)
    categorical = [
        column for column in used if column in data_profile.categorical_exog
    ]
    used_by_refined = used_exog_columns(refined, data_profile)
    takes = {
        # Scales the numeric columns; an autoregressive forecaster that does
        # not hold it had it decided again by the rules for its estimator.
        "transformer_exog": (
            len(used) > len(categorical),
            refined.forecaster in AUTOREG_FORECASTERS,
        ),
        "categorical_features": (
            bool(categorical),
            refined.forecaster in CATEGORICAL_FORECASTERS
            or set(categorical) <= set(used_by_refined),
        ),
    }
    named = []
    for key, (had_effect, used_by_new) in takes.items():
        value = plan.forecaster_kwargs.get(key)
        if (
            _is_neutral(value)
            or not had_effect
            or used_by_new
            or value == refined.forecaster_kwargs.get(key)
            or f"forecaster_kwargs['{key}']" in discarded
        ):
            continue
        named.append(f"{key}={value!r} (chosen by the rules)")

    return named


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
    exog: pd.DataFrame | str | Path | None,
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
    exog : pandas DataFrame, str, Path, None
        Future exogenous variables supplied for prediction mode, or the
        path of a CSV file with them, whose rows are counted once it is
        read (see `check_exog_covers_horizon`).
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
    # The rows of a file are counted once it is read.
    if exog is not None and not isinstance(exog, (str, Path)):
        check_exog_covers_horizon(exog, steps)


def check_exog_covers_horizon(exog: pd.DataFrame, steps: int) -> None:
    """
    Check that the future exogenous variables have a row for each of the
    `steps` of the horizon.

    Parameters
    ----------
    exog : pandas DataFrame
        Future exogenous variables.
    steps : int
        Forecast horizon.

    Returns
    -------
    None
    """
    if len(exog) < steps:
        raise InvalidInputError(
            f"`exog` must cover the forecast horizon: {steps} rows are "
            f"required but only {len(exog)} were provided.",
            field = "exog",
        )


# How the last CSV file read in this context is written: the path recorded
# for it, its separator, its decimal mark, its thousands separator, the
# format of its dates, the notes on how it was read and its encoding. The
# workflows read the file first and record its path in the profile later
# (`_with_data_path`), which takes the dialect from here instead of reading
# the file again.
_READ_CSV_DIALECT: ContextVar[
    tuple[str, str, str, str | None, str | None, tuple[str, ...], str] | None
] = ContextVar("_READ_CSV_DIALECT", default=None)


class DialectRead(NamedTuple):
    """
    How a CSV file was read: its separator, its decimal mark, its thousands
    separator, the format of its dates (`DataProfile.date_format`), the
    notes on how it was read (an encoding that cannot be checked, an order
    of the day and the month told from their regularity), which belong in
    `DataProfile.warnings`, and its encoding (`DataProfile.csv_encoding`).
    """

    sep: str | None
    decimal: str | None
    thousands: str | None
    date_format: str | None
    notes: tuple[str, ...] = ()
    encoding: str | None = None


def _dialect_read(data_path: str) -> DialectRead:
    """
    Return how the file recorded as `data_path` was read (see
    `DialectRead`), or None in every field (no notes) when the last CSV
    read in this context is another one (or none, for data passed in
    memory). The separator is never None for a file read.
    """
    read = _READ_CSV_DIALECT.get()
    if read is None or read[0] != data_path or data_path == PLACEHOLDER_DATA_PATH:
        return DialectRead(None, None, None, None)
    return DialectRead(*read[1:])


def encoding_notes(encoding: str, field: str = "data") -> list[str]:
    """
    Return the note on a CSV file read as cp1252, an encoding that cannot
    be checked (see `cp1252_note`), or none for UTF-8.
    """
    return [cp1252_note(field)] if encoding == CP1252 else []


def with_read_notes(
    data_profile: DataProfile,
    notes: tuple[str, ...] | list[str],
) -> DataProfile:
    """
    Return the data profile with the notes on how its file was read (its
    encoding, its dates) first among its warnings, as `create_data_profile`
    puts them, unless it has them already.
    """
    missing = [note for note in notes if note not in data_profile.warnings]
    if not missing:
        return data_profile
    return data_profile.model_copy(
        update={"warnings": [*missing, *data_profile.warnings]}
    )


# The date format of the saved profile that a refresh profiles data passed in
# memory with again (`ForecastingAssistant._refresh_profile`): it decides the
# order of their text dates when they read both ways, as it does for a file.
KNOWN_DATE_FORMAT: ContextVar[str | None] = ContextVar(
    "KNOWN_DATE_FORMAT", default=None
)


def _read_csv_url(
    url: str,
    sep: str | None = None,
    decimal: str | None = None,
    thousands: str | None = None,
    series_id_column: str | None = None,
    date_column: str | None = None,
) -> tuple[pd.DataFrame, str, str, str | None, str]:
    """
    Read the CSV file of a URL and return how it is written.

    The file is first read as before, with `','` and `'.'`. Only when a
    column name then holds another separator, or pandas cannot read the
    rows with `','` (rows with different numbers of decimal commas), is the
    start of the file downloaded again to tell its dialect (see
    `detect_csv_dialect`), and the file read with it, as the generated
    script reads it. So it is when the file is not UTF-8: it is then read
    as cp1252 (see `sample_encoding`), unless its start says it is in
    another encoding.

    Parameters
    ----------
    url : str
        URL of the file.
    sep : str, default None
        Separator of the fields. If None, it is detected.
    decimal : str, default None
        Decimal mark. If None, it is detected.
    thousands : str, default None
        Thousands separator. If None, it is detected, except when `decimal`
        is `'.'`.
    series_id_column : str, default None
        Column of the series ids of long-format data, read as text (see
        `read_csv_with_dialect`).
    date_column : str, default None
        Column of the dates, read as text with a thousands separator (see
        `read_csv_with_dialect`).

    Returns
    -------
    data : pandas DataFrame
        Content of the file.
    sep : str
        Separator the file was read with.
    decimal : str
        Decimal mark the file was read with.
    thousands : str, None
        Thousands separator the file was read with, or None for none.
    encoding : str
        Encoding the file was read with: `'utf-8'` or `'cp1252'`.
    """
    decimal_given = decimal is not None
    unchecked = False
    dates = date_column
    encoding = DEFAULT_CSV_ENCODING
    # Whether the start of the file was read and is not in UTF-16 (see
    # `sample_encoding`), so that the file may be read as cp1252.
    checked = False

    def read_as(sep: str, decimal: str, thousands: str | None) -> pd.DataFrame:
        try:
            return pd.read_csv(
                       url,
                       **csv_read_kwargs(
                           sep, decimal, thousands, series_id_column, dates, encoding
                       ),
                   )
        except UnicodeDecodeError as exc:
            if encoding != CP1252:
                raise
            byte = exc.object[exc.start:exc.start + 1]
            raise undefined_byte_error(url, "data", byte) from exc

    def read(sep: str, decimal: str, thousands: str | None = None) -> pd.DataFrame:
        nonlocal encoding, checked
        try:
            return read_as(sep, decimal, thousands)
        except UnicodeDecodeError:
            if not checked:
                # Raises for a file in UTF-16 or with a null byte.
                checked = read_url_sample(url) is not None
            if encoding != DEFAULT_CSV_ENCODING or not checked:
                raise
        # Bytes that are not UTF-8, at the start or after it.
        encoding = CP1252
        return read_as(sep, decimal, thousands)

    if sep is None or decimal is None or thousands is not None:
        data, unread = None, None
        if sep is None and decimal is None and thousands is None:
            try:
                data = read(DEFAULT_CSV_SEP, DEFAULT_CSV_DECIMAL)
            except pd.errors.ParserError as exc:
                # Raised again below unless the file has another dialect.
                unread = exc
            else:
                header = "".join(str(column) for column in data.columns)
                if not any(
                    other in header for other in CSV_SEPARATORS
                    if other != DEFAULT_CSV_SEP
                ):
                    return (
                        data, DEFAULT_CSV_SEP, DEFAULT_CSV_DECIMAL, None, encoding
                    )
        sample = read_url_sample(url)
        if sample is None:
            # Checked once pandas reads the file (see `read_csv_with_dialect`).
            unchecked = True
            sep = DEFAULT_CSV_SEP if sep is None else sep
            decimal = DEFAULT_CSV_DECIMAL if decimal is None else decimal
            decimal = "," if thousands is not None else decimal
        else:
            checked = True
            if sample.encoding != encoding == DEFAULT_CSV_ENCODING:
                # Not UTF-8 at the start: read below as cp1252.
                encoding, data = sample.encoding, None
            sep, decimal, thousands = detect_csv_dialect(
                                          sample           = sample.text,
                                          source           = url,
                                          sep              = sep,
                                          decimal          = decimal,
                                          thousands        = thousands,
                                          series_id_column = series_id_column,
                                          date_column      = date_column,
                                      )
            check_csv_dialect(sep, decimal, thousands)
            dates = sample_date_column(sample.text, sep, series_id_column, date_column)
        # Without `series_id_column`: the question is whether the dialect is
        # the default one, which the `dtype` of the ids would hide.
        if not csv_read_kwargs(sep, decimal, thousands):
            if unread is not None:
                raise unread
            if data is not None:
                return data, sep, decimal, thousands, encoding

    data = read(sep, decimal, thousands)
    if unchecked:
        check_csv_dialect(sep, decimal, thousands)
    if (
        not decimal_given
        and sep != DEFAULT_CSV_SEP
        and decimal == DEFAULT_CSV_DECIMAL
        and decimal_after_sample(
                without_series_ids(data, series_id_column, dates), url, "data", sep
            ) != decimal
    ):
        decimal = ","
        data = read(sep, decimal)
    if thousands is None and decimal == "," and dates is None:
        # Without the start of the file (`sep` and `decimal` given), the
        # dates are found in the file read.
        dates = frame_date_column(data, series_id_column)
    if (
        thousands is None
        and decimal == ","
        and thousands_after_sample(
                without_series_ids(data, series_id_column, dates), url, "data"
            ) is not None
    ):
        thousands = "."
        data = read(sep, decimal, thousands)

    return data, sep, decimal, thousands, encoding


def _resolve_data_and_target(
    data: pd.Series | pd.DataFrame | str | Path,
    target: str | list[str] | None,
    date_column: str | None = None,
    sep: str | None = None,
    decimal: str | None = None,
    thousands: str | None = None,
    series_id_column: str | None = None,
    dayfirst: bool | None = None,
    date_format: str | None = None,
) -> tuple[pd.DataFrame, str | list[str]]:
    """
    Coerce the input to a DataFrame and resolve the target column name.

    Centralizes the rules for accepting a `pandas Series` as input. When
    `data` is a Series, the target is derived from the Series name; for
    every other input type a `target` must be provided explicitly. CSV
    paths and URLs are loaded with `pandas.read_csv` (without `parse_dates`,
    deprecated in pandas 2.2+); date columns are detected and parsed by
    `_try_parse_first_date_column` instead, leaving every column intact so
    callers can reference a `date_column` by name. The separator, the
    decimal mark and the thousands separator of the file are detected
    unless given (see `read_csv_with_dialect`), and kept for
    `_with_data_path` to record them in the profile. The series ids of
    long-format data are text, as the generated script reads them: the
    column of a CSV file is read as text and the ids of a DataFrame are
    turned into text (see `series_ids_as_text`). The dates of a CSV file
    are read in the order of their day and month (see `_day_month_order`),
    and the format the script reads them with is kept with the dialect, as
    are its encoding, UTF-8 or cp1252 (see `sample_encoding`), and the
    notes on how the file was read (see `DialectRead`).

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
    sep : str, default None
        Separator of the fields of a CSV file: `','`, `';'` or a tabulator.
        If None, it is detected. Ignored for data passed in memory.
    decimal : str, default None
        Decimal mark of a CSV file: `'.'` or `','`. If None, it is
        detected. Ignored for data passed in memory.
    thousands : str, default None
        Thousands separator of a CSV file: `'.'`, with `','` as decimal
        mark. If None, it is detected. Ignored for data passed in memory.
    series_id_column : str, default None
        Column of the series ids of long-format data, whose ids become
        text.
    dayfirst : bool, default None
        Order of the day and the month of the dates of a CSV file that read
        in both: True for day first, False for month first. If None, it is
        told from the dates (see `_day_month_order`). Ignored for data
        passed in memory, whose text dates `create_data_profile` reads.
    date_format : str, default None
        Format of the dates recorded by a profile of the data, which decides
        the order of dates of a CSV file that read in both. Ignored for data
        passed in memory.

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
        be read as one or its separator, decimal mark or thousands separator
        cannot be told.
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

    check_csv_dialect(sep, decimal, thousands)
    if isinstance(data, (str, Path)):
        data_str = str(data)
        if data_str.startswith(("http://", "https://")):
            try:
                df, sep, decimal, thousands, encoding = _read_csv_url(
                                                  url              = data_str,
                                                  sep              = sep,
                                                  decimal          = decimal,
                                                  thousands        = thousands,
                                                  series_id_column = series_id_column,
                                                  date_column      = date_column,
                                              )
            except InvalidInputError:
                # The dialect of the file cannot be told.
                raise
            except Exception as e:
                # An unreachable URL is an OSError (urllib's HTTPError and
                # URLError); anything else was downloaded but is not a CSV.
                raise DataNotFoundError(
                    f"Could not read CSV from URL: '{data_str}'. {e}",
                    code  = None if isinstance(e, OSError) else "data_unreadable",
                    field = "data",
                ) from e
            check_csv_fields(df, data_str)
            notes = encoding_notes(encoding)
            df, read_format = _try_parse_first_date_column(
                                  data             = df,
                                  date_column      = date_column,
                                  series_id_column = series_id_column,
                                  dayfirst         = dayfirst,
                                  date_format      = date_format,
                                  notes            = notes,
                              )
            _READ_CSV_DIALECT.set(
                (
                    recorded_data_path(data), sep, decimal, thousands,
                    read_format, tuple(notes), encoding,
                )
            )
            return df, target
        path = Path(data_str)
        if not path.is_file():
            raise DataNotFoundError(
                f"CSV file not found: '{path}'. Please provide a valid file path.",
                field = "data",
            )
        df, sep, decimal, thousands, encoding = read_csv_with_dialect(
                                          path             = path,
                                          sep              = sep,
                                          decimal          = decimal,
                                          thousands        = thousands,
                                          series_id_column = series_id_column,
                                          date_column      = date_column,
                                      )
        notes = encoding_notes(encoding)
        df, read_format = _try_parse_first_date_column(
                              data             = df,
                              date_column      = date_column,
                              series_id_column = series_id_column,
                              dayfirst         = dayfirst,
                              date_format      = date_format,
                              notes            = notes,
                          )
        _READ_CSV_DIALECT.set(
            (
                recorded_data_path(data), sep, decimal, thousands, read_format,
                tuple(notes), encoding,
            )
        )
        return df, target

    return series_ids_as_text(data, series_id_column), target


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
    path: str | Path,
    date_column: str | None = None,
    series_id_column: str | None = None,
    date_format: str | None = None,
    index_type: str = "datetime",
) -> tuple[pd.DataFrame, FutureExogFile]:
    """
    Load the future exogenous variables from a CSV file.

    The separator, the decimal mark and the thousands separator of the file
    are detected as for the data (see `read_csv_with_dialect`).
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
    (`to_csv(index_label=False)`, R's `write.csv`) is read as before when
    every row has one field more than the header and its last column is
    not then empty; other rows longer than the header (a separator at the
    end of every row, a field too many in the first row) and a column
    without name and values raise (see `check_csv_fields`); rows made only
    of separators (a spreadsheet saved as CSV) are dropped,
    as they hold no date and no value. The dates become the index, sorted.
    The format of the dates is the file's own, told as for the data (see
    `_day_month_order`): dates in ISO 8601 (`to_csv()` of a frame with
    dates) need none, and day-first dates are read day first. Dates whose
    day and month read in both orders (the seven days of a short horizon)
    are read in the order of `date_format`, the format of the dates of the
    data, when it writes them so; otherwise in the only order in which they
    have a regular frequency, with a warning that says so, and when both
    orders have one, or neither, they raise. The encoding of the file is
    told as for the data (see `sample_encoding`): a file that is not UTF-8
    is read as cp1252, with a warning, as that cannot be checked.

    Future values of data without dates (`index_type` `'range'`) have no
    dates to read: their rows are the steps of the horizon, in order. A
    first column without a name (the index that `to_csv()` writes, or a
    header one field short) holds their positions and becomes the index,
    which must follow the data (see `validate_future_exog`); a file without
    it is numbered by position when it is read with the data (see
    `read_future_exog`).

    The path of the file and how it is written (its separator, decimal
    mark, thousands separator, encoding and format of the dates) are
    returned with the frame, as a `FutureExogFile`: the generated script
    reads that same file with them, as it reads the data with the dialect
    of the profile.

    Parameters
    ----------
    path : str, Path
        Path to the CSV file.
    date_column : str, default None
        Name of the column holding the dates.
    series_id_column : str, default None
        Name of the series id column of long-format data, read as text
        (`'001'`), as the series ids of the data.
    date_format : str, default None
        Format of the dates of the data (`DataProfile.date_format`), which
        decides the order of the day and the month of dates of the file
        that read in both.
    index_type : str, default 'datetime'
        Index of the data (`DataProfile.index_type`): `'range'` for data
        without dates, whose future values are read without dates.

    Returns
    -------
    exog : pandas DataFrame
        Future exogenous variables indexed by their dates, or, without
        dates, by the positions of the file or by row.
    exog_file : FutureExogFile
        File the generated script reads the future exogenous variables
        from, and how it is written.
    """
    path = Path(path)
    if not path.is_file():
        raise DataNotFoundError(
            f"Exog CSV not found: '{path}'.",
            field = "exog",
        )

    # Rows longer than the header raise, except a header one field short
    # (see `check_csv_fields`).
    exog, sep, decimal, thousands, encoding = read_csv_with_dialect(
                                        path             = path,
                                        field            = "exog",
                                        index_first      = True,
                                        series_id_column = series_id_column,
                                        date_column      = date_column,
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
    # and no value; the generated code dropped them with asfreq. The
    # positions of data without dates are the index the script reads, which
    # its `dropna(how='all')` does not look at: a row with a position and no
    # value is dropped too.
    values = exog
    if index_type == "range" and len(exog.columns) and exog.columns[0] == "Unnamed: 0":
        values = exog[exog.columns[1:]]
    filled = values.notna().any(axis=1).to_numpy()
    exog = exog[filled].reset_index(drop=True)
    if index_type == "range":
        return _exog_without_dates(
                   exog      = exog,
                   path      = path,
                   exog_file = FutureExogFile(
                                   path       = str(path),
                                   sep        = sep,
                                   decimal    = decimal,
                                   thousands  = thousands,
                                   encoding   = encoding,
                                   blank_rows = not filled.all(),
                               ),
               )
    text = {column: exog[column].copy() for column in exog.columns}
    # The format of the dates of the file, and the notes on how it was read
    # (its encoding, its dates), given as warnings.
    exog_format, notes = None, encoding_notes(encoding, "exog")
    if date_column is not None:
        if date_column not in exog.columns:
            raise DataContentError(
                f"The exog CSV '{path}' has no column {date_column!r}; its "
                f"columns are {list(exog.columns)}.",
                field = "exog",
            )
        values = exog[date_column]
        parsed, issue = None, None
        if is_text(values):
            parsed, issue, exog_format = _read_date_column(
                                             name        = date_column,
                                             values      = values,
                                             named       = True,
                                             date_format = date_format,
                                             source      = "exog",
                                             notes       = notes,
                                         )
        else:
            parsed = _compact_dates(values)
            if parsed is not None:
                exog_format = COMPACT_DATE_FORMAT
        if issue is not None:
            raise DataContentError(
                f"Exog CSV '{path}': {''.join(issue)}",
                code  = getattr(issue, "code", None),
                field = "exog",
                hint  = date_issue_hint(issue),
            )
        if parsed is None or parsed.isna().any():
            raise DataContentError(
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
                index = pd.read_csv(
                    path,
                    index_col   = 0,
                    parse_dates = True,
                    **csv_read_kwargs(sep, decimal, thousands, encoding=encoding),
                ).index
            if isinstance(index, pd.DatetimeIndex) and len(index) == len(filled):
                exog[first] = index[filled]
                found = first
                if _compact_dates(text[first]) is not None:
                    exog_format = COMPACT_DATE_FORMAT
        if found is None:
            try:
                exog, exog_format = _try_parse_first_date_column(
                                        data             = exog,
                                        series_id_column = series_id_column,
                                        date_format      = date_format,
                                        source           = "exog",
                                        notes            = notes,
                                    )
            except InvalidInputError as exc:
                raise DataContentError(
                    f"Exog CSV '{path}': {exc}",
                    code  = exc.code,
                    field = "exog",
                    hint  = exc.hint,
                ) from exc
            found = next(
                (
                    column for column in exog.columns
                    if not pd.api.types.is_datetime64_any_dtype(text[column])
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
        # The generated script reads the dates with `pd.to_datetime`: the
        # check shared with the data rejects most dates it cannot read, and
        # this one catches what that check lets through.
        try:
            with warnings.catch_warnings():
                # The dates were read already: pandas only repeats that it
                # parses each one on its own.
                warnings.simplefilter("ignore", UserWarning)
                parse_text_dates(text[found], exog_format)
        except (ValueError, TypeError) as exc:
            raise DataContentError(
                f"Exog CSV '{path}': the dates of column {found!r} cannot be "
                f"read as the generated code reads them: {exc}",
                field = "exog",
            ) from exc
    if found is None:
        # Nothing reads as dates: the first column, as `index_col=0` read it;
        # the checks of the future exogenous variables report it.
        found = exog.columns[0]
    for note in notes:
        # Read through `forecast()` too: the warning points at the user.
        warnings.warn(
            f"Exog CSV '{path}': {note}", UserWarning, stacklevel=_caller_stacklevel()
        )
    exog = exog.set_index(found).sort_index()
    if str(found).startswith("Unnamed: "):
        exog.index.name = None
    exog_file = FutureExogFile(
                    path        = str(path),
                    sep         = sep,
                    decimal     = decimal,
                    thousands   = thousands,
                    encoding    = encoding,
                    date_format = exog_format,
                    date_column = str(found),
                    blank_rows  = not filled.all(),
                )

    return exog, exog_file


def _exog_without_dates(
    exog: pd.DataFrame,
    path: Path,
    exog_file: FutureExogFile,
) -> tuple[pd.DataFrame, FutureExogFile]:
    """
    Return the future values of data without dates read from a CSV file, as
    `load_exog` reads them: a first column without a name holds the
    positions of the rows, which must be consecutive, and becomes the
    index, a RangeIndex from the first one, as the generated script reads it
    (`index_col=0`); without it, the rows are the steps of the horizon in
    order (`FutureExogFile.by_position`).
    """
    first = exog.columns[0] if len(exog.columns) else None
    by_position = first != "Unnamed: 0"
    if not by_position:
        positions = exog[first]
        # The script numbers the rows from the first position (a RangeIndex,
        # which skforecast requires), so they must be consecutive.
        if (
            not pd.api.types.is_numeric_dtype(positions)
            or positions.isna().any()
            or (positions != positions.round()).any()
            or (np.diff(positions.to_numpy()) != 1).any()
        ):
            raise DataContentError(
                f"Exog CSV '{path}': its first column has no name, so it is "
                f"read as the positions of the rows (the index that `to_csv()` "
                f"writes), but it does not hold consecutive whole numbers. The "
                f"data have no dates: the future values are one row per step "
                f"of the horizon, in order, and a first column of values needs "
                f"a name.",
                field = "exog",
            )
    for note in encoding_notes(exog_file.encoding, "exog"):
        warnings.warn(
            f"Exog CSV '{path}': {note}", UserWarning, stacklevel=_caller_stacklevel()
        )
    if by_position:
        return exog, exog_file.model_copy(update={"by_position": True})
    start = int(exog[first].iloc[0]) if len(exog) else 0
    exog = exog.drop(columns=first)
    exog.index = pd.RangeIndex(start, start + len(exog))

    return exog, exog_file


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


def _flatten_multiindex(
    data: pd.DataFrame,
    date_column: str | None,
    series_id_column: str | None,
) -> tuple[pd.DataFrame, str | None, str | None]:
    """
    Flatten long-format data indexed by a `(series_id, date)` MultiIndex.

    The generated script reads the date and the series identifier as
    columns of the frame saved with `to_csv()`: the levels are reset into
    columns of the same name, as profiling does (`_normalize_multiindex`,
    which rejects a MultiIndex that is not two levels named with text), and
    the ids of the first level become text (`series_ids_as_text`). Data
    without a MultiIndex keep their columns, with the series ids turned
    into text too.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    date_column : str, None
        Name of the date column. Filled from the second level when None.
    series_id_column : str, None
        Name of the series identifier column. Filled from the first level
        when None.

    Returns
    -------
    data : pandas DataFrame
        DataFrame without a MultiIndex.
    date_column : str, None
        Resolved date column name.
    series_id_column : str, None
        Resolved series identifier column name.
    """
    data, date_column, series_id_column = _normalize_multiindex(
        data, date_column, series_id_column
    )
    # The ids of a MultiIndex were a level, not a column turned into text.
    data = series_ids_as_text(data, series_id_column)

    return data, date_column, series_id_column


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

    Long-format data indexed by a `(series_id, date)` MultiIndex is
    flattened as profiling flattens it (`_flatten_multiindex`): its
    levels become columns of the same name, which is also how the
    generated script reads the frame saved with `to_csv()`, and the series
    ids of its first level become text (`series_ids_as_text`). A MultiIndex
    that is not two levels named with text raises `InvalidInputError`.
    Without a profile, a None `date_column` or `series_id_column` is taken
    from the levels, as `profile()` does.

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
        Coerced DataFrame, without a MultiIndex.
    target : str, list
        Resolved target column name(s).
    date_column : str, None
        Resolved date column name.
    series_id_column : str, None
        Resolved series identifier column name.
    """

    if profile is None:
        data_df, target = _resolve_data_and_target(
                              data             = data,
                              target           = target,
                              date_column      = date_column,
                              series_id_column = series_id_column,
                          )
        # Before the levels fill `series_id_column` (see `profile()`).
        _validate_target_format(data_df, target, series_id_column)
        data_df, date_column, series_id_column = _flatten_multiindex(
            data_df, date_column, series_id_column
        )
        return data_df, target, date_column, series_id_column

    dp = profile.data_profile

    # A Series carries its own name, which is the target the profile was
    # built with; `_resolve_data_and_target` already reconciles it with an
    # explicit `target`. For any other input the profile fills the gap.
    if not isinstance(data, pd.Series) and target is None:
        target = dp.target
    # The CSV loader checks the date column of the profile, which the script
    # reads, and reports it when its dates cannot be used.
    # How a file is written belongs to the file, not to the data. The file
    # the profile was built from is read as the profile says, which is how
    # `sep`, `decimal` and `thousands` of `profile()` reach the other
    # methods: detecting it again would undo a `decimal='.'` given against
    # what the file seemed to say. Another file (the same data exported
    # again with another separator) is detected, and read as the profile
    # says only when its dialect cannot be told. So are the dates: their
    # order of day and month is told from them, and the format of the
    # profile decides it only when they read in both.
    dialect = {
        "sep": dp.csv_sep,
        "decimal": dp.csv_decimal,
        "thousands": dp.csv_thousands,
    }
    same_file = (
        dp.data_path != PLACEHOLDER_DATA_PATH
        and isinstance(data, (str, Path))
        and recorded_data_path(data) == dp.data_path
    )
    try:
        data_df, target = _resolve_data_and_target(
                              data             = data,
                              target           = target,
                              date_column      = dp.date_column,
                              series_id_column = dp.series_id_column,
                              date_format      = dp.date_format,
                              **(dialect if same_file else {}),
                          )
    except CsvDialectError:
        if dp.data_path == PLACEHOLDER_DATA_PATH or same_file:
            raise
        data_df, target = _resolve_data_and_target(
                              data             = data,
                              target           = target,
                              date_column      = dp.date_column,
                              series_id_column = dp.series_id_column,
                              date_format      = dp.date_format,
                              **dialect,
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

    # The columns of the profile are already resolved, so the names the
    # levels of a MultiIndex would give are not taken.
    data_df, *_ = _flatten_multiindex(data_df, date_column, series_id_column)

    required = list(target) if isinstance(target, list) else [target]
    required += [col for col in (date_column, series_id_column) if col is not None]
    missing = [col for col in required if col not in data_df.columns]
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


# Whether the plan of the `CVResult` that `compare()` receives is one the
# caller chose. The CLI builds the default plan of the profile only to size
# the strategy of `compare --candidates`, so that plan not being compared is
# nothing to tell its user.
_STRATEGY_PLAN_CHOSEN: ContextVar[bool] = ContextVar(
    "_STRATEGY_PLAN_CHOSEN", default=True
)


@contextmanager
def _strategy_plan_not_chosen() -> Iterator[None]:
    """
    Within the block, take the plan of the `CVResult` of `compare()` as one
    built only to size the strategy: with explicit `candidates`, nothing
    warns, nor says in the explanation, that it was not compared.
    """
    token = _STRATEGY_PLAN_CHOSEN.set(False)
    try:
        yield
    finally:
        _STRATEGY_PLAN_CHOSEN.reset(token)


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
    the file again; it reaches the script through `repr()`. The separator,
    the decimal mark and the thousands separator the file was read with are
    recorded with it (`','`, `'.'` and none for data passed in memory), so
    the script reads the file as it was read. So are its encoding
    (`DataProfile.csv_encoding`, with its note in the warnings when it is
    cp1252) and the format of its dates (`DataProfile.date_format`); for
    data passed in memory, UTF-8 and the format of its own dates, on which
    the script runs (see `frame_date_format`).

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
    dp = profile.data_profile
    sep, decimal, thousands = dp.csv_sep, dp.csv_decimal, dp.csv_thousands
    date_format, encoding = dp.date_format, dp.csv_encoding
    if data_path == PLACEHOLDER_DATA_PATH:
        sep, decimal, thousands = DEFAULT_CSV_SEP, DEFAULT_CSV_DECIMAL, None
        encoding = DEFAULT_CSV_ENCODING
        date_format = frame_date_format(data, dp.date_column, dp.date_format)
    else:
        # Also for the DataFrame of a comparison, whose path is the one of
        # the file it was read from. The notes on how it was read go with
        # them: the profile was built from the DataFrame read.
        read = _dialect_read(data_path)
        if read.sep is not None:
            sep, decimal, thousands, date_format = read[:4]
            encoding = read.encoding
            dp = with_read_notes(dp, read.notes)
    update = {
        "data_path": data_path,
        "csv_sep": sep,
        "csv_decimal": decimal,
        "csv_thousands": thousands,
        "csv_encoding": encoding,
        "date_format": date_format,
    }
    if dp is profile.data_profile and all(
        getattr(dp, name) == value for name, value in update.items()
    ):
        return profile
    return profile.model_copy(update={"data_profile": dp.model_copy(update=update)})


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

    if plan.task_type not in ML_TASK_TYPES:
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


def window_without_refit(
    fixed_train_size: bool | None,
    refit: object,
    forecaster: str,
) -> bool:
    """
    Whether a `fixed_train_size` is passed for a strategy that trains the
    forecaster once, where it has no effect.

    Parameters
    ----------
    fixed_train_size : bool, None
        Value passed by the caller; None when not passed.
    refit : bool, int, None
        `refit` of the strategy; None counts as False, its default.
    forecaster : str
        Forecaster of the plan. `ForecasterStats`, which skforecast refits
        in every fold, is never trained once.

    Returns
    -------
    without_refit : bool
        True when `fixed_train_size` is passed and the forecaster is
        trained once.
    """
    if fixed_train_size is None or forecaster == "ForecasterStats":
        return False
    refits = refit is True or (
        isinstance(refit, numbers.Integral)
        and not isinstance(refit, bool)
        and refit > 0
    )
    return not refits


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
    if window_without_refit(fixed_train_size, refit, forecaster):
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


def stats_skip_folds_issue(forecaster: str, skip_folds: object) -> str | None:
    """
    Say why a `ForecasterStats` plan cannot be backtested with a strategy
    that skips folds, or return None when it can.

    skforecast refits `ForecasterStats` in every fold and rejects any
    `skip_folds` other than None for it, an empty list included.

    Parameters
    ----------
    forecaster : str
        Forecaster of the plan.
    skip_folds : int, list, None
        `skip_folds` of the strategy.

    Returns
    -------
    issue : str, None
        What fails, or None when the plan is not `ForecasterStats` or the
        strategy runs every fold.
    """
    if forecaster != "ForecasterStats" or skip_folds is None:
        return None

    return (
        f"`skip_folds={skip_folds!r}` is not allowed for ForecasterStats: "
        f"skforecast refits it in every fold and rejects any `skip_folds`, "
        f"an empty list included"
    )


# Ways to run fewer folds without `skip_folds`, named by the errors about
# `ForecasterStats`.
STATS_FEWER_FOLDS = (
    "For fewer folds, use a later `initial_train_size` or a larger "
    "`fold_stride`."
)


def _check_stats_skip_folds(plan: ForecastPlan, cv: TimeSeriesFold) -> None:
    """
    Raise when a `ForecasterStats` plan is backtested with a strategy that
    skips folds (see `stats_skip_folds_issue`).

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
    issue = stats_skip_folds_issue(plan.forecaster, cv.skip_folds)
    if issue is not None:
        raise InvalidInputError(
            f"{issue}. Use a strategy without `skip_folds`, or another "
            f"forecaster.",
            field = "cv",
            hint  = STATS_FEWER_FOLDS,
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


def _cv_in_time_zone(
    cv: TimeSeriesFold,
    data: pd.DataFrame | None,
    data_profile: DataProfile,
) -> TimeSeriesFold:
    """
    Return the strategy the backtesting script runs, with a date
    `initial_train_size` turned into its number of observations when the
    dates of the data have a time zone.

    `create_cv()` writes the date without time zone (in the local time of
    data that start at midnight), and skforecast compares it with the index
    of the data, which
    fails for dates with a time zone ("Cannot compare tz-naive and tz-aware
    timestamps"). The date is read as the local time of the data, as the
    profile placed it, and the script gets the observations of the data
    from the first date to it at the frequency of the profile, which is the
    training window skforecast takes from that date. Writing the date with
    a UTC offset instead would not do: '+02:00' does not match a named zone
    such as 'Europe/Madrid'. The strategy passed is not changed:
    `cv_config` and the explanation describe it as given.

    The strategy is returned as it is without data (`backtest_code()`
    rendered from a profile alone: the count needs the dates), for a date
    that has its own time zone, which skforecast places on the dates of the
    data, and for a date that does not parse or is outside the dates of the
    data, which skforecast reports as before.

    Parameters
    ----------
    cv : TimeSeriesFold
        Strategy of the backtest.
    data : pandas DataFrame, None
        Data of the backtest; None when the script is rendered without data.
    data_profile : DataProfile
        Profile of the data: date column and frequency.

    Returns
    -------
    cv : TimeSeriesFold
        `cv`, or a copy with the number of observations of its date.
    """
    initial_train_size = cv.initial_train_size
    if (
        data is None
        or data_profile.frequency is None
        or not isinstance(initial_train_size, (str, pd.Timestamp))
    ):
        return cv
    dates = row_dates(data, data_profile.date_column, data_profile.date_format)
    if getattr(dates, "tz", None) is None:
        return cv
    try:
        date = pd.Timestamp(initial_train_size)
    except (ValueError, TypeError):
        return cv
    if date.tz is not None:
        return cv
    # Counted on the local times of the grid, so a date in the hour that a
    # daylight saving change skips or repeats is placed as the profile did.
    grid = pd.date_range(
        start = dates.min(),
        end   = dates.max(),
        freq  = data_profile.frequency,
    ).tz_localize(None)
    if date < grid[0] or date > grid[-1]:
        return cv
    localized = copy.deepcopy(cv)
    localized.set_params({"initial_train_size": int((grid <= date).sum())})

    return localized


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
    front. When they all fall on days of the week on which the target never
    has a value (a shop closed on Sundays), the message names those days and
    says that a business closed on them can fill them with 0, after asking
    the user. Multi-series backtesting drops them per series and is not
    checked. `end_train` and a date of the strategy without time zone are
    read in the time zone of the dates; a date of the strategy that
    skforecast cannot place on them (a date with a time zone on an index
    without one, a text that is not a date) skips the check, and the
    validation of the strategy reports it.

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
        index = row_dates(data, data_profile.date_column, data_profile.date_format)
    else:
        index = data.index
    if target not in data:
        return
    y = pd.Series(data[target].to_numpy(), index=index).sort_index()
    if y.index.has_duplicates:
        return
    with_value = y.index[y.notna().to_numpy()]
    if data_profile.frequency is not None and isinstance(y.index, pd.DatetimeIndex):
        y = y.asfreq(data_profile.frequency)

    if cv is not None:
        original_verbose = cv.verbose
        cv.verbose = False
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                folds = cv.split(X=y, as_pandas=True)
        except (TypeError, ValueError):
            # A strategy skforecast cannot split on these dates (a date with
            # a time zone on an index without one, a text that is not a
            # date): its validation reports it with its own error.
            return
        finally:
            cv.verbose = original_verbose
        bounds = [
            (int(start), int(end))
            for start, end in zip(
                folds["test_start_with_gap"], folds["test_end_with_gap"]
            )
        ]
        positions = sorted({
            position for start, end in bounds for position in range(start, end)
        })
        evaluated = y.iloc[positions]
        # The folds that hold a missing value, numbered from 1 in the order
        # the backtest runs them.
        absent = np.flatnonzero(y.isna().to_numpy())
        with_missing = [
            number for number, (start, end) in enumerate(bounds, start=1)
            if ((absent >= start) & (absent < end)).any()
        ]
        where = (
            f"in {_test_folds_phrase(with_missing, len(bounds))}"
            if with_missing else ""
        )
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
    closed = (
        closed_weekdays(with_value, data_profile.frequency)
        if isinstance(missing, pd.DatetimeIndex) else []
    )
    if closed and np.isin(missing.dayofweek, closed).all():
        days = weekday_names(sorted(set(missing.dayofweek)))
        raise DataContentError(
            f"The target has {len(missing)} missing value(s) {where} "
            f"({shown}), counting the missing timestamps that asfreq() "
            f"restores: all of them on {days}, when the target never has a "
            f"value. skforecast cannot compute the metrics on them, whatever "
            f"the estimator. {closed_days_remedy(days)}; otherwise, impute the "
            f"target, or evaluate on dates without missing values.",
            field = "data",
        )
    raise DataContentError(
        f"The target has {len(missing)} missing value(s) {where} ({shown}), "
        f"counting the missing timestamps that asfreq() restores. skforecast "
        f"cannot compute the metrics on them, whatever the estimator. Impute "
        f"the target, or evaluate on dates without missing values.",
        field = "data",
    )


def _test_folds_phrase(numbers: list[int], n_folds: int) -> str:
    """
    Name test folds by their numbers, from 1: `'test fold 4 of 6'`,
    `'test folds 2 and 4 of 6'`, up to 5 numbers and then `'and N more'`,
    or `'all 6 test folds'`.
    """
    if len(numbers) == n_folds > 1:
        return f"all {n_folds} test folds"
    shown = [str(number) for number in numbers[:5]]
    if len(numbers) > 5:
        shown.append(f"{len(numbers) - 5} more")
    if len(shown) == 1:
        return f"test fold {shown[0]} of {n_folds}"

    return f"test folds {', '.join(shown[:-1])} and {shown[-1]} of {n_folds}"


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
    generated scripts pass `suppress_warnings=True`. `backtest()` refuses
    such a run until it is confirmed (`check_backtest_cost`); the
    `create_cv` tool of the MCP server warns with this text when the
    strategy is built, while it can still change.

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


def long_inference_message(
    inference_windows: int,
    n_series: int,
    n_folds: int,
    n_candidates: int = 1,
) -> str:
    """
    Describe the cost of a backtest of a foundation model in inference
    windows.

    Parameters
    ----------
    inference_windows : int
        Number of inference windows of the backtest, or of all the
        candidates of a comparison.
    n_series : int
        Number of series of the data.
    n_folds : int
        Number of folds of the strategy.
    n_candidates : int, default 1
        Number of `ForecasterFoundation` candidates of a comparison that
        the windows add up.

    Returns
    -------
    message : str
        Sentence with the number of windows, broken down into series, folds
        and candidates. The number is an upper bound ("up to"): a series
        without data in a fold is not forecast in it.
    """

    candidates = f" x {n_candidates} candidates" if n_candidates > 1 else ""

    return (
        f"ForecasterFoundation will forecast up to {inference_windows} "
        f"inference windows ({n_series} series x {n_folds} folds{candidates})"
    )


def warn_long_inference(
    inference_windows: int,
    n_series: int,
    n_folds: int,
    n_candidates: int = 1,
) -> None:
    """
    Warn before a backtest of a foundation model that forecasts many
    windows.

    A foundation model is not trained, so its estimator fits are 0 and
    `warn_long_training` never fires for it; its time is the inference of
    each series in each fold. Above `LONG_INFERENCE_WINDOWS` windows the
    backtest can take a minute or more on a CPU with few cores (seconds on
    a GPU, and a larger model takes several times longer per window).
    `backtest()` refuses such a run until it is confirmed
    (`check_backtest_cost`); the `create_cv` tool of the MCP server warns
    with this text when the strategy is built.

    Parameters
    ----------
    inference_windows : int
        Number of inference windows of the backtest, see
        `count_inference_windows`.
    n_series : int
        Number of series of the data.
    n_folds : int
        Number of folds of the strategy.
    n_candidates : int, default 1
        Number of `ForecasterFoundation` candidates of a comparison that
        `inference_windows` adds up.

    Returns
    -------
    None
    """

    if inference_windows <= LONG_INFERENCE_WINDOWS:
        return

    message = long_inference_message(
        inference_windows, n_series, n_folds, n_candidates
    )
    warnings.warn(
        f"{message}, "
        f"more than {LONG_INFERENCE_WINDOWS}. This can take minutes on a CPU. "
        f"If not feasible, use a cross-validation strategy with fewer folds "
        f"(a later `initial_train_size` or a larger `fold_stride`) or "
        f"forecast fewer series.",
        LongTrainingWarning,
        stacklevel=3,
    )


def cost_remedies(
    forecasters: Iterable[str],
    n_fits: int,
    steps: int,
    skip_folds: bool = True,
    false: str = "False",
) -> list[str]:
    """
    Name the changes that lower the cost of a backtest or a comparison.

    Only what lowers the cost of the forecasters given is named: `refit`
    changes nothing for `ForecasterStats` (skforecast refits it in every
    fold whatever it says) nor for `ForecasterFoundation` (never trained),
    and nothing for the others either once they train once (`n_fits` 1);
    fewer folds lower every cost but that of a forecaster trained once. A
    shorter horizon is named only for a direct forecaster trained once,
    since nothing else lowers its cost then, and not next to
    `ForecasterStats` or `ForecasterFoundation`: for them it means more
    folds of the default `fold_stride`, a higher cost. The order is fixed,
    so the text is the same for the same input.

    Parameters
    ----------
    forecasters : iterable of str
        Names of the forecasters whose cost is above the threshold, or adds
        up to a total above it.
    n_fits : int
        Number of folds in which a forecaster is trained under the
        strategy, see `count_cv_fits`.
    steps : int
        Forecast horizon of each fold.
    skip_folds : bool, default True
        Whether `skip_folds` can be named among the ways to have fewer
        folds: False when `ForecasterStats` runs on the strategy, which
        rejects it. Never named when `forecasters` has `ForecasterStats`.
    false : str, default 'False'
        How the text writes `refit=False`: `'false'` for the JSON arguments
        of the MCP server.

    Returns
    -------
    remedies : list of str
        One phrase per change, such as `'an integer `refit` (retrain every n
        folds)'`. Empty when nothing lowers the cost.
    """

    forecasters = set(forecasters)
    untrained = {"ForecasterStats", "ForecasterFoundation", "ForecasterEquivalentDate"}
    refits = bool(forecasters - untrained) and n_fits > 1
    remedies = []
    if refits:
        remedies.append("an integer `refit` (retrain every n folds)")
    if refits or forecasters & {"ForecasterStats", "ForecasterFoundation"}:
        if skip_folds and "ForecasterStats" not in forecasters:
            ways = (
                "a later `initial_train_size`, a larger `fold_stride` or "
                "`skip_folds`"
            )
        else:
            ways = "a later `initial_train_size` or a larger `fold_stride`"
        remedies.append(f"fewer folds ({ways})")
    if refits:
        remedies.append(f"`refit={false}` (train once)")
    if (
        n_fits <= 1
        and steps > 1
        and forecasters & DIRECT_FORECASTERS
        and not forecasters & {"ForecasterStats", "ForecasterFoundation"}
    ):
        remedies.append(
            "a shorter horizon (a direct forecaster fits one estimator per step)"
        )
    if "ForecasterFoundation" in forecasters:
        remedies.append("fewer series")

    return remedies


def join_remedies(remedies: list[str]) -> str:
    """
    Join the phrases of `cost_remedies` as `'a, b or c'`.

    Parameters
    ----------
    remedies : list of str
        Phrases returned by `cost_remedies`.

    Returns
    -------
    text : str
        The phrases joined, the last one with "or".
    """

    if len(remedies) <= 1:
        return "".join(remedies)

    return f"{', '.join(remedies[:-1])} or {remedies[-1]}"


def long_comparison_message(cost: ComparisonCost, steps: int) -> str:
    """
    Describe the cost of a comparison in estimator fits: the total and
    what each candidate adds to it.

    Parameters
    ----------
    cost : ComparisonCost
        Cost of the comparison, see `count_comparison_cost`.
    steps : int
        Forecast horizon of each fold.

    Returns
    -------
    message : str
        Sentence with the total, each candidate with its fits and the
        direct ones broken down into trainings and estimators.
    """

    # A direct forecaster fits one estimator per step, which is what makes
    # it costly: its share says so.
    shown = ", ".join(
        f"'{name}': {candidate.estimator_fits}"
        + (
            f" ({candidate.n_fits} trainings x {steps} estimators)"
            if candidate.forecaster in DIRECT_FORECASTERS else ""
        )
        for name, candidate in cost.candidates.items()
    )

    return f"The comparison will fit {cost.estimator_fits} estimators in all ({shown})"


def comparison_remedies(
    cost: ComparisonCost,
    n_fits: int,
    steps: int,
    false: str = "False",
) -> list[str]:
    """
    Name the changes of the strategy that lower the cost of a comparison
    above the thresholds of an expensive run.

    They are those of `cost_remedies` for the forecasters whose cost puts
    the comparison above them: the candidates that fit estimators when the
    fits are above `LONG_TRAINING_FITS`, and `ForecasterFoundation` when
    the inference windows are above `LONG_INFERENCE_WINDOWS`.

    Parameters
    ----------
    cost : ComparisonCost
        Cost of the comparison, see `count_comparison_cost`.
    n_fits : int
        Number of folds in which a forecaster is trained under the shared
        strategy, see `count_cv_fits`.
    steps : int
        Forecast horizon of each fold.
    false : str, default 'False'
        How the text writes `refit=False`, see `cost_remedies`.

    Returns
    -------
    remedies : list of str
        One phrase per change, see `cost_remedies`.
    """

    candidates = cost.candidates.values()
    costly = set()
    if cost.estimator_fits > LONG_TRAINING_FITS:
        costly |= {c.forecaster for c in candidates if c.estimator_fits}
    if cost.inference_windows > LONG_INFERENCE_WINDOWS:
        costly.add("ForecasterFoundation")

    return cost_remedies(
        forecasters = costly,
        n_fits      = n_fits,
        steps       = steps,
        skip_folds  = all(c.forecaster != "ForecasterStats" for c in candidates),
        false       = false,
    )


def expensive_run_figure(estimator_fits: int, inference_windows: int) -> int | None:
    """
    Number that confirms a run above the thresholds of an expensive run.

    Parameters
    ----------
    estimator_fits : int
        Estimator fits of the run (all its candidates, for a comparison).
    inference_windows : int
        Inference windows of the run (all its candidates, for a
        comparison).

    Returns
    -------
    figure : int, None
        `estimator_fits` when above `LONG_TRAINING_FITS`, else
        `inference_windows` when above `LONG_INFERENCE_WINDOWS` (the cost
        of a foundation model, which fits no estimator), else None: the
        run needs no confirmation.
    """

    if estimator_fits > LONG_TRAINING_FITS:
        return estimator_fits
    if inference_windows > LONG_INFERENCE_WINDOWS:
        return inference_windows

    return None


def changed_since(run: Literal["backtest", "comparison"]) -> str:
    """
    Name what changes the cost of a run, for the message of a confirmation
    given for another cost.

    Parameters
    ----------
    run : {'backtest', 'comparison'}
        What runs.

    Returns
    -------
    text : str
        `'the strategy or the plan'` of a backtest, `'the strategy or the
        candidates'` of a comparison.
    """

    return "the strategy or the candidates" if run == "comparison" else (
        "the strategy or the plan"
    )


def check_cost_confirmed(
    confirm_cost: bool | int,
    run: Literal["backtest", "comparison"],
    cost: dict[str, int],
    description: str,
    remedies: str,
    comparison_cost: ComparisonCost | None = None,
) -> None:
    """
    Stop a run above the thresholds of an expensive run that `confirm_cost`
    does not confirm, before anything runs.

    A warning arrives once the run has started and does not stop it, so a
    run above the thresholds needs a confirmation: `True`, or the figure of
    its cost (see `expensive_run_figure`), which no longer confirms it once
    the strategy, the plan or the candidates change its cost. Below the
    thresholds `confirm_cost` is not read.

    Parameters
    ----------
    confirm_cost : bool, int
        Confirmation passed by the caller, see `validate_confirm_cost`.
    run : {'backtest', 'comparison'}
        What runs, as the message names it.
    cost : dict
        `n_folds`, `n_fits`, `estimator_fits` and `inference_windows` of
        the run.
    description : str
        Sentences stating the cost and what makes it, with a final period.
    remedies : str
        What lowers the cost, completing "If not feasible, " (such as
        `'use `refit=False` (train once)'`). Empty when nothing does.
    comparison_cost : ComparisonCost, default None
        Cost of each candidate of a comparison.

    Returns
    -------
    None

    Raises
    ------
    CostNotConfirmedError
        If the run is above the thresholds and `confirm_cost` is neither
        True nor the figure of its cost.
    """

    figure = expensive_run_figure(cost["estimator_fits"], cost["inference_windows"])
    if figure is None or confirm_cost is True:
        return
    given = not isinstance(confirm_cost, bool)
    if given and confirm_cost == figure:
        return

    message = (
        f"This {run} is above the threshold of an expensive run "
        f"({LONG_TRAINING_FITS} estimator fits or {LONG_INFERENCE_WINDOWS} "
        f"inference windows), so it needs a confirmation and nothing ran. "
        f"{description} It can take substantial amounts of time."
    )
    if remedies:
        message += f" If not feasible, {remedies}."
    if given:
        message += (
            f" `confirm_cost={confirm_cost}` does not confirm it: the figure of "
            f"this cost is {figure}, so {changed_since(run)} changed since "
            f"that number was given."
        )
    raise CostNotConfirmedError(
        message,
        figure          = figure,
        cost            = cost,
        description     = description,
        comparison_cost = comparison_cost,
        hint            = "Pass `confirm_cost=True` to run it as it is.",
    )


def check_backtest_cost(
    confirm_cost: bool | int,
    cv_config: dict,
    forecaster: str,
    steps: int,
    n_series: int,
) -> None:
    """
    Stop a backtest above the thresholds of an expensive run that
    `confirm_cost` does not confirm, see `check_cost_confirmed`.

    Parameters
    ----------
    confirm_cost : bool, int
        Confirmation passed to `backtest()`.
    cv_config : dict
        Resolved strategy of the backtest, with `n_folds` and `n_fits` as
        the forecaster runs it (see `resolve_cv_config`).
    forecaster : str
        Name of the skforecast forecaster class.
    steps : int
        Forecast horizon of each fold.
    n_series : int
        Number of series of the data.

    Returns
    -------
    None
    """

    n_fits, n_folds = cv_config["n_fits"], cv_config["n_folds"]
    cost = {
        "n_folds": n_folds,
        "n_fits": n_fits,
        "estimator_fits": count_estimator_fits(
                              n_fits     = n_fits,
                              forecaster = forecaster,
                              steps      = steps,
                          ),
        # A foundation model fits nothing: its cost is the inference of
        # each series in each fold.
        "inference_windows": count_inference_windows(
                                 n_folds    = n_folds,
                                 n_series   = n_series,
                                 forecaster = forecaster,
                             ),
    }
    if expensive_run_figure(cost["estimator_fits"], cost["inference_windows"]) is None:
        return
    if cost["estimator_fits"] > LONG_TRAINING_FITS:
        description = long_training_message(
            cost["estimator_fits"], n_fits, forecaster, steps
        )
    else:
        description = long_inference_message(
            cost["inference_windows"], n_series, n_folds
        )
    remedies = cost_remedies(forecasters=[forecaster], n_fits=n_fits, steps=steps)
    check_cost_confirmed(
        confirm_cost = confirm_cost,
        run          = "backtest",
        cost         = cost,
        description  = f"{description}.",
        remedies     = f"use {join_remedies(remedies)}" if remedies else "",
    )


def check_comparison_cost(
    confirm_cost: bool | int,
    cost: ComparisonCost,
    n_fits: int,
    steps: int,
    n_series: int,
    not_counted: list[str] | None = None,
) -> None:
    """
    Stop a comparison above the thresholds of an expensive run that
    `confirm_cost` does not confirm, see `check_cost_confirmed`.

    The thresholds apply to the total of the comparison, not to each
    candidate: candidates that are cheap one by one can add up to an
    expensive run. The message states the total and what each candidate
    adds to it.

    Parameters
    ----------
    confirm_cost : bool, int
        Confirmation passed to `compare()`.
    cost : ComparisonCost
        Cost of the comparison, see `count_comparison_cost`.
    n_fits : int
        Number of folds in which a forecaster is trained under the shared
        strategy, see `count_cv_fits`.
    steps : int
        Forecast horizon of each fold.
    n_series : int
        Number of series of the data.
    not_counted : list of str, default None
        Names of the candidates whose plan cannot be built, which run
        nothing and are not in `cost`.

    Returns
    -------
    None
    """

    if expensive_run_figure(cost.estimator_fits, cost.inference_windows) is None:
        return
    parts = []
    if cost.estimator_fits > LONG_TRAINING_FITS:
        parts.append(long_comparison_message(cost, steps))
    if cost.inference_windows > LONG_INFERENCE_WINDOWS:
        parts.append(
            long_inference_message(
                inference_windows = cost.inference_windows,
                n_series          = n_series,
                n_folds           = cost.n_folds,
                n_candidates      = sum(
                                        candidate.inference_windows > 0
                                        for candidate in cost.candidates.values()
                                    ),
            )
        )
    description = f"{' and '.join(parts)}."
    if not_counted:
        names = [f"'{name}'" for name in not_counted]
        if len(names) == 1:
            description += (
                f" {names[0]} is not counted: its plan cannot be built, so it "
                f"runs nothing."
            )
        else:
            description += (
                f" {', '.join(names[:-1])} and {names[-1]} are not counted: "
                f"their plans cannot be built, so they run nothing."
            )
    remedies = comparison_remedies(cost, n_fits=n_fits, steps=steps)
    check_cost_confirmed(
        confirm_cost    = confirm_cost,
        run             = "comparison",
        cost            = {
                              "n_folds": cost.n_folds,
                              "n_fits": cost.n_fits,
                              "estimator_fits": cost.estimator_fits,
                              "inference_windows": cost.inference_windows,
                          },
        description     = description,
        remedies        = (
                              f"compare fewer candidates or use "
                              f"{join_remedies(remedies)}"
                              if remedies else "compare fewer candidates"
                          ),
        comparison_cost = cost,
    )
