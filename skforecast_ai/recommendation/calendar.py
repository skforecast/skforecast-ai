"""Calendar features selection rules."""

from __future__ import annotations

from .._constants import TREE_BASED_ESTIMATORS

# Calendar feature selection. `MIN_OBS_CALENDAR` is the smallest series length
# worth adding calendar features to. `CALENDAR_FEATURE_RELEVANCE` maps a
# normalized frequency base to its recommended calendar features. The map is
# restricted to the features `skforecast.preprocessing.CalendarFeatures` supports: 
# year, month, week, day_of_week, day_of_month, day_of_year, weekend, hour, minute, 
# second, quarter. Yearly frequencies are intentionally absent: they have no 
# sub-year seasonality, so no calendar feature is recommended.
MIN_OBS_CALENDAR = 30
CALENDAR_FEATURE_RELEVANCE: dict[str, list[str]] = {
    "T":   ["hour", "minute", "day_of_week", "weekend"],
    "MIN": ["hour", "minute", "day_of_week", "weekend"],
    "H":   ["hour", "day_of_week", "weekend"],
    "B":   ["day_of_week", "month"],
    "D":   ["day_of_week", "weekend", "month"],
    "W":   ["week", "month"],
    "MS":  ["month", "quarter"],
    "ME":  ["month", "quarter"],
    "M":   ["month", "quarter"],
    "QS":  ["quarter"],
    "QE":  ["quarter"],
    "Q":   ["quarter"],
}

# Approximate number of observations in a calendar year for each sub-daily
# frequency base. Sub-daily frequencies capture intraday and weekly patterns
# but, by default, no annual one. When a series spans enough full years
# (`MIN_YEARS_FOR_ANNUAL`), `month` is appended so strong annual seasonality
# (energy demand, traffic, web load, ...) can be modeled without overfitting
# short, sub-annual histories.
OBS_PER_YEAR: dict[str, int] = {
    "T":   525_600,  # 60 * 24 * 365
    "MIN": 525_600,  # 60 * 24 * 365
    "H":   8_760,    # 24 * 365
}
MIN_YEARS_FOR_ANNUAL = 2


def select_calendar_features(
    task_type: str,
    frequency: str | None,
    n_observations: int,
) -> list[str] | None:
    """
    Select the recommended calendar features for a series.

    The recommendation depends only on the index frequency and the series
    length, so it is forecaster- and estimator-invariant (the encoding is
    chosen later, in the plan stage). The returned names are passed to a
    `skforecast.preprocessing.CalendarFeatures` instance via the
    forecaster's `calendar_features` parameter (delegated calendar
    features, skforecast 0.23.0).

    Parameters
    ----------
    task_type : str
        Forecasting task type implied by the chosen forecaster. Calendar
        features are only generated for the machine-learning task types.
    frequency : str, None
        Pandas frequency string used to look up the recommended feature
        set. When None (no datetime index / frequency could not be
        inferred), no calendar features are recommended.
    n_observations : int
        Number of observations available (per series).

    Returns
    -------
    calendar_features : list of str, None
        Recommended calendar feature names (a subset of those supported by
        `CalendarFeatures`). None when the task is statistical/foundation,
        the frequency is unknown, the series is too short, or the
        frequency has no sub-period seasonality (e.g. yearly).

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`.

    The frequency is normalized the same way as `estimate_seasonality`
    (uppercased, anchor suffix dropped) so anchored offsets such as
    `'W-SUN'`, `'QS-OCT'` and multiplied frequencies such as `'30min'` or
    `'2h'` resolve to the same recommendation as their base unit.

    For sub-daily frequencies the base recommendation only captures intraday
    and weekly patterns. When the series spans at least `MIN_YEARS_FOR_ANNUAL`
    full years (estimated from `OBS_PER_YEAR`), `month` is appended so annual
    seasonality can also be modeled.
    """

    if task_type in ("statistical", "foundation"):
        return None

    if frequency is None:
        return None

    if n_observations < MIN_OBS_CALENDAR:
        return None

    freq_upper = frequency.upper().split("-")[0]

    for key, recommended in CALENDAR_FEATURE_RELEVANCE.items():
        if freq_upper == key or freq_upper.endswith(key):
            features = list(recommended)
            if (
                key in OBS_PER_YEAR
                and "month" not in features
                and n_observations >= MIN_YEARS_FOR_ANNUAL * OBS_PER_YEAR[key]
            ):
                features.append("month")
            return features

    return None


def select_calendar_encoding(
    estimator: str | None,
    task_type: str,
) -> str | None:
    """
    Choose the calendar feature encoding based on estimator type.

    Tree-based models split on raw ordinal values natively and are most
    memory-efficient with unencoded integer calendar features, so no
    encoding is applied. Other models (linear, SVM, KNN, neural networks)
    benefit from the smooth, continuous representation of cyclical
    (sine/cosine) encoding.

    Parameters
    ----------
    estimator : str, None
        Name of the scikit-learn compatible estimator.
    task_type : str
        Forecasting task category.

    Returns
    -------
    encoding : str, None
        `None` for tree-based estimators (raw ordinal calendar features),
        `'cyclical'` otherwise.

    Notes
    -----
    Source: `skforecast_ai/skills/feature-engineering/SKILL.md`.

    `'year'` and `'weekend'` are never encoded by `CalendarFeatures`
    regardless of this setting.

    """

    if task_type in ("statistical", "foundation"):
        return None
    if estimator in TREE_BASED_ESTIMATORS:
        return None
    
    return "cyclical"
