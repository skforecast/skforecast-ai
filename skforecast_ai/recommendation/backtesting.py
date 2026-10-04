################################################################################
#                       Recommendations: backtesting                           #
#                                                                              #
# Cross-validation strategy recommendation for backtesting                     #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import copy
import re
import warnings
import pandas as pd
from skforecast.exceptions import IgnoredArgumentWarning
from skforecast.model_selection import TimeSeriesFold
from .._constants import AUTOREG_FORECASTERS, DIRECT_FORECASTERS, ML_TASK_TYPES
from ..schemas import DataProfile, ForecastingProfile, ForecastPlan
from ..exceptions import InvalidInputError, InvalidInputTypeError


def derive_cv_defaults(
    profile: ForecastingProfile,
    plan: ForecastPlan,
) -> dict:
    """
    Compute deterministic defaults for `TimeSeriesFold` parameters.

    Parameters
    ----------
    profile : ForecastingProfile
        Profiled dataset and high-level modeling decisions.
    plan : ForecastPlan
        Detailed forecasting plan.

    Returns
    -------
    cv_params : dict
        Dictionary of `TimeSeriesFold` keyword arguments with
        recommended defaults.
    """

    span_index_length = profile.data_profile.span_index_length
    steps = plan.steps

    # Compute initial_train_size as an integer first (with floor/ceiling)
    initial_train_size = int(0.7 * span_index_length)
    min_train_size = _compute_min_train_size(plan)
    initial_train_size = max(initial_train_size, min_train_size)

    # Ensure initial_train_size leaves room for at least 2 folds
    max_train_size = span_index_length - 2 * steps
    if max_train_size > 0:
        initial_train_size = min(initial_train_size, max_train_size)

    # Convert to a date string when datetime info is available
    initial_train_size = _position_to_date(
        position=initial_train_size,
        start_date=profile.data_profile.span_start_date,
        frequency=profile.data_profile.frequency,
        time_zone=profile.data_profile.time_zone,
    )

    return {
        "steps": steps,
        "initial_train_size": initial_train_size,
        # Train once, as skforecast does by default: refitting in every fold
        # multiplies the cost by the number of folds, which grows with the
        # series length (hours for a direct forecaster on hourly data).
        "refit": False,
        "fixed_train_size": False,
        "gap": 0,
        "fold_stride": None,
        "skip_folds": None,
        "allow_incomplete_fold": True,
        "differentiation": plan.forecaster_kwargs.get("differentiation"),
    }


def build_cv_explanation(
    cv_params: dict,
    n_observations: int,
    n_folds: int,
    trains: bool = True,
    n_fits: int | None = None,
    forecaster: str | None = None,
    inference_windows: int | None = None,
) -> str:
    """
    Build a human-readable explanation of the cross-validation strategy.

    Parameters
    ----------
    cv_params : dict
        Resolved `TimeSeriesFold` parameters.
    n_observations : int
        Total number of observations in the dataset.
    n_folds : int
        Number of folds produced by the configuration.
    trains : bool, default True
        Whether the forecaster is trained. A foundation model is not: each
        fold forecasts from the observations before it, so the training
        window and the refit settings do not apply and are not described.
    n_fits : int, default None
        Number of folds in which the forecaster is trained, see
        `count_cv_fits`. Stated when the forecaster is refitted. None when
        unknown.
    forecaster : str, default None
        Name of the forecaster the strategy is applied to. For a direct
        forecaster, which fits one estimator per step, the total number of
        estimator fits is also stated, and for `ForecasterStats` that it is
        refitted in every fold (see `cv_as_executed`). None when the
        strategy is shared by several forecasters.
    inference_windows : int, default None
        Number of inference windows of a foundation model (one per series
        and fold, see `count_inference_windows`), stated when `trains` is
        False. None when unknown.

    Returns
    -------
    explanation : str
        Multi-sentence description of the CV configuration.
    """

    initial_train_size = cv_params["initial_train_size"]
    steps = cv_params["steps"]
    refit = cv_params["refit"]
    fixed_train_size = cv_params["fixed_train_size"]
    gap = cv_params["gap"]

    if not trains:
        if isinstance(initial_train_size, str):
            first_desc = f"First fold forecasts from the data up to {initial_train_size}"
        else:
            pct = round(100 * initial_train_size / n_observations)
            first_desc = (
                f"First fold forecasts from {pct}% of data "
                f"({initial_train_size} observations)"
            )
        parts = [
            first_desc,
            "no training (each fold forecasts from the observations before it)",
            f"{steps}-step horizon",
        ]
        if n_folds > 0:
            parts.append(f"{n_folds} folds")
        if gap > 0:
            parts.append(f"gap of {gap} observations")
        explanation = ", ".join(parts) + "."
        if inference_windows is not None:
            explanation += (
                f" The model forecasts each series in each fold "
                f"({inference_windows} inference windows in all)."
            )
        return explanation

    if isinstance(initial_train_size, str):
        train_desc = f"Initial training up to {initial_train_size}"
    else:
        pct = round(100 * initial_train_size / n_observations)
        train_desc = (
            f"Using {pct}% of data ({initial_train_size} observations) for"
            f" initial training"
        )
    trainings = f" ({n_fits} trainings)" if n_fits is not None else ""
    if refit is True:
        refit_desc = f"refit every fold{trainings}"
    elif isinstance(refit, int) and not isinstance(refit, bool) and refit > 0:
        refit_desc = f"refit every {refit} folds{trainings}"
    else:
        refit_desc = "trained once (no refit)"

    # The window type only matters when the forecaster is refitted.
    parts = [train_desc]
    if refit_desc != "trained once (no refit)":
        parts.append("fixed window" if fixed_train_size else "expanding window")
    parts += [refit_desc, f"{steps}-step horizon"]

    if n_folds > 0:
        parts.append(f"{n_folds} folds")

    if gap > 0:
        parts.append(f"gap of {gap} observations")

    differentiation = cv_params.get("differentiation")
    if differentiation is not None:
        parts.append(f"differentiation order {differentiation}")

    explanation = ", ".join(parts) + "."
    if forecaster == "ForecasterStats":
        explanation += (
            " ForecasterStats is refitted in every fold whatever `refit` "
            "says: skforecast requires it for ARIMA models."
        )
    if forecaster in DIRECT_FORECASTERS and n_fits is not None:
        explanation += (
            f" {forecaster} fits one estimator per step, so each training "
            f"fits {steps} estimators "
            f"({count_estimator_fits(n_fits, forecaster, steps)} fits in all)."
        )

    return explanation


