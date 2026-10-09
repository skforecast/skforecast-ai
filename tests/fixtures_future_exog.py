# Fixtures for the checks of the future exogenous variables

import numpy as np
import pandas as pd

from skforecast_ai import ForecastingAssistant

from tests.fixtures_assistant import df_categorical_exog
from tests.fixtures_datasets import df_items_sales_long

_assistant = ForecastingAssistant()


def _profile_and_plans(data, estimators, **kwargs):
    """
    Profile `data` and plan 7 steps with each estimator (a ForecasterFoundation
    model for "ForecasterFoundation").
    """
    profile = _assistant.profile(data, **kwargs)
    plans = [
        _assistant.plan(profile, steps=7, forecaster=estimator)
        if estimator == "ForecasterFoundation"
        else _assistant.plan(profile, steps=7, estimator=estimator)
        for estimator in estimators
    ]
    return profile.data_profile, plans


# --- Daily data with a date column, a numeric and a categorical exog ---
# Last date 2023-04-10; the 7 dates to forecast are 2023-04-11 to 2023-04-17.
data_daily = df_categorical_exog
profile_daily, (plan_daily_ridge, plan_daily_lgbm) = _profile_and_plans(
    data_daily, ["Ridge", "LGBMRegressor"], target="sales", date_column="date"
)
_future_dates = pd.date_range("2023-04-11", periods=7, freq="D")
exog_daily = pd.DataFrame(
    {
        "promo": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        "weekday": _future_dates.day_name(),
    },
    index=_future_dates,
)

# Plans of other forecasters for the daily data: ForecasterStats leaves the
# categorical column out, and so does TabICL, a foundation model that only
# takes numeric covariates.
_profile_daily_full = _assistant.profile(
    data_daily, target="sales", date_column="date"
)
plans_daily_by_forecaster = {
    "direct": _assistant.plan(
        _profile_daily_full, steps=7, forecaster="ForecasterDirect"
    ),
    "stats": _assistant.plan(
        _profile_daily_full, steps=7, forecaster="ForecasterStats"
    ),
    "foundation": _assistant.plan(
        _profile_daily_full, steps=7, forecaster="ForecasterFoundation"
    ),
    "foundation_numeric": _assistant.plan(
        _profile_daily_full, steps=7, forecaster="ForecasterFoundation",
        estimator="soda-inria/tabicl",
    ),
    # A baseline reads no exogenous variables, even with `use_exog` set.
    "baseline": _assistant.plan(
        _profile_daily_full, steps=7, forecaster="ForecasterEquivalentDate"
    ).model_copy(update={"use_exog": True}),
}

# A profile of the daily data that leaves `weekday` out (`exog_columns`), and
# the plan of a foundation model, which takes every covariate it is given.
_profile_daily_promo = _assistant.profile(
    data_daily, target="sales", date_column="date", exog_columns=["promo"]
)
profile_daily_promo = _profile_daily_promo.data_profile
plan_daily_promo_foundation = _assistant.plan(
    _profile_daily_promo, steps=7, forecaster="ForecasterFoundation"
)

# --- Long data with a numeric exog (items_sales, last date 2012-04-29) ---
data_long = df_items_sales_long.assign(
    price=np.arange(len(df_items_sales_long)) % 7 + 1.0
)
profile_long, (plan_long_ridge,) = _profile_and_plans(
    data_long, ["Ridge"], target="value", date_column="date",
    series_id_column="series",
)
_long_dates = pd.date_range("2012-04-30", periods=7, freq="D")
exog_long = pd.DataFrame(
    {
        "series": np.repeat(["item_1", "item_2", "item_3"], 7),
        "date": np.tile(_long_dates, 3),
        "price": np.tile(np.arange(7) + 1.0, 3),
    }
)

# --- Long data whose series item_3 ends on 2012-04-26, three days early ---
data_long_early = data_long[
    (data_long["series"] != "item_3") | (data_long["date"] <= "2012-04-26")
]
profile_long_early, (plan_long_early_ridge, plan_long_early_foundation) = (
    _profile_and_plans(
        data_long_early, ["Ridge", "ForecasterFoundation"], target="value",
        date_column="date", series_id_column="series",
    )
)
# item_3 from the date after its own last date, the others as in exog_long.
exog_long_early = pd.concat(
    [
        exog_long[exog_long["series"] != "item_3"],
        exog_long[exog_long["series"] == "item_3"].assign(
            date=pd.date_range("2012-04-27", periods=7, freq="D")
        ),
    ],
    ignore_index=True,
)

