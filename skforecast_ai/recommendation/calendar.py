################################################################################
#                       Recommendations: Calendar features                     #
#                                                                              #
# Calendar features selection rules                                            #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from datetime import timedelta
import pandas as pd
from skforecast.preprocessing import CalendarFeatures
from .._constants import TREE_BASED_ESTIMATORS
from ..exceptions import InvalidInputError
from ..schemas import DataProfile

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
        raise InvalidInputError(
            f"Unsupported calendar encoding {encoding!r}. Only None and "
            f"'cyclical' are generated.",
            field = "forecaster_kwargs",
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


# Shortest span over which each calendar feature changes value (a month is
# at least 28 days, a quarter 90, a year 365). A feature whose span is
# shorter than a step of the data is finer than its frequency.
# Written with `datetime.timedelta`: numpy 2.5 deprecates the unit pandas
# 2.3 reads a text such as '1h' with.
_FEATURE_SPANS = {
    "second": timedelta(seconds=1),
    "minute": timedelta(minutes=1),
    "hour": timedelta(hours=1),
    "day_of_week": timedelta(days=1),
    "day_of_month": timedelta(days=1),
    "day_of_year": timedelta(days=1),
    "weekend": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=28),
    "quarter": timedelta(days=90),
    "year": timedelta(days=365),
}

# Dates of the grid on which the calendar features are computed, at most.
_MAX_GRID_DATES = 1000


def constant_calendar_features(
    features: list[str],
    data_profile: DataProfile,
) -> list[str]:
    """
    Calendar features finer than the frequency of the data whose column
    takes a single value on the dates of the data, such as `'hour'` on
    daily data, `'day_of_week'` on weekly data or `'weekend'` on business
    days.

    `CalendarFeatures` computes them without an error, and the model gets a
    constant column it learns nothing from. The values are computed with
    `CalendarFeatures` on the regular grid of the data (from
    `span_start_date`, at `frequency`, in its time zone, up to 1000 dates).
    A feature coarser than the frequency that is constant only because the
    data are short (`'year'` on a few months) is not listed.

    Parameters
    ----------
    features : list of str
        Calendar features chosen for the plan.
    data_profile : DataProfile
        Profile of the data.

    Returns
    -------
    constant : list of str
        Features of `features`, in their order, that are finer than the
        frequency and constant on the grid. Empty when the grid cannot be
        built (no frequency, fewer than two dates, a start or a zone pandas
        rejects).
    """

    periods = min(data_profile.span_index_length, _MAX_GRID_DATES)
    if (
        not features
        or data_profile.frequency is None
        or data_profile.span_start_date is None
        or periods < 2
    ):
        return []
    try:
        start = pd.Timestamp(data_profile.span_start_date)
        if data_profile.time_zone is not None:
            # The first date is written as local time; a profile saved
            # by an earlier build wrote it with its UTC offset when it was
            # not midnight. Either way the grid is built in the zone,
            # across its changes of time, as the dates of the data are.
            start = (
                start.tz_localize(data_profile.time_zone)
                if start.tzinfo is None
                else start.tz_convert(data_profile.time_zone)
            )
        grid = pd.date_range(
            start   = start,
            periods = periods,
            freq    = data_profile.frequency,
        )
        values = CalendarFeatures(
            features = list(features),
            encoding = None,
        ).fit_transform(pd.DataFrame(index=grid))
    except Exception:
        # The warning is advice: a grid that cannot be rebuilt (a local
        # midnight that does not exist, a zone or dates pandas rejects)
        # leaves it out, and the plan is built as before.
        return []
    step = (grid[1] - grid[0]).to_pytimedelta()
    # Business days step by a day and never reach a weekend.
    without_weekend = grid.dayofweek.max() < 5

    return [
        feature for feature in features
        if feature in _FEATURE_SPANS
        and (
            _FEATURE_SPANS[feature] < step
            or (feature == "weekend" and without_weekend)
        )
        and values[feature].nunique(dropna=False) == 1
    ]