def _local_index(
    start_date: str,
    n_observations: int,
    frequency: str,
    time_zone: str | None,
) -> pd.DatetimeIndex:
    """
    Rebuild the dates of the data, as local times without time zone.

    Without a time zone it is the regular grid from `start_date`. With one,
    the grid is built in that zone and its local times are returned: they
    skip an hour at the spring daylight saving change and repeat one in
    autumn, as the dates of the data do, so the position of a date is the
    one it has in the data. A zone pandas cannot use gives the regular grid.
    """
    index = pd.date_range(start=start_date, periods=n_observations, freq=frequency)
    if time_zone is None:
        return index
    try:
        aware = pd.date_range(
            start   = pd.Timestamp(start_date).tz_localize(time_zone),
            periods = n_observations,
            freq    = frequency,
        )
    except Exception:
        return index

    return aware.tz_localize(None)


def _split_folds(
    cv: TimeSeriesFold,
    n_observations: int,
    start_date: str | None = None,
    frequency: str | None = None,
    time_zone: str | None = None,
) -> list:
    """
    Split a throwaway index the way a cross-validation splitter would.

    Builds a throwaway index of the given length and runs `cv.split` on
    it, so folds and refits can be counted before any data is loaded. A
    date-based `initial_train_size` (string or pandas Timestamp) needs a
    DatetimeIndex so `cv.split` can locate the split date; integer sizes
    are split on a plain RangeIndex. This is the single place where a
    date-based `initial_train_size` is checked against the dataset.

    The `window_size` of `cv` is unset here (no forecaster attached yet),
    so skforecast emits an `IgnoredArgumentWarning` about the last window.
    It is irrelevant for counting folds and is suppressed. The `verbose`
    setting of `cv` is also temporarily disabled so a user-supplied
    splitter does not print its fold report, and restored on exit.

    Parameters
    ----------
    cv : TimeSeriesFold
        Configured cross-validation fold splitter.
    n_observations : int
        Number of observations spanned by the dataset.
    start_date : str, default None
        First date of the dataset, used to build a DatetimeIndex when
        `cv.initial_train_size` is a date string or a pandas Timestamp.
        Required in that case; a `ValueError` is raised otherwise.
    frequency : str, default None
        Index frequency, used together with `start_date` to build the
        DatetimeIndex. Required when `cv.initial_train_size` is a date;
        without it the split date cannot be located on the real index, so
        a `ValueError` is raised rather than counting folds on a guessed
        index.
    time_zone : str, default None
        Time zone of the dates of the dataset (`DataProfile.time_zone`),
        to place a date on their local times (see `_local_index`).

    Returns
    -------
    folds : list
        Folds as returned by `cv.split(as_pandas=False)`; the last element
        of each fold says whether the forecaster is trained in it.
    """
    its = cv.initial_train_size
    if isinstance(its, (str, pd.Timestamp)):
        if start_date is None or frequency is None:
            raise InvalidInputError(
                f"`initial_train_size` is a date ({its!r}) but the dataset has "
                f"no datetime index with a known frequency, so the split date "
                f"cannot be located. Pass an integer number of observations "
                f"instead.",
                field = "initial_train_size",
            )
        if isinstance(its, str):
            try:
                pd.Timestamp(its)
            except (ValueError, TypeError) as exc:
                raise InvalidInputError(
                    f"`initial_train_size` date {its!r} could not be parsed. "
                    f"Use an ISO date such as '2023-03-01'.",
                    field = "initial_train_size",
                ) from exc
        index = pd.date_range(
                    start   = start_date,
                    periods = n_observations,
                    freq    = frequency,
                )
        # skforecast places a date by the frequency of the index, which the
        # local times of a zone with daylight saving changes do not keep:
        # the date is counted on them here, as the backtesting script
        # counts it on the data (`_cv_in_time_zone`).
        local = _local_index(start_date, n_observations, frequency, time_zone)
        date = pd.Timestamp(its)
        if (
            not local.equals(index)
            and date.tz is None
            and local[0] <= date <= local[-1]
        ):
            cv = copy.deepcopy(cv)
            cv.set_params({"initial_train_size": int((local <= date).sum())})
            index = pd.RangeIndex(n_observations)
    else:
        index = pd.RangeIndex(n_observations)

    # `cv` may be user-supplied with `verbose=True`, in which case `split`
    # prints a full fold report. Counting folds is an internal diagnostic,
    # so silence it and restore the original setting afterwards.
    original_verbose = cv.verbose
    cv.verbose = False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=IgnoredArgumentWarning)
            folds = cv.split(X=index, as_pandas=False)
    finally:
        cv.verbose = original_verbose

    return folds



