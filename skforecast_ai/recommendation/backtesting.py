"""Cross-validation strategy recommendation for backtesting."""

from __future__ import annotations

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

    n_observations = profile.data_profile.n_observations
    steps = plan.steps

    # Compute initial_train_size (70% of data, floored by task minimum)
    initial_train_size = int(0.7 * n_observations)
    min_train_size = _compute_min_train_size(plan)
    initial_train_size = max(initial_train_size, min_train_size)

    # Ensure initial_train_size leaves room for at least 2 folds
    max_train_size = n_observations - 2 * steps
    if max_train_size > 0:
        initial_train_size = min(initial_train_size, max_train_size)

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
        train_desc = f"training starting from {initial_train_size}"
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
