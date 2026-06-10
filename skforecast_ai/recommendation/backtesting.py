"""Cross-validation strategy recommendation for backtesting."""

from __future__ import annotations

import pandas as pd

from ..schemas import ForecastingProfile, ForecastPlan


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


def _compute_min_train_size(plan: ForecastPlan) -> int:
    """
    Compute the minimum initial training size based on task type.

    The effective window size of a forecaster is
    ``max(max_lag, max_window_from_window_features)``.
    ``initial_train_size`` must exceed this value for skforecast to
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
            max_lag = max(lags)
        else:
            max_lag = 0

        # Account for window_features which also contribute to window_size
        max_window = 0
        wf = plan.forecaster_kwargs.get("window_features")
        if isinstance(wf, list):
            for entry in wf:
                ws = entry.get("window_sizes")
                if isinstance(ws, int):
                    max_window = max(max_window, ws)
                elif isinstance(ws, list):
                    max_window = max(max_window, max(ws))

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
    ``position - 1``).

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
        ts = idx[-1]
        if ts.hour != 0 or ts.minute != 0 or ts.second != 0:
            return str(ts)
        return str(ts.date())
    except Exception:
        return position