def count_cv_folds(
    cv: TimeSeriesFold,
    n_observations: int,
    start_date: str | None = None,
    frequency: str | None = None,
    time_zone: str | None = None,
) -> int:
    """
    Count the folds a cross-validation splitter produces over a dataset.

    A date-based `initial_train_size` is checked against the dataset here,
    for splitters built by `build_cv` as well as for user-supplied ones
    described by `resolve_cv_config`.

    Parameters
    ----------
    cv : TimeSeriesFold
        Configured cross-validation fold splitter.
    n_observations : int
        Number of observations spanned by the dataset.
    start_date : str, default None
        First date of the dataset. Required when `cv.initial_train_size`
        is a date string or a pandas Timestamp.
    frequency : str, default None
        Index frequency. Required when `cv.initial_train_size` is a date.
    time_zone : str, default None
        Time zone of the dates (`DataProfile.time_zone`).

    Returns
    -------
    n_folds : int
        Number of folds produced by the configuration.
    """

    return len(_split_folds(cv, n_observations, start_date, frequency, time_zone))


def count_cv_fits(
    cv: TimeSeriesFold,
    n_observations: int,
    start_date: str | None = None,
    frequency: str | None = None,
    time_zone: str | None = None,
) -> int:
    """
    Count how many folds train the forecaster under a splitter.

    Reads the training flag that `TimeSeriesFold.split` sets on each fold:
    the first fold always trains, and the rest follow `refit` (never with
    False, every fold with True, every n folds with an integer).

    Parameters
    ----------
    cv : TimeSeriesFold
        Configured cross-validation fold splitter.
    n_observations : int
        Number of observations spanned by the dataset.
    start_date : str, default None
        First date of the dataset. Required when `cv.initial_train_size`
        is a date string or a pandas Timestamp.
    frequency : str, default None
        Index frequency. Required when `cv.initial_train_size` is a date.
    time_zone : str, default None
        Time zone of the dates (`DataProfile.time_zone`).

    Returns
    -------
    n_fits : int
        Number of folds in which the forecaster is trained.
    """

    folds = _split_folds(cv, n_observations, start_date, frequency, time_zone)

    return sum(bool(fold[-1]) for fold in folds)


