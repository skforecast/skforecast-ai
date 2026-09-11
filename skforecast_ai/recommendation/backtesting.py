################################################################################
#                       Recommendations: backtesting                           #
#                                                                              #
# Cross-validation strategy recommendation for backtesting                     #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import warnings
import pandas as pd
from skforecast.exceptions import IgnoredArgumentWarning
from skforecast.model_selection import TimeSeriesFold
from ..schemas import DataProfile, ForecastingProfile, ForecastPlan


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
        start_date=profile.data_profile.start_date,
        frequency=profile.data_profile.frequency,
    )

    return {
        "steps": steps,
        "initial_train_size": initial_train_size,
        "refit": True,
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

    if isinstance(initial_train_size, str):
        train_desc = f"Initial training up to {initial_train_size}"
    else:
        pct = round(100 * initial_train_size / n_observations)
        train_desc = (
            f"Using {pct}% of data ({initial_train_size} observations) for"
            f" initial training"
        )
    window_type = "fixed window" if fixed_train_size else "expanding window"

    if refit is True:
        refit_desc = "refit every fold"
    elif refit is False:
        refit_desc = "no refit"
    elif isinstance(refit, int):
        refit_desc = f"refit every {refit} folds"
    else:
        refit_desc = "no refit"

    parts = [
        train_desc,
        window_type,
        refit_desc,
        f"{steps}-step horizon",
    ]

    if n_folds > 0:
        parts.append(f"{n_folds} folds")

    if gap > 0:
        parts.append(f"gap of {gap} observations")

    differentiation = cv_params.get("differentiation")
    if differentiation is not None:
        parts.append(f"differentiation order {differentiation}")

    return ", ".join(parts) + "."


def count_cv_folds(
    cv: TimeSeriesFold,
    n_observations: int,
    start_date: str | None = None,
    frequency: str | None = None,
) -> int:
    """
    Count the folds a cross-validation splitter produces over a dataset.

    Builds a throwaway index of the given length and runs `cv.split` to
    count the resulting folds. A date-based `initial_train_size` (string or
    pandas Timestamp) needs a DatetimeIndex so `cv.split` can locate the
    split date; integer sizes are counted against a plain RangeIndex. This
    is the single place where a date-based `initial_train_size` is checked
    against the dataset, for splitters built by `build_cv` as well as for
    user-supplied ones described by `resolve_cv_config`.

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

    Returns
    -------
    n_folds : int
        Number of folds produced by the configuration.
    """
    its = cv.initial_train_size
    if isinstance(its, (str, pd.Timestamp)):
        if start_date is None or frequency is None:
            raise ValueError(
                f"`initial_train_size` is a date ({its!r}) but the dataset has "
                f"no datetime index with a known frequency, so the split date "
                f"cannot be located. Pass an integer number of observations "
                f"instead."
            )
        if isinstance(its, str):
            try:
                pd.Timestamp(its)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"`initial_train_size` date {its!r} could not be parsed. "
                    f"Use an ISO date such as '2023-03-01'."
                ) from exc
        index = pd.date_range(
                    start   = start_date,
                    periods = n_observations,
                    freq    = frequency,
                )
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

    return len(folds)



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
                  start_date     = data_profile.start_date,
                  frequency      = data_profile.frequency,
              )
    if n_folds < min_folds:
        public_params = {
            key: value for key, value in cv_params.items()
            if not key.startswith("_")
        }
        raise ValueError(
            f"The resolved CV configuration produces only "
            f"{n_folds} fold(s). At least {min_folds} are required. "
            f"Resolved parameters: {public_params}."
        )

    return cv


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
        raise ValueError(
            f"`initial_train_size` must be an int, a float in (0, 1), a date "
            f"string or a pandas Timestamp, got {value!r}."
        )
    if isinstance(value, float):
        if not (0 < value < 1):
            raise ValueError(
                f"initial_train_size as float must satisfy "
                f"0 < value < 1, got {value}."
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

    Returns
    -------
    cv_config : dict
        Resolved `TimeSeriesFold` parameters (`steps`,
        `initial_train_size`, `refit`, `fixed_train_size`, `gap`,
        `fold_stride`, `skip_folds`, `allow_incomplete_fold`,
        `differentiation`) plus `n_folds`.
    explanation : str
        Multi-sentence description of the strategy, see
        `build_cv_explanation`.
    """

    span_index_length = data_profile.span_index_length
    n_folds = count_cv_folds(
                  cv             = cv,
                  n_observations = span_index_length,
                  start_date     = data_profile.start_date,
                  frequency      = data_profile.frequency,
              )
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
    }
    explanation = build_cv_explanation(
                      cv_params      = cv_config,
                      n_observations = span_index_length,
                      n_folds        = n_folds,
                  )

    return cv_config, explanation


def _compute_min_train_size(plan: ForecastPlan) -> int:
    """
    Compute the minimum initial training size based on task type.

    The effective window size of a forecaster is
    `max(max_lag, max_window_from_window_features)`.
    `initial_train_size` must exceed this value for skforecast to
    accept the CV configuration.

    Parameters
    ----------
    plan : ForecastPlan
        Detailed forecasting plan.

    Returns
    -------
    min_train_size : int
        Minimum number of observations for the initial training set.
    """

    task_type = plan.task_type
    steps = plan.steps

    if task_type in ("single_series", "multi_series", "multivariate"):
        lags = plan.forecaster_kwargs.get("lags")
        if isinstance(lags, int):
            max_lag = lags
        elif isinstance(lags, list):
            max_lag = max(lags, default=0)
        else:
            max_lag = 0

        # Account for window_features which also contribute to window_size
        max_window = 0
        wf = plan.forecaster_kwargs.get("window_features")
        if isinstance(wf, list):
            for entry in wf:
                ws = entry.get("window_size")
                if isinstance(ws, int):
                    max_window = max(max_window, ws)
                elif isinstance(ws, list):
                    max_window = max(max_window, max(ws, default=0))

        effective_window = max(max_lag, max_window)
        if effective_window == 0:
            return 2 * steps

        # Need initial_train_size > window_size, so floor at window + steps
        return effective_window + steps

    # statistical, foundation
    return 2 * steps


def _position_to_date(
    position: int,
    start_date: str | None,
    frequency: str | None,
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

    Returns
    -------
    result : int or str
        Date string if conversion is possible, otherwise the original
        integer.
    """
    if start_date is None or frequency is None:
        return position

    try:
        idx = pd.date_range(start=start_date, periods=position, freq=frequency)
        return _timestamp_to_str(idx[-1])
    except Exception:
        return position
