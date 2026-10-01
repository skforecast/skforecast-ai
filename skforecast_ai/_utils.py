################################################################################
#                                  Utils                                       #
#                                                                              #
# Shared internal utilities for skforecast_ai                                  #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import re
import warnings
from pathlib import Path
import pandas as pd
from pydantic import BaseModel
from skforecast.exceptions import LongTrainingWarning
from skforecast.model_selection import TimeSeriesFold

from ._constants import (
    DIRECT_FORECASTERS,
    LONG_TRAINING_FITS,
    MAX_FEATURE_FRACTION,
)
from ._foundation import resolve_foundation_model, validate_foundation_interval
# `_validate_lags` and `_validate_window_features` live in `_validation`,
# which the plan schema imports; they are re-exported here for the callers
# that import them from `_utils`.
from ._validation import (
    _validate_lags as _validate_lags,
    _validate_window_features as _validate_window_features,
    validate_interval,
)
from .profiling.data_profile import _try_parse_first_date_column
from .schemas import CVResult, DataProfile, ForecastingProfile, ForecastPlan

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

    Returns
    -------
    None
    """
    max_span = _max_window_size(lags, window_features)
    max_allowed = int(span_index_length * MAX_FEATURE_FRACTION)
    if max_span > max_allowed:
        raise ValueError(
            f"Explicit lags/window_features span up to {max_span} "
            f"observations, exceeding the maximum of {max_allowed} "
            f"({int(MAX_FEATURE_FRACTION * 100)}% of "
            f"{span_index_length} observations). "
            f"Reduce the largest lag or window size."
        )


def _validate_task_input(data_profile: DataProfile, task_type: str) -> None:
    """
    Validate that the input shape is compatible with the task type.

    Single-series tasks (`single_series`, `statistical`, `baseline`) accept
    exactly one series. The `multivariate` task requires all series to share
    the same length. `foundation` takes one or several series.

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
        raise ValueError(
            f"Task type '{task_type}' supports a single series only, but the "
            f"input contains {n_series} series ({list(series_lengths)}). "
            f"Use a multi-series forecaster (e.g. "
            f"'ForecasterRecursiveMultiSeries') or provide a single series."
        )

    if task_type == "multivariate":
        lengths = {info.length for info in series_lengths.values()}
        if len(lengths) > 1:
            detail = {
                name: info.length for name, info in series_lengths.items()
            }
            raise ValueError(
                f"Task type 'multivariate' (ForecasterDirectMultiVariate) "
                f"requires all series to have the same length, but got "
                f"{detail}. Align the series to a common index or use "
                f"'ForecasterRecursiveMultiSeries'."
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
        )
        if value is not None and value != plan_value
    ]
    if conflicts:
        raise ValueError(
            f"A pre-built `plan` was provided and the following argument(s) "
            f"differ from what it holds: {conflicts}. Omit them to use the "
            f"plan as is, or refine the plan with `refine_plan()` first."
        )


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
    return plan.model_copy(
        update={
            "interval": interval,
            "interval_method": interval_method,
            "explanation": explanation,
        }
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
            raise ValueError(
                "`exog` is only used for future prediction (`test_size=None`). "
                "In evaluation mode the test-set exogenous values are taken "
                "from the train/test split, so `exog` must not be provided."
            )
        return

    if uses_exog is None:
        uses_exog = has_exog

    # Prediction mode.
    if require_exog and uses_exog and exog is None:
        raise ValueError(
            "`exog` is required for future prediction because the data "
            "contains exogenous variables. Provide future exogenous "
            "values covering the forecast horizon, or pass `test_size` "
            "to run in evaluation mode instead."
        )
    if not has_exog and exog is not None:
        raise ValueError(
            "`exog` was provided but the data contains no exogenous "
            "variables. Remove `exog` or add exogenous columns to the "
            "data."
        )
    if has_exog and not uses_exog and exog is not None:
        raise ValueError(
            "`exog` was provided but the plan does not use exogenous "
            "variables (`plan.use_exog` is False). Remove `exog`."
        )
    if exog is not None and len(exog) < steps:
        raise ValueError(
            f"`exog` must cover the forecast horizon: {steps} rows are "
            f"required but only {len(exog)} were provided."
        )


def _resolve_data_and_target(
    data: pd.Series | pd.DataFrame | str | Path,
    target: str | list[str] | None,
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

    Returns
    -------
    data : pandas DataFrame
        Coerced DataFrame.
    target : str, list
        Resolved target column name(s).

    Raises
    ------
    ValueError
        When `data` is a Series and `target` is provided but does not
        match the Series name, or when `data` is not a Series and
        `target` is None.
    FileNotFoundError
        When `data` is a path or URL that cannot be read.
    """
    if isinstance(data, pd.Series):
        name = data.name
        if target is not None and target != name:
            raise ValueError(
                f"When `data` is a pandas Series and `target` is provided, "
                f"`target` must match the Series name. Got target={target!r} "
                f"and series.name={name!r}. Omit `target` to use the Series "
                f"name, or rename the Series."
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
        raise ValueError(
            "`target` is required when `data` is not a pandas Series."
        )

    if isinstance(data, (str, Path)):
        data_str = str(data)
        if data_str.startswith(("http://", "https://")):
            try:
                df = pd.read_csv(data_str)
            except Exception as e:
                raise FileNotFoundError(
                    f"Could not read CSV from URL: '{data_str}'. {e}"
                ) from e
            return _try_parse_first_date_column(df), target
        path = Path(data_str)
        if not path.is_file():
            raise FileNotFoundError(
                f"CSV file not found: '{path}'. Please provide a valid file path."
            )
        df = pd.read_csv(path)
        return _try_parse_first_date_column(df), target

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
        raise ValueError(
            f"`{name}` {value!r} does not match the value recorded in "
            f"`profile` ({recorded!r}). Pass the value the profile was built "
            f"with, or omit it."
        )
    return value


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
        data_df, target = _resolve_data_and_target(data, target)
        return data_df, target, date_column, series_id_column

    dp = profile.data_profile

    # A Series carries its own name, which is the target the profile was
    # built with; `_resolve_data_and_target` already reconciles it with an
    # explicit `target`. For any other input the profile fills the gap.
    if not isinstance(data, pd.Series) and target is None:
        target = dp.target
    data_df, target = _resolve_data_and_target(data, target)
    if target != dp.target:
        raise ValueError(
            f"`target` {target!r} does not match the target recorded in "
            f"`profile` ({dp.target!r}). Pass the target the profile was "
            f"built with, or omit it."
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
        raise ValueError(
            f"`data` does not contain the column(s) {missing} recorded in "
            f"`profile`. Available columns: {list(data_df.columns)}. Pass the "
            f"dataset the profile was built from."
        )

    return data_df, target, date_column, series_id_column


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

    return cv.cv if isinstance(cv, CVResult) else cv


def _check_evaluated_target(
    data: pd.DataFrame,
    data_profile: DataProfile,
    cv: TimeSeriesFold | None = None,
    end_train: str | None = None,
    steps: int | None = None,
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
    checked.

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

    Returns
    -------
    None

    Raises
    ------
    ValueError
        If a checked date has a missing target value.
    """

    if data_profile.n_series != 1 or not isinstance(data_profile.target, str):
        return
    if not data_profile.missing_target and not data_profile.has_gaps:
        return

    # Rebuild the target as the generated script does: datetime index,
    # sorted, and on its regular grid when the frequency is known.
    if data_profile.date_column is not None and data_profile.date_column in data:
        index = pd.to_datetime(data[data_profile.date_column])
    else:
        index = data.index
    y = pd.Series(data[data_profile.target].to_numpy(), index=index).sort_index()
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
        evaluated = y.loc[y.index > pd.Timestamp(end_train)].iloc[:steps]
        where = "in the test split"
    else:
        return

    missing = evaluated.index[evaluated.isna()]
    if len(missing) == 0:
        return

    shown = ", ".join(str(date) for date in missing[:5])
    if len(missing) > 5:
        shown += f" and {len(missing) - 5} more"
    raise ValueError(
        f"The target has {len(missing)} missing value(s) {where} ({shown}), "
        f"counting the missing timestamps that asfreq() restores. skforecast "
        f"cannot compute the metrics on them, whatever the estimator. Impute "
        f"the target, or evaluate on dates without missing values."
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

    warnings.warn(
        f"{long_training_message(estimator_fits, n_fits, forecaster, steps)}. "
        f"This can take substantial amounts of time. If not feasible, use a "
        f"cross-validation strategy with `refit=False` (train once) or an "
        f"integer `refit` (retrain every n folds).",
        LongTrainingWarning,
        stacklevel=3,
    )