def count_estimator_fits(
    n_fits: int,
    forecaster: str,
    steps: int,
    n_folds: int | None = None,
) -> int:
    """
    Count the estimator fits of a backtest, the measure of its cost.

    Parameters
    ----------
    n_fits : int
        Number of folds in which the forecaster is trained, see
        `count_cv_fits`.
    forecaster : str
        Name of the skforecast forecaster class.
    steps : int
        Forecast horizon of each fold.
    n_folds : int, default None
        Number of folds of the strategy, see `count_cv_folds`. skforecast
        refits `ForecasterStats` in every fold whatever `refit` says (see
        `cv_as_executed`), so its count is `n_folds` when given. None when
        `n_fits` already counts the folds of the strategy as executed.

    Returns
    -------
    estimator_fits : int
        Number of times an estimator is fitted: `n_fits * steps` for the
        direct forecasters, which fit one estimator per step, 0 for
        `ForecasterFoundation` (never trained) and
        `ForecasterEquivalentDate` (no estimator), `n_folds` (or `n_fits`
        when it is None) for `ForecasterStats`, and `n_fits` otherwise.
    """

    if forecaster in ("ForecasterFoundation", "ForecasterEquivalentDate"):
        return 0
    if forecaster in DIRECT_FORECASTERS:
        return n_fits * steps
    if forecaster == "ForecasterStats" and n_folds is not None:
        return n_folds

    return n_fits


def count_inference_windows(
    n_folds: int,
    n_series: int,
    forecaster: str,
) -> int:
    """
    Count the inference windows of a backtest, the measure of the cost of a
    foundation model.

    A foundation model is never trained: it loads its weights once and
    forecasts each series in each fold, so its time grows with the number
    of series times the number of folds.

    Parameters
    ----------
    n_folds : int
        Number of folds of the strategy, see `count_cv_folds`.
    n_series : int
        Number of series of the data.
    forecaster : str
        Name of the skforecast forecaster class.

    Returns
    -------
    inference_windows : int
        `n_folds * n_series` for `ForecasterFoundation`, 0 for any other
        forecaster (their cost is counted in estimator fits, see
        `count_estimator_fits`). With long data whose series start on
        different dates, a series absent from a fold is counted all the
        same, so it is an upper bound.
    """

    if forecaster != "ForecasterFoundation":
        return 0

    return n_folds * n_series


def cv_as_executed(
    cv: TimeSeriesFold,
    forecaster: str | None,
) -> TimeSeriesFold:
    """
    Return the splitter that skforecast runs for a forecaster.

    `backtesting_stats` refits in every fold unless all the estimators are
    `skforecast.stats.Sarimax`, and `ForecasterStats` plans always use
    `Arima`: a `refit` other than `True` (or 1) is replaced by `True`, with
    the warning silenced by `suppress_warnings=True` in the script. The
    script writes `fixed_train_size` only when `refit` is set, so after a
    `refit=False` the training window has the fixed size that is the
    default of `TimeSeriesFold`. The copy returned states both, so the
    script, `cv_config` and the explanation describe what runs; the
    metrics do not change. Any other forecaster runs `cv` as it is.

    Parameters
    ----------
    cv : TimeSeriesFold
        Configured cross-validation fold splitter. It is not modified.
    forecaster : str, None
        Name of the forecaster the strategy is applied to. None when the
        strategy is shared by several forecasters.

    Returns
    -------
    cv : TimeSeriesFold
        `cv` itself, or for `ForecasterStats` with a `refit` other than
        `True` (or 1) a shallow copy with `refit=True` and the
        `fixed_train_size` that runs.
    """

    if forecaster != "ForecasterStats" or cv.refit == 1:
        return cv

    executed = copy.copy(cv)
    executed.fixed_train_size = bool(cv.fixed_train_size) if cv.refit else True
    executed.refit = True

    return executed


