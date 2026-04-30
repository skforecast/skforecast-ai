"""Pre-execution validation checks for the forecasting runner."""

from __future__ import annotations

import pandas as pd

from ..schemas import DataProfile, ForecastPlan


def validate_run_inputs(
    data: pd.DataFrame,
    profile: DataProfile,
    plan: ForecastPlan,
) -> list[str]:
    """
    Validate preconditions before executing a forecasting workflow.

    Parameters
    ----------
    data : pandas DataFrame
        Input dataset.
    profile : DataProfile
        Profiled dataset metadata.
    plan : ForecastPlan
        Validated forecast plan.

    Returns
    -------
    warnings : list
        List of human-readable warning strings. Empty if all checks pass.
    """
    warnings: list[str] = []

    if profile.n_observations < 50:
        warnings.append(
            f"Series has only {profile.n_observations} observations. "
            f"Backtesting results may be unreliable with fewer than 50 "
            f"observations."
        )

    test_size = int(profile.n_observations * 0.2)
    if plan.horizon > test_size:
        warnings.append(
            f"Horizon ({plan.horizon}) exceeds test set size ({test_size}). "
            f"Backtesting may not produce meaningful results."
        )

    if plan.use_exog and profile.exog_columns:
        missing_cols = [
            col for col in profile.exog_columns if col not in data.columns
        ]
        if missing_cols:
            warnings.append(
                f"Exogenous columns missing from data: {missing_cols}."
            )

    if profile.missing_values:
        total_missing = sum(profile.missing_values.values())
        if total_missing > 0:
            warnings.append(
                f"Data contains {total_missing} missing value(s) across "
                f"columns: {list(profile.missing_values.keys())}. "
                f"This may cause errors during execution."
            )

    return warnings