# --- Business-day data indexed by date (last date Friday 2023-03-24) ---
data_business = pd.DataFrame(
    {"y": np.arange(60.0) % 5, "x": np.arange(60.0) % 3},
    index=pd.bdate_range("2023-01-02", periods=60),
)
profile_business, (plan_business, plan_business_lgbm) = _profile_and_plans(
    data_business, ["Ridge", "LGBMRegressor"], target="y"
)
# Calendar days from Saturday 2023-03-25: the weekends are dropped by asfreq.
exog_calendar_days = pd.DataFrame(
    {"x": np.arange(11.0)},
    index=pd.date_range("2023-03-25", periods=11, freq="D"),
)

# --- The business-day data without dates (RangeIndex 0 to 59) ---
data_range = data_business.reset_index(drop=True)
profile_range, (plan_range_ridge,) = _profile_and_plans(
    data_range, ["Ridge"], target="y"
)
exog_range = pd.DataFrame({"x": np.arange(7.0)}, index=pd.RangeIndex(60, 67))

# --- One series in long format: read as wide data by ForecasterRecursive ---
data_long_single = data_long[data_long["series"] == "item_1"]
profile_long_single, (plan_long_single,) = _profile_and_plans(
    data_long_single, ["Ridge"], target="value", date_column="date",
    series_id_column="series",
)

# --- Wide multi-series data whose last two rows have no target value ---
# The last date with a value is 2012-04-27, so ForecasterRecursiveMultiSeries
# forecasts from 2012-04-28; the rows of 2012-04-28 and 29 hold only `price`.
data_wide = data_long.pivot(index="date", columns="series", values="value").assign(
    price=np.arange(120) % 7 + 1.0
).rename_axis(columns=None).asfreq("D")
data_wide.iloc[-2:, :3] = np.nan
profile_wide, (plan_wide_ridge,) = _profile_and_plans(
    data_wide, ["Ridge"], target=["item_1", "item_2", "item_3"]
)
exog_wide = pd.DataFrame(
    {"price": np.arange(7) + 1.0},
    index=pd.date_range("2012-04-28", periods=7, freq="D"),
)

# --- Daily time zone aware data ending on a daylight saving time change ---
# skforecast forecasts from the last date plus 24 hours: 2021-03-29 01:00.
data_dst = pd.DataFrame(
    {"y": np.arange(60.0) % 5, "x": np.arange(60.0) % 3},
    index=pd.date_range(end="2021-03-28", periods=60, freq="D", tz="Europe/Madrid"),
)
profile_dst, (plan_dst,) = _profile_and_plans(data_dst, ["Ridge"], target="y")
exog_dst = pd.DataFrame(
    {"x": np.arange(7.0)},
    index=pd.date_range(
        data_dst.index[-1] + pd.offsets.Day(), periods=7, freq="D"
    ),
)

# --- Business-hour data (last date 2020-02-21 12:00) ---
data_bh = pd.DataFrame(
    {"y": np.arange(300.0) % 7, "x": np.arange(300.0) % 3},
    index=pd.date_range("2020-01-01 09:00", periods=300, freq="bh"),
)
profile_bh, (plan_bh,) = _profile_and_plans(data_bh, ["Ridge"], target="y")
# Every calendar hour of the 7 business hours to forecast, closes included.
_bh_dates = pd.date_range(
    data_bh.index[-1] + pd.offsets.BusinessHour(), periods=7, freq="bh"
)
exog_bh = pd.DataFrame(
    {"x": 1.0}, index=pd.date_range(_bh_dates[0], _bh_dates[-1], freq="h")
)

# --- The wide data with a category only in the rows without target ---
data_wide_kind = data_wide.assign(kind=np.where(np.arange(120) % 2, "a", "b"))
data_wide_kind.iloc[-2:, data_wide_kind.columns.get_loc("kind")] = "zz"
profile_wide_kind, (plan_wide_kind,) = _profile_and_plans(
    data_wide_kind, ["Ridge"], target=["item_1", "item_2", "item_3"]
)

# --- The same data with two rows without target and the category 'closed' ---
# Rows inside the target values, so the encoder of
# ForecasterRecursiveMultiSeries is fitted on them and knows 'closed'.
data_wide_closed = data_wide_kind.copy()
_closed = data_wide_closed.index.isin(pd.date_range("2012-03-01", periods=2))
data_wide_closed.loc[_closed, ["item_1", "item_2", "item_3"]] = np.nan
data_wide_closed.loc[_closed, "kind"] = "closed"