def build_cv(
    cv_params: dict,
    data_profile: DataProfile,
    min_folds: int = 2,
) -> TimeSeriesFold:
    """
    Build a `TimeSeriesFold` from resolved parameters and validate it.

    Single construction path shared by `create_cv` (deterministic defaults
    plus explicit overrides) and the LLM configuration loop, so a
    configuration accepted in one place cannot fail in the other. Resolves
    `initial_train_size` (a fraction becomes an absolute count, a pandas
    Timestamp becomes a date string), builds the splitter and counts the
    folds it produces over the dataset with `count_cv_folds`, which also
    checks that a date-based size can be located on the dataset index. A
    `ValueError` is raised when fewer than `min_folds` folds result.

    An argument that `TimeSeriesFold` rejects raises `InvalidInputError`
    (`InvalidInputTypeError` for a wrong type) naming it in `field` when
    its message names a single one, and a list of `skip_folds` with
    indexes beyond the folds of the strategy, which `TimeSeriesFold`
    ignores, raises too.

    Parameters
    ----------
    cv_params : dict
        Resolved `TimeSeriesFold` parameters with keys `'steps'`,
        `'initial_train_size'`, `'refit'`, `'fixed_train_size'`, `'gap'`,
        `'fold_stride'`, `'skip_folds'`, `'allow_incomplete_fold'` and
        `'differentiation'`. Keys starting with an underscore (such as the
        LLM `'_reasoning'`) are ignored. `'initial_train_size'` is
        normalised in place.
    data_profile : DataProfile
        Profile of the dataset the splitter is applied to.
    min_folds : int, default 2
        Minimum number of folds the configuration must produce.

    Returns
    -------
    cv : TimeSeriesFold
        Validated fold splitter.
    """

    cv_params["initial_train_size"] = _resolve_initial_train_size(
        value        = cv_params["initial_train_size"],
        data_profile = data_profile,
    )

    try:
        cv = TimeSeriesFold(
            steps                 = cv_params["steps"],
            initial_train_size    = cv_params["initial_train_size"],
            refit                 = cv_params["refit"],
            fixed_train_size      = cv_params["fixed_train_size"],
            gap                   = cv_params["gap"],
            fold_stride           = cv_params.get("fold_stride"),
            skip_folds            = cv_params.get("skip_folds"),
            allow_incomplete_fold = cv_params.get("allow_incomplete_fold", True),
            differentiation       = cv_params.get("differentiation"),
            verbose               = False,
        )

        n_folds = count_cv_folds(
                      cv             = cv,
                      n_observations = data_profile.span_index_length,
                      start_date     = data_profile.span_start_date,
                      frequency      = data_profile.frequency,
                      time_zone      = data_profile.time_zone,
                  )
    except InvalidInputError:
        raise
    except (ValueError, TypeError) as exc:
        raise _strategy_error(exc) from exc

    _check_skip_folds(cv, data_profile)
    if n_folds < min_folds:
        public_params = {
            key: value for key, value in cv_params.items()
            if not key.startswith("_")
        }
        raise InvalidInputError(
            f"The resolved CV configuration produces only "
            f"{n_folds} fold(s). At least {min_folds} are required. "
            f"Resolved parameters: {public_params}.",
            code = "insufficient_data",
        )

    return cv


# Arguments of `TimeSeriesFold` that its error messages name in backticks.
_CV_ARGUMENT = re.compile(
    r"`(initial_train_size|fold_stride|gap|skip_folds|refit|fixed_train_size"
    r"|allow_incomplete_fold|steps)\b"
)


def _strategy_error(exc: Exception) -> InvalidInputError:
    """
    Turn an error of skforecast while it builds or splits a cross-validation
    strategy into an `InvalidInputError` naming the argument at fault.

    `TimeSeriesFold` checks its arguments (`gap >= 0`, `fold_stride >= 1`,
    an `initial_train_size` inside the data, ...) with a `ValueError` or a
    `TypeError` of its own; the message, which quotes sizes and dates of
    the index but no value of the data, is kept on one line, and a
    `TypeError` stays one (`InvalidInputTypeError`).
    """
    message = " ".join(str(exc).split()) or type(exc).__name__
    # A message that names several arguments (`initial_train_size + gap`)
    # does not say which one to change.
    named = set(_CV_ARGUMENT.findall(message))
    error_class = (
        InvalidInputTypeError if isinstance(exc, TypeError) else InvalidInputError
    )
    field = named.pop() if len(named) == 1 else None
    # The folds are the remedy only when the strategy does not fit in the
    # data; a value `TimeSeriesFold` rejects by itself (`gap=-1`,
    # `refit='yes'`) is fixed in its own argument.
    if field not in (None, "initial_train_size", "steps"):
        hint = f"Pass a value that `TimeSeriesFold` accepts for `{field}`."
    else:
        hint = (
            "Change the arguments of the strategy (`initial_train_size`, "
            "`fold_stride`, `gap`, `skip_folds`) or the `steps` of the plan "
            "so that at least two folds fit in the data."
        )

    return error_class(
        f"The cross-validation strategy cannot be built: {message}",
        field = field,
        hint  = hint,
    )


def _check_skip_folds(cv: TimeSeriesFold, data_profile: DataProfile) -> None:
    """
    Reject a list of `skip_folds` with indexes beyond the folds of `cv`,
    which `TimeSeriesFold` ignores without an error.
    """
    skip_folds = cv.skip_folds
    if not isinstance(skip_folds, list) or not skip_folds:
        return
    unskipped = copy.copy(cv)
    unskipped.skip_folds = None
    n_folds = count_cv_folds(
                  cv             = unskipped,
                  n_observations = data_profile.span_index_length,
                  start_date     = data_profile.span_start_date,
                  frequency      = data_profile.frequency,
                  time_zone      = data_profile.time_zone,
              )
    beyond = [index for index in skip_folds if index >= n_folds]
    if beyond:
        shown = (
            f"{beyond[:5]} and {len(beyond) - 5} more" if len(beyond) > 5
            else f"{beyond}"
        )
        raise InvalidInputError(
            f"`skip_folds` names folds that do not exist ({shown}): the "
            f"strategy has {n_folds} folds, numbered from 0 to {n_folds - 1}.",
            field = "skip_folds",
        )


