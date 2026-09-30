################################################################################
#                       Recommendations: baseline                              #
#                                                                              #
# Deterministic configuration of the ForecasterEquivalentDate baseline         #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from .._constants import FREQUENCY_TO_SEASONAL_PERIOD, MAX_FEATURE_FRACTION
from ..schemas import DataProfile
from .autoregressive import estimate_seasonality


def select_baseline_seasonal_period(frequency: str | None) -> int:
    """
    Select the seasonal period the baseline repeats.

    The period is read from `FREQUENCY_TO_SEASONAL_PERIOD`, the table the
    statistical forecaster also uses, so the baseline repeats the same
    cycle (the day for sub-daily data, the week for daily data). Frequencies
    missing from the table (multiplied or anchored variants such as `'2W'`
    or `'QS-OCT'`) fall back to the primary period of
    `estimate_seasonality()`.

    Parameters
    ----------
    frequency : str, None
        Pandas frequency string of the series.

    Returns
    -------
    period : int
        Seasonal period in steps, 1 when no seasonal period is known.
    """

    if frequency is None:
        return 1
    period = FREQUENCY_TO_SEASONAL_PERIOD.get(frequency)
    if period is None:
        seasonalities = estimate_seasonality(frequency)
        period = seasonalities[0] if seasonalities else 1
    return period


def baseline_missing_values_note(data_profile: DataProfile) -> str | None:
    """
    Explain why missing target values break the baseline.

    `ForecasterEquivalentDate` has no `dropna_from_series` option and
    learns nothing it could impute with: a missing value at an equivalent
    date becomes a missing prediction, and the backtesting metrics cannot
    be computed on it.

    Parameters
    ----------
    data_profile : DataProfile
        Universal data profile from Stage 1.

    Returns
    -------
    note : str, None
        Sentence describing the problem, or None when the target has
        neither missing values nor missing timestamps.
    """

    if not data_profile.missing_target and not data_profile.has_gaps:
        return None
    return (
        "the target has missing values or missing timestamps, and "
        "ForecasterEquivalentDate repeats a missing value as a missing "
        "prediction"
    )


def select_baseline_config(
    data_profile: DataProfile,
) -> tuple[dict[str, int], str]:
    """
    Select the `ForecasterEquivalentDate` configuration used as baseline.

    The baseline is a seasonal naive forecast: each step repeats the value
    observed one seasonal period earlier. The offset is the seasonal
    period implied by the frequency (see
    `select_baseline_seasonal_period()`). It falls back to a naive
    forecast (`offset=1`, repeat the last value) when the frequency is
    unknown, has no sub-period cycle, or when one seasonal period spans
    more than `MAX_FEATURE_FRACTION` of the observations (the same budget
    that bounds the lags).

    Parameters
    ----------
    data_profile : DataProfile
        Universal data profile from Stage 1.

    Returns
    -------
    forecaster_kwargs : dict
        Keyword arguments for the `ForecasterEquivalentDate` constructor,
        `{'offset': int, 'n_offsets': 1}`.
    explanation : str
        One sentence describing the chosen baseline.

    Notes
    -----
    Source: `skforecast_ai/skills/baseline-forecasting/SKILL.md`.

    An integer offset is used instead of a pandas `DateOffset`: it works
    with any index, and a `DateOffset` makes the window size unknown until
    the forecaster is fitted, so the cross-validation cannot be checked
    against it beforehand. The configuration is fixed rather than searched
    with `grid_search_equivalent_date`: the baseline is a reference, and
    tuning it on the folds used to rank the candidates would bias it.
    """

    period = select_baseline_seasonal_period(data_profile.frequency)
    budget = MAX_FEATURE_FRACTION * data_profile.span_index_length

    if period > 1 and period <= budget:
        offset = period
        explanation = (
            f"Baseline: seasonal naive, each step repeats the value observed "
            f"{offset} steps earlier (one seasonal period)."
        )
    else:
        offset = 1
        if period > 1:
            reason = (
                f"the seasonal period ({period}) spans more than "
                f"{MAX_FEATURE_FRACTION:.0%} of the observations"
            )
        else:
            reason = "no seasonal period is known for this frequency"
        explanation = (
            f"Baseline: naive, each step repeats the last observed value "
            f"({reason})."
        )

    return {"offset": offset, "n_offsets": 1}, explanation
