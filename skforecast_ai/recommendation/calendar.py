################################################################################
#                       Recommendations: Calendar features                     #
#                                                                              #
# Calendar features selection rules                                            #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

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

    if task_type in ("statistical", "foundation", "baseline"):
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

    if task_type in ("statistical", "foundation", "baseline"):
        return None
    if estimator in TREE_BASED_ESTIMATORS:
        return None
    
    return "cyclical"


# Features that `CalendarFeatures` turns into `<name>_sin` and `<name>_cos`
# columns under cyclical encoding (the keys of skforecast's default
# `max_values`); `'year'` and `'weekend'` always stay as raw columns.
# `tests_recommendation/test_calendar.py` checks it against skforecast.
CYCLICAL_ENCODABLE_FEATURES = frozenset({
    "month",
    "week",
    "day_of_week",
    "day_of_month",
    "day_of_year",
    "hour",
    "minute",
    "second",
    "quarter",
})


def calendar_feature_names_out(
    features: list[str],
    encoding: str | None,
) -> dict[str, list[str]]:
    """
    Name the columns `CalendarFeatures` creates for each calendar feature.

    Parameters
    ----------
    features : list of str
        Calendar feature names, as passed to `CalendarFeatures`.
    encoding : str, None
        Calendar encoding chosen by `select_calendar_encoding`: None (raw
        ordinal values) or `'cyclical'`.

    Returns
    -------
    names_out : dict
        Mapping of each feature to the output column names it creates.

    Notes
    -----
    Any other encoding raises a `ValueError`: the plan only generates None
    and `'cyclical'`, and a new encoding needs its naming added here.
    """

    if encoding not in (None, "cyclical"):
        raise ValueError(
            f"Unsupported calendar encoding {encoding!r}. Only None and "
            f"'cyclical' are generated."
        )

    names_out = {}
    for feature in features:
        if encoding == "cyclical" and feature in CYCLICAL_ENCODABLE_FEATURES:
            names_out[feature] = [f"{feature}_sin", f"{feature}_cos"]
        else:
            names_out[feature] = [feature]

    return names_out


def drop_colliding_calendar_features(
    features: list[str],
    encoding: str | None,
    exog_columns: list[str],
) -> tuple[list[str], list[str]]:
    """
    Leave out the calendar features whose columns already exist as exog.

    skforecast raises an error when two predictors share a name, so a
    calendar feature that would create a column named like an exogenous
    variable (for example `'month'` with raw encoding when the data has a
    `month` column) is skipped and the user's column is used instead.

    Parameters
    ----------
    features : list of str
        Calendar feature names recommended by the profile.
    encoding : str, None
        Calendar encoding chosen by `select_calendar_encoding`.
    exog_columns : list of str
        Names of the exogenous columns used by the plan.

    Returns
    -------
    kept : list of str
        Features whose output columns do not collide, in input order.
    skipped : list of str
        Features left out because at least one of their output columns is
        an exogenous column, in input order.
    """

    exog = set(exog_columns)
    names_out = calendar_feature_names_out(features, encoding)

    kept = []
    skipped = []
    for feature in features:
        if exog.intersection(names_out[feature]):
            skipped.append(feature)
        else:
            kept.append(feature)

    return kept, skipped