def _resolve_initial_train_size(
    value: int | float | str | pd.Timestamp,
    data_profile: DataProfile,
) -> int | str:
    """
    Normalise an `initial_train_size` value to what `TimeSeriesFold` stores.

    A float in (0, 1) is a fraction of the dataset span and becomes an
    absolute count. A pandas Timestamp becomes its string form, so the
    rendered `TimeSeriesFold(...)` snippet stays valid Python and the
    resolved configuration serializes to JSON. A `bool` is rejected because
    `TimeSeriesFold` would silently read it as the integer 1. Integers and
    date strings pass through; `TimeSeriesFold` validates the former and
    `count_cv_folds` the latter.

    Parameters
    ----------
    value : int, float, str, pandas Timestamp
        Requested initial training size.
    data_profile : DataProfile
        Profile of the dataset, used to resolve a fraction.

    Returns
    -------
    initial_train_size : int, str
        Normalised value.
    """

    if isinstance(value, bool):
        raise InvalidInputError(
            f"`initial_train_size` must be an int, a float in (0, 1), a date "
            f"string or a pandas Timestamp, got {value!r}.",
            field = "initial_train_size",
        )
    if isinstance(value, float):
        if not (0 < value < 1):
            raise InvalidInputError(
                f"initial_train_size as float must satisfy "
                f"0 < value < 1, got {value}.",
                field = "initial_train_size",
            )
        return int(value * data_profile.span_index_length)
    if isinstance(value, pd.Timestamp):
        return _timestamp_to_str(value)
    return value


def _timestamp_to_str(ts: pd.Timestamp) -> str:
    """
    Render a Timestamp as a date string, keeping the time only when set.

    Parameters
    ----------
    ts : pandas Timestamp
        Timestamp to render.

    Returns
    -------
    text : str
        `'YYYY-MM-DD'` when the time component is midnight, otherwise the
        full `'YYYY-MM-DD HH:MM:SS'` form.
    """

    if ts.hour != 0 or ts.minute != 0 or ts.second != 0:
        return str(ts)
    return str(ts.date())


def resolve_cv_config(
    cv: TimeSeriesFold,
    data_profile: DataProfile,
    trains: bool = True,
    forecaster: str | None = None,
) -> tuple[dict, str]:
    """
    Describe a cross-validation splitter as applied to a profiled dataset.

    Counts the folds `cv` produces over the dataset span and returns the
    `TimeSeriesFold` parameters together with that count, plus the
    human-readable explanation built from them. `n_folds` is stored next
    to the parameters because it is the fact a reader (or the LLM)
    actually needs; without it the count had to be re-derived from the
    prediction row count.

    Parameters
    ----------
    cv : TimeSeriesFold
        Configured cross-validation fold splitter.
    data_profile : DataProfile
        Profile of the dataset the splitter is applied to.
    trains : bool, default True
        Whether the forecaster is trained; False for a foundation model,
        whose explanation does not describe a training window or refits.
    forecaster : str, default None
        Name of the forecaster the strategy is applied to, used to state
        the estimator fits of a direct forecaster. For `ForecasterStats`
        the strategy is described as skforecast runs it, refitted in every
        fold (see `cv_as_executed`). None when the strategy is shared by
        several forecasters.

    Returns
    -------
    cv_config : dict
        Resolved `TimeSeriesFold` parameters (`steps`,
        `initial_train_size`, `refit`, `fixed_train_size`, `gap`,
        `fold_stride`, `skip_folds`, `allow_incomplete_fold`,
        `differentiation`) plus `n_folds` and `n_fits` (folds in which the
        forecaster is trained, 0 when it is not trained), and for
        `ForecasterFoundation` `inference_windows` (one per series and
        fold, see `count_inference_windows`).
    explanation : str
        Multi-sentence description of the strategy, see
        `build_cv_explanation`.
    """

    cv = cv_as_executed(cv, forecaster)
    span_index_length = data_profile.span_index_length
    folds = _split_folds(
                cv             = cv,
                n_observations = span_index_length,
                start_date     = data_profile.span_start_date,
                frequency      = data_profile.frequency,
                time_zone      = data_profile.time_zone,
            )
    n_folds = len(folds)
    n_fits = sum(bool(fold[-1]) for fold in folds) if trains else 0
    cv_config = {
        "steps": cv.steps,
        "initial_train_size": cv.initial_train_size,
        "refit": cv.refit,
        "fixed_train_size": cv.fixed_train_size,
        "gap": cv.gap,
        "fold_stride": cv.fold_stride,
        "skip_folds": cv.skip_folds,
        "allow_incomplete_fold": cv.allow_incomplete_fold,
        "differentiation": cv.differentiation,
        "n_folds": n_folds,
        "n_fits": n_fits,
    }
    inference_windows = None
    if forecaster == "ForecasterFoundation":
        inference_windows = count_inference_windows(
                                n_folds    = n_folds,
                                n_series   = data_profile.n_series,
                                forecaster = forecaster,
                            )
        cv_config["inference_windows"] = inference_windows
    explanation = build_cv_explanation(
                      cv_params         = cv_config,
                      n_observations    = span_index_length,
                      n_folds           = n_folds,
                      trains            = trains,
                      n_fits            = n_fits,
                      forecaster        = forecaster,
                      inference_windows = inference_windows,
                  )

    return cv_config, explanation


