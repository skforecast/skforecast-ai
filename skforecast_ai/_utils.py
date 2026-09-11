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
from skforecast.model_selection import TimeSeriesFold

from ._constants import ALLOWED_WINDOW_STATS, MAX_FEATURE_FRACTION
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


def _validate_lags(lags: int | list[int] | None) -> None:
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

    Returns
    -------
    None
    """
    if lags is None:
        return

    # `bool` is a subclass of `int`; reject it explicitly.
    if isinstance(lags, bool) or not isinstance(lags, (int, list)):
        raise ValueError(
            f"`lags` must be an int or a list of ints, got {lags!r}."
        )

    if isinstance(lags, int):
        if lags < 1:
            raise ValueError(
                f"`lags` must be positive integers (>= 1), got {lags!r}."
            )
        return

    if not lags:
        raise ValueError(
            "`lags` must not be an empty list; pass None to keep the "
            "deterministic lag selection."
        )

    if any(isinstance(lag, bool) or not isinstance(lag, int) for lag in lags):
        raise ValueError(f"`lags` must contain ints only, got {lags!r}.")

    if any(lag < 1 for lag in lags):
        raise ValueError(
            f"`lags` must be positive integers (>= 1), got {lags!r}."
        )

    if len(set(lags)) != len(lags):
        raise ValueError(f"`lags` must not contain duplicates, got {lags!r}.")


def _validate_window_features(window_features: list[dict] | None) -> None:
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

    Returns
    -------
    None
    """
    if window_features is None:
        return

    if not isinstance(window_features, list):
        raise ValueError(
            f"`window_features` must be a list of dicts, got "
            f"{type(window_features).__name__}."
        )

    for i, wf in enumerate(window_features):
        if not isinstance(wf, dict):
            raise ValueError(
                f"`window_features[{i}]` must be a dict with keys 'stats' "
                f"and 'window_size', got {type(wf).__name__}."
            )

        missing = {"stats", "window_size"} - wf.keys()
        if missing:
            raise ValueError(
                f"`window_features[{i}]` is missing required key(s): "
                f"{sorted(missing)}. Each entry must have 'stats' and "
                f"'window_size'."
            )

        stats = wf["stats"]
        if not isinstance(stats, list) or not stats:
            raise ValueError(
                f"`window_features[{i}]['stats']` must be a non-empty list "
                f"of statistic names, got {stats!r}."
            )
        invalid_stats = [s for s in stats if s not in ALLOWED_WINDOW_STATS]
        if invalid_stats:
            raise ValueError(
                f"`window_features[{i}]['stats']` contains unsupported "
                f"statistic(s): {invalid_stats}. Allowed statistics are: "
                f"{sorted(ALLOWED_WINDOW_STATS)}."
            )

        window_size = wf["window_size"]
        # `bool` is a subclass of `int`; reject it explicitly.
        if not isinstance(window_size, int) or isinstance(window_size, bool):
            raise ValueError(
                f"`window_features[{i}]['window_size']` must be a scalar "
                f"int, got {window_size!r}. Within a single entry 'stats' "
                f"may be a list but 'window_size' must be a scalar applied "
                f"to all of them; add one entry per window size to use "
                f"several sizes."
            )
        if window_size < 1:
            raise ValueError(
                f"`window_features[{i}]['window_size']` must be a positive "
                f"int, got {window_size}."
            )

    pairs = [
        (stat, wf["window_size"]) for wf in window_features for stat in wf["stats"]
    ]
    duplicates = sorted({pair for pair in pairs if pairs.count(pair) > 1})
    if duplicates:
        raise ValueError(
            f"`window_features` contains duplicate (stat, window_size) "
            f"pairs: {duplicates}. Merge the entries or change the window "
            f"size."
        )


def _validate_task_input(data_profile: DataProfile, task_type: str) -> None:
    """
    Validate that the input shape is compatible with the task type.

    Single-series tasks (`single_series`, `statistical`, `foundation`)
    accept exactly one series. The `multivariate` task requires all
    series to share the same length.

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

    if task_type in ("single_series", "statistical", "foundation") and n_series > 1:
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
        produce their own intervals, `'bootstrapping'` otherwise, and
        None when `interval` is None.
    """
    if interval is None:
        return None
    if task_type in {"statistical", "foundation"}:
        return "native"
    return "bootstrapping"


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
    """
    if plan.interval == interval:
        return plan
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

    # Prediction mode.
    if require_exog and has_exog and exog is None:
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
