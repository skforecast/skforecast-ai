################################################################################
#                       Recommendations: baseline                              #
#                                                                              #
# Deterministic configuration of the ForecasterEquivalentDate baseline         #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from .._constants import MAX_FEATURE_FRACTION
from ..schemas import DataProfile
from .autoregressive import estimate_seasonality


def select_baseline_config(
    data_profile: DataProfile,
) -> tuple[dict[str, int], str]:
    """
    Select the `ForecasterEquivalentDate` configuration used as baseline.

    The baseline is a seasonal naive forecast: each step repeats the value
    observed one seasonal period earlier. The offset is the primary
    seasonal period implied by the frequency. It falls back to a naive
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

    seasonalities = estimate_seasonality(data_profile.frequency)
    period = seasonalities[0] if seasonalities else 1
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