def plan_window_size(plan: ForecastPlan) -> int | None:
    """
    Return the window size of the forecaster of a plan, as skforecast
    computes it: the observations it reads before its first prediction.

    For the machine learning forecasters, the largest lag or window feature
    plus the differentiation order; for the baseline, `offset * n_offsets`.
    None for the forecasters whose window is not checked here
    (`ForecasterStats`, `ForecasterFoundation`).

    Parameters
    ----------
    plan : ForecastPlan
        Detailed forecasting plan.

    Returns
    -------
    window_size : int, None
        Window size of the forecaster, or None.
    """
    kwargs = plan.forecaster_kwargs
    if plan.task_type in ML_TASK_TYPES:
        lags = kwargs.get("lags")
        if isinstance(lags, int):
            max_lag = lags
        elif isinstance(lags, list):
            max_lag = max(lags, default=0)
        else:
            max_lag = 0
        max_window = 0
        for entry in kwargs.get("window_features") or []:
            sizes = entry.get("window_size")
            sizes = sizes if isinstance(sizes, list) else [sizes]
            max_window = max(
                [max_window, *(size for size in sizes if isinstance(size, int))]
            )
        return max(max_lag, max_window) + (kwargs.get("differentiation") or 0)
    if plan.task_type == "baseline":
        offset = kwargs.get("offset", 1)
        if isinstance(offset, int):
            return offset * kwargs.get("n_offsets", 1)

    return None


def first_window_issue(
    plan: ForecastPlan,
    cv: TimeSeriesFold,
    data_profile: DataProfile,
) -> str | None:
    """
    Say why the first training window of a strategy is too short for the
    forecaster of a plan, or return None when it is not.

    skforecast needs more observations in the first training window than
    the window size of the forecaster (`plan_window_size`), and a direct
    forecaster, which trains one estimator per step, at least the window
    size plus `steps`. A strategy whose horizon leaves fewer, such as
    `steps=100` on 204 observations (2 folds take 200), is valid for
    `TimeSeriesFold` and fails when the forecaster is backtested.

    Parameters
    ----------
    plan : ForecastPlan
        Plan to backtest.
    cv : TimeSeriesFold
        Strategy of the backtest.
    data_profile : DataProfile
        Profile of the data, to place a date `initial_train_size`.

    Returns
    -------
    issue : str, None
        What fails, or None.
    """
    window_size = plan_window_size(plan)
    if window_size is None:
        return None
    # skforecast splits the dates of every series, from the earliest first
    # date in long format, where `start_date` is the latest one.
    folds = _split_folds(
        cv             = cv_as_executed(cv, plan.forecaster),
        n_observations = data_profile.span_index_length,
        start_date     = data_profile.span_start_date,
        frequency      = data_profile.frequency,
        time_zone      = data_profile.time_zone,
    )
    if not folds:
        return None
    train_start, train_end = folds[0][1]
    n_train = train_end - train_start
    if plan.forecaster in DIRECT_FORECASTERS:
        needed = window_size + plan.steps
        reason = (
            f"its window size, {window_size}, plus the {plan.steps} steps it "
            f"is trained to predict"
        )
    else:
        needed = window_size + 1
        reason = f"more than its window size, {window_size}"
    if n_train >= needed:
        return None

    return (
        f"The first training window of the strategy has {n_train} "
        f"observations, and {plan.forecaster} needs at least {needed} "
        f"({reason}), so skforecast would fail"
    )


def check_first_window(
    plan: ForecastPlan,
    cv: TimeSeriesFold,
    data_profile: DataProfile,
    strict: bool = True,
) -> None:
    """
    Raise when the first training window of a strategy is too short for the
    forecaster of a plan (see `first_window_issue`).

    Parameters
    ----------
    plan : ForecastPlan
        Plan to backtest.
    cv : TimeSeriesFold
        Strategy of the backtest.
    data_profile : DataProfile
        Profile of the data.
    strict : bool, default True
        Whether a strategy that skforecast cannot split on the dates of the
        profile (a date `initial_train_size` outside the data) raises an
        `InvalidInputError` with the message of skforecast. When False it
        is left to where the strategy runs (`backtest_code()` returns its
        script).

    Returns
    -------
    None
    """
    try:
        issue = first_window_issue(plan, cv, data_profile)
    except (ValueError, TypeError) as exc:
        if strict:
            raise _strategy_error(exc) from exc
        return
    if issue is not None:
        features = (
            ", fewer lags or smaller window features"
            if plan.forecaster in AUTOREG_FORECASTERS else ""
        )
        raise InvalidInputError(
            f"{issue}. Use a later `initial_train_size`, or a shorter "
            f"horizon (`steps`){features}.",
            field = "cv",
            code  = "insufficient_data",
        )


def warn_first_window(
    plan: ForecastPlan,
    cv: TimeSeriesFold,
    data_profile: DataProfile,
) -> None:
    """
    Warn when a strategy is built whose first training window is too short
    for the forecaster of its plan: its backtest raises (see
    `check_first_window`), but the strategy can still serve forecasters
    with a smaller window in `compare()`.

    Parameters
    ----------
    plan : ForecastPlan
        Plan the strategy is built for.
    cv : TimeSeriesFold
        Strategy built.
    data_profile : DataProfile
        Profile of the data.

    Returns
    -------
    None
    """
    try:
        issue = first_window_issue(plan, cv, data_profile)
    except ValueError:
        # A strategy that cannot be split is reported by `build_cv()`.
        return
    if issue is not None:
        warnings.warn(
            f"{issue}: `backtest()` of this plan with this strategy raises. "
            f"The strategy can still serve the candidates of `compare()` "
            f"with a smaller window; use a later `initial_train_size`, or a "
            f"shorter horizon, to backtest this plan.",
            UserWarning,
            stacklevel = 3,
        )


def _compute_min_train_size(plan: ForecastPlan) -> int:
    """
    Compute the minimum initial training size based on task type.

    The window size of the forecaster is the one skforecast computes
    (`plan_window_size`: the largest lag or window feature plus the
    differentiation order, or `offset * n_offsets` for the baseline).
    `initial_train_size` must exceed it for skforecast to accept the CV
    configuration, so the minimum is the window plus `steps`; without lags
    or window features, and for the forecasters without a window, it is
    twice `steps`.

    Parameters
    ----------
    plan : ForecastPlan
        Detailed forecasting plan.

    Returns
    -------
    min_train_size : int
        Minimum number of observations for the initial training set.
    """

    steps = plan.steps
    window_size = plan_window_size(plan)

    if plan.task_type in ML_TASK_TYPES:
        differentiation = plan.forecaster_kwargs.get("differentiation") or 0
        if window_size == differentiation:
            # No lags nor window features: the order alone is no window.
            return 2 * steps
        return window_size + steps

    if plan.task_type == "baseline" and window_size is not None:
        # ForecasterEquivalentDate needs more observations than
        # `offset * n_offsets` to find every equivalent date.
        return max(window_size + steps, 2 * steps)

    # statistical, foundation
    return 2 * steps


def _position_to_date(
    position: int,
    start_date: str | None,
    frequency: str | None,
    time_zone: str | None = None,
) -> int | str:
    """
    Convert an integer position to a date string.

    Uses the start date and frequency to reconstruct the date at the
    given position (1-based count, so the date returned is at index
    `position - 1`).

    Parameters
    ----------
    position : int
        Number of observations (1-based count).
    start_date : str, None
        Start date of the datetime index.
    frequency : str, None
        Pandas frequency string.
    time_zone : str, default None
        Time zone of the dates (`DataProfile.time_zone`): the date is then
        the local time at that position (see `_local_index`).

    Returns
    -------
    result : int or str
        Date string if conversion is possible, otherwise the original
        integer.
    """
    if start_date is None or frequency is None:
        return position

    try:
        idx = _local_index(start_date, position, frequency, time_zone)
        return _timestamp_to_str(idx[-1])
    except Exception:
        return position
