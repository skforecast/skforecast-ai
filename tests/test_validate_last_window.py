# Unit test validate_last_window

import re
import warnings

import numpy as np
import pandas as pd
import pytest

from skforecast.exceptions import MissingValuesWarning

from skforecast_ai import ForecastingAssistant
from skforecast_ai._last_window import (
    _missing_read,
    _read_positions,
    validate_last_window,
)
from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.execution.forecast_runner import render_forecast_script
from skforecast_ai.profiling.data_profile import _fmt_timestamp

from tests.fixtures_last_window import (
    data_long,
    data_single,
    data_wide,
    plan_long_foundation,
    plan_long_lgbm,
    plan_long_multivariate,
    plan_long_ridge,
    plan_single_baseline,
    plan_single_direct,
    plan_single_lgbm,
    plan_single_ridge,
    plan_wide_lgbm,
    plan_wide_multivariate,
    plan_wide_ridge,
    plans_single_without_lags,
    profile_long,
    profile_single,
    profile_wide,
    with_missing,
    with_missing_long,
)

def _final_rows_message(last: str, rows: str, where: str = "") -> str:
    """Return the message of the error for final rows without a target."""
    return (
        f"The data has no target value{where} after {last}: drop its last "
        f"{rows}, so that it ends with the last value of the target."
    )


def _ignored_rows_message(last: str, rows: str, where: str = "") -> str:
    """
    Return the message of the warning for final rows without a target that
    ForecasterRecursiveMultiSeries ignores.
    """
    return (
        f"The data has no target value{where} after {last}: "
        f"ForecasterRecursiveMultiSeries ignores its last {rows} and forecasts "
        f"the dates after {last}. Drop those rows to avoid this warning."
    )


_WEEKEND_ADVICE = (
    " Saturdays and Sundays never have a value: to forecast the business days, "
    "drop every Saturday and Sunday row instead, so that the data has a "
    "business-day frequency."
)


def _no_warning(data, profile, plan) -> None:
    """Run the check, failing on any warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        validate_last_window(data=data, profile=profile, plan=plan)


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (data_single, profile_single, plan_single_ridge),
        (data_single, profile_single, plan_single_baseline),
        (data_wide, profile_wide, plan_wide_ridge),
        (data_wide, profile_wide, plan_wide_multivariate),
        (data_long, profile_long, plan_long_ridge),
        (data_long, profile_long, plan_long_foundation),
    ],
    ids=["single", "baseline", "wide", "multivariate", "long", "long_foundation"],
)
def test_validate_last_window_no_error_when_target_complete(data, profile, plan):
    """
    Test that a target with a value at every date raises no error and gives
    no warning.
    """
    _no_warning(data, profile, plan)


@pytest.mark.parametrize(
    "plan",
    [
        plan_single_ridge,
        plan_single_lgbm,
        plan_single_direct,
        plan_single_baseline,
        plans_single_without_lags["stats"],
        plans_single_without_lags["foundation"],
    ],
    ids=["ridge", "lgbm", "direct", "baseline", "stats", "foundation"],
)
def test_validate_last_window_InvalidInputError_when_final_rows_without_target(
    plan,
):
    """
    Test that final rows without a target value (future rows appended to
    carry the exogenous variables) raise whatever the forecaster and the
    estimator: the forecast starts after them, from missing values.
    """
    data = with_missing(data_single, [1, 2])

    err_msg = re.escape(
        _final_rows_message("2023-02-27", "2 row(s) (2023-02-28 to 2023-03-01)")
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_last_window(data=data, profile=profile_single, plan=plan)
    assert exc_info.value.field == "data"


def test_validate_last_window_InvalidInputError_when_final_row_and_rows_unsorted():
    """
    Test that the final row is the last date, not the last row: rows out of
    date order are read in date order, as the generated code sorts them.
    """
    data = with_missing(data_single, [1]).sample(frac=1, random_state=0)

    err_msg = re.escape(_final_rows_message("2023-02-28", "1 row(s) (2023-03-01)"))
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile_single, plan=plan_single_ridge)


def test_validate_last_window_InvalidInputError_when_final_row_repeated():
    """
    Test that a final date repeated in identical rows without a target value
    raises: the generated code keeps the first of them.
    """
    future = data_single.iloc[[-1, -1]].assign(
        date=pd.Timestamp("2023-03-02"), y=np.nan
    )
    data = pd.concat([data_single, future], ignore_index=True)

    err_msg = re.escape(_final_rows_message("2023-03-01", "2 row(s) (2023-03-02)"))
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile_single, plan=plan_single_ridge)


def test_validate_last_window_InvalidInputError_when_final_rows_without_target_wide():
    """
    Test that, in wide format, final dates where no series has a value raise
    for ForecasterDirectMultiVariate, which forecasts after them.
    """
    data = data_wide.copy()
    data.iloc[-2:, :] = np.nan

    err_msg = re.escape(
        _final_rows_message("2012-04-27", "2 row(s) (2012-04-28 to 2012-04-29)")
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(
            data=data, profile=profile_wide, plan=plan_wide_multivariate
        )


def test_validate_last_window_InvalidInputError_when_final_rows_without_target_long():
    """
    Test that, in long format, final dates where no series has a value raise
    for a foundation model, which forecasts after them.
    """
    data = data_long.copy()
    data.loc[data["date"] >= "2012-04-28", "value"] = np.nan

    err_msg = re.escape(
        _final_rows_message(
            "2012-04-27", "6 row(s) (2012-04-28 to 2012-04-29)", " in any series"
        )
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile_long, plan=plan_long_foundation)


def test_validate_last_window_UserWarning_when_multiseries_final_rows_wide():
    """
    Test that, in wide format, final dates where no series has a value give a
    warning for ForecasterRecursiveMultiSeries: it drops them and forecasts
    the dates after the last value, as without them.
    """
    data = data_wide.copy()
    data.iloc[-2:, :] = np.nan

    warn_msg = re.escape(
        _ignored_rows_message("2012-04-27", "2 row(s) (2012-04-28 to 2012-04-29)")
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_last_window(data=data, profile=profile_wide, plan=plan_wide_ridge)


def test_validate_last_window_UserWarning_when_multiseries_final_rows_long():
    """
    Test that, in long format, final dates where no series has a value give a
    warning for ForecasterRecursiveMultiSeries, which drops them.
    """
    data = data_long.copy()
    data.loc[data["date"] >= "2012-04-28", "value"] = np.nan

    warn_msg = re.escape(
        _ignored_rows_message(
            "2012-04-27", "6 row(s) (2012-04-28 to 2012-04-29)", " in any series"
        )
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_last_window(data=data, profile=profile_long, plan=plan_long_ridge)


def test_validate_last_window_InvalidInputError_when_multiseries_final_rows_and_lag_reads_missing_value():
    """
    Test that, after ignoring the final rows, the window of
    ForecasterRecursiveMultiSeries ends on the last value and its missing
    values are checked: lag 5 reads the missing value of 'item_1' two dates
    before the last date with a value.
    """
    data = data_wide.copy()
    data.iloc[-2:, :] = np.nan
    data.iloc[-5, 0] = np.nan

    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict ('item_1': 1 "
        "value(s), such as '2012-04-25')."
    )
    with pytest.warns(UserWarning, match="ignores its last 2 row"):
        with pytest.raises(InvalidInputError, match=err_msg):
            validate_last_window(
                data=data, profile=profile_wide, plan=plan_wide_ridge
            )


def _weekend_profile(data: pd.DataFrame):
    """Profile `data`, whose PACF warns on the missing weekend values."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MissingValuesWarning)
        return ForecastingAssistant().profile(
            data, target="y", date_column="date"
        ).data_profile


def _weekend_data(last: str) -> pd.DataFrame:
    """
    Return daily data whose Saturdays and Sundays never have a value, ending
    on `last`.
    """
    dates = pd.date_range("2023-01-02", last, freq="D")
    y = 10.0 + np.sin(np.arange(len(dates)))
    y[dates.dayofweek >= 5] = np.nan
    return pd.DataFrame({"date": dates, "y": y})


def test_validate_last_window_InvalidInputError_advises_business_days_when_weekends_empty():
    """
    Test that final rows that are weekend days, in daily data whose weekends
    never have a value, raise with the advice to drop every weekend row:
    dropping only the final rows forecasts the weekend first.
    """
    data = _weekend_data("2023-03-05")
    profile = _weekend_profile(data)

    err_msg = re.escape(
        _final_rows_message("2023-03-03", "2 row(s) (2023-03-04 to 2023-03-05)")[:-1]
        + "." + _WEEKEND_ADVICE
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile, plan=plan_single_lgbm)


def test_validate_last_window_no_weekend_advice_when_a_weekend_has_value():
    """
    Test that the advice to drop every weekend row is not given when some
    weekend day of the data has a value.
    """
    data = _weekend_data("2023-03-05")
    data.loc[data["date"] == "2023-01-07", "y"] = 1.0
    profile = _weekend_profile(data)

    with pytest.raises(InvalidInputError) as exc_info:
        validate_last_window(data=data, profile=profile, plan=plan_single_lgbm)
    assert "Saturdays and Sundays" not in str(exc_info.value)


def test_validate_last_window_InvalidInputError_when_final_rows_without_dates():
    """
    Test that, without dates, the final rows are those at the end of the index.
    """
    data = data_single.drop(columns="date")
    profile = ForecastingAssistant().profile(data, target="y").data_profile

    err_msg = re.escape(_final_rows_message("index 57", "2 row(s) (index 58 to 59)"))
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(
            data    = with_missing(data, [1, 2]),
            profile = profile,
            plan    = plan_single_ridge,
        )


@pytest.mark.parametrize(
    "data, profile, plan",
    [
        (with_missing_long(data_long, "item_2", [1, 2]), profile_long, plan_long_ridge),
        (
            with_missing_long(data_long, "item_2", [1, 2]), profile_long,
            plan_long_foundation,
        ),
        (data_long[data_long.index != 239], profile_long, plan_long_ridge),
    ],
    ids=["multiseries_missing_values", "foundation", "multiseries_without_rows"],
)
def test_validate_last_window_no_error_when_series_ends_early(data, profile, plan):
    """
    Test that a series that ends before the others is not a final row of the
    data: the note "Series ending early" of the profile says that
    ForecasterRecursiveMultiSeries does not predict it.
    """
    _no_warning(data, profile, plan)


def test_validate_last_window_no_error_when_wide_series_ends_early():
    """
    Test that a wide series with missing values at the end, next to series
    with values, is not a final row: ForecasterRecursiveMultiSeries does not
    predict it, so the values its lags would read are not checked.
    """
    data = data_wide.copy()
    data.iloc[-2:, 1] = np.nan

    _no_warning(data, profile_wide, plan_wide_ridge)


@pytest.mark.parametrize(
    "plan, position, date",
    [
        (plan_single_ridge, 5, "2023-02-25"),
        (plan_single_ridge, 4, "2023-02-26"),
        (plan_single_direct, 5, "2023-02-25"),
    ],
    ids=["recursive_lag_5_step_1", "recursive_lag_5_step_2", "direct_lag_5"],
)
def test_validate_last_window_InvalidInputError_when_lag_reads_missing_value(
    plan, position, date
):
    """
    Test that a missing value that a lag reads raises with an estimator that
    does not tolerate missing values: Ridge gave missing predictions without
    an error.
    """
    data = with_missing(data_single, [position])

    err_msg = re.escape(
        f"The forecaster reads missing values of the target to predict ('y': 1 "
        f"value(s), such as '{date}'). {plan.forecaster} with Ridge cannot use "
        f"them, so its predictions would be missing: fill them in."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_last_window(data=data, profile=profile_single, plan=plan)
    assert exc_info.value.field == "data"


@pytest.mark.parametrize(
    "plan, position",
    [(plan_single_ridge, 2), (plan_single_direct, 4), (plan_single_ridge, 6)],
    ids=["recursive_not_a_lag", "direct_not_a_lag", "recursive_rolling_window"],
)
def test_validate_last_window_no_error_when_missing_value_not_read(plan, position):
    """
    Test that a missing value that no lag reads raises no error, as Ridge
    predicts finite values from it: the rolling statistics skip it
    (position 2, read by the rolling mean of 3), a direct forecaster reads
    lag 5 only at position 5, and position 6 is before the lags.
    """
    _no_warning(with_missing(data_single, [position]), profile_single, plan)


def test_validate_last_window_UserWarning_when_estimator_tolerates_missing_values():
    """
    Test that, with an estimator that tolerates missing values (LightGBM), a
    missing value that a lag reads gives a warning naming it, not an error.
    """
    data = with_missing(data_single, [5])

    warn_msg = re.escape(
        "The forecaster reads missing values of the target to predict ('y': 1 "
        "value(s), such as '2023-02-25'). LGBMRegressor treats them as missing "
        "values; check that they are meant to be missing."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_last_window(data=data, profile=profile_single, plan=plan_single_lgbm)


def test_validate_last_window_InvalidInputError_when_missing_timestamp_read():
    """
    Test that a missing date, which the generated code inserts as a missing
    value (`asfreq`), counts as a missing value when a lag reads it.
    """
    data = data_single.drop(index=data_single.index[-5])

    err_msg = re.escape("('y': 1 value(s), such as '2023-02-25')")
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile_single, plan=plan_single_ridge)


def test_validate_last_window_InvalidInputError_when_missing_value_without_dates():
    """
    Test that, without dates, the missing value is named by its index.
    """
    data = data_single.drop(columns="date")
    profile = ForecastingAssistant().profile(data, target="y").data_profile

    err_msg = re.escape("('y': 1 value(s), such as index 55)")
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(
            data    = with_missing(data, [5]),
            profile = profile,
            plan    = plan_single_ridge,
        )


@pytest.mark.parametrize("plan", [plan_single_ridge, plan_single_lgbm],
                         ids=["ridge", "lgbm"])
def test_validate_last_window_InvalidInputError_when_differentiation_reads_it(plan):
    """
    Test that a missing value the inverse of the differentiation reads (the
    last 2 values with order 2) raises whatever the estimator: the
    predictions would be missing with LightGBM too.
    """
    plan = plan.model_copy(update={"forecaster_kwargs": {
        **plan.forecaster_kwargs, "differentiation": 2,
    }})
    data = with_missing(data_single, [2])

    err_msg = re.escape("('y': 1 value(s), such as '2023-02-28').")
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        validate_last_window(data=data, profile=profile_single, plan=plan)
    if plan.estimator == "LGBMRegressor":
        assert str(exc_info.value).endswith(
            "The differentiation of ForecasterRecursive reads the last 2 value(s), "
            "so its predictions would be missing: fill them in."
        )


def test_validate_last_window_InvalidInputError_when_window_feature_all_missing():
    """
    Test that a window feature whose differenced values are all missing
    gives a missing predictor: with differentiation, a missing value at
    position 2 makes the 2 last differenced values missing, which a rolling
    mean of 2 reads, though no lag reads them.
    """
    plan = plan_single_ridge.model_copy(update={
        "steps": 1,
        "forecaster_kwargs": {
            **plan_single_ridge.forecaster_kwargs,
            "lags": [5],
            "window_features": [{"stats": ["mean"], "window_size": 2}],
            "differentiation": 1,
        },
    })
    data = with_missing(data_single, [2])

    err_msg = re.escape("('y': 1 value(s), such as '2023-02-28')")
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile_single, plan=plan)


@pytest.mark.parametrize("position", [7, 5], ids=["offset", "offset_step_3"])
def test_validate_last_window_InvalidInputError_when_equivalent_date_missing(
    position,
):
    """
    Test that ForecasterEquivalentDate raises for a missing value at an
    equivalent date it reads (positions 7, 6 and 5 for 3 steps with an
    offset of 7), which it repeats as a missing prediction.
    """
    data = with_missing(data_single, [position])

    err_msg = re.escape(
        "ForecasterEquivalentDate repeats them as missing predictions: fill "
        "them in."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(
            data    = data,
            profile = profile_single,
            plan    = plan_single_baseline,
        )


def test_validate_last_window_no_error_when_equivalent_date_not_read():
    """
    Test that ForecasterEquivalentDate raises no error for a missing value it
    does not read for 3 steps (position 3, an offset of 7).
    """
    _no_warning(with_missing(data_single, [3]), profile_single, plan_single_baseline)


@pytest.mark.parametrize("kind", ["stats", "foundation"])
def test_validate_last_window_InvalidInputError_when_no_lags_and_final_row(kind):
    """
    Test that ForecasterStats and a foundation model raise for a final row
    without a target value.
    """
    data = with_missing(data_single, [1])

    with pytest.raises(InvalidInputError, match=re.escape("has no target value")):
        validate_last_window(
            data    = data,
            profile = profile_single,
            plan    = plans_single_without_lags[kind],
        )


@pytest.mark.parametrize("position", [5, 30], ids=["lag", "before_window"])
@pytest.mark.parametrize("kind", ["stats", "foundation"])
def test_validate_last_window_no_error_when_no_lags_and_missing_value(kind, position):
    """
    Test that ForecasterStats (which fails on any missing value) and a
    foundation model (which takes them as they are) are only checked for
    final rows.
    """
    _no_warning(
        with_missing(data_single, [position]), profile_single,
        plans_single_without_lags[kind],
    )


_MISSING_ITEM_1 = re.escape(
    "The forecaster reads missing values of the target to predict ('item_1': 1 "
    "value(s), such as '2012-04-26')."
)
_MISSING_ITEM_2_LONG = re.escape(
    "The forecaster reads missing values of the target to predict (series "
    "'item_2': 1 value(s), such as '2012-04-26')."
)


def test_validate_last_window_InvalidInputError_when_wide_series_missing_value():
    """
    Test that, in wide format, the missing value read by a lag raises with
    Ridge, naming its series.
    """
    data = data_wide.copy()
    data.iloc[-4, 0] = np.nan

    with pytest.raises(InvalidInputError, match=_MISSING_ITEM_1):
        validate_last_window(data=data, profile=profile_wide, plan=plan_wide_ridge)


def test_validate_last_window_UserWarning_when_wide_series_missing_value():
    """
    Test that, in wide format, the missing value read by a lag gives a
    warning with LightGBM, naming its series.
    """
    data = data_wide.copy()
    data.iloc[-4, 0] = np.nan

    with pytest.warns(UserWarning, match=_MISSING_ITEM_1):
        validate_last_window(data=data, profile=profile_wide, plan=plan_wide_lgbm)


def test_validate_last_window_InvalidInputError_when_multivariate_series_ends_early():
    """
    Test that ForecasterDirectMultiVariate, which reads every series up to
    the last date, raises with Ridge for a series that ends early: its lags
    read the missing values at the end.
    """
    data = data_wide.copy()
    data.iloc[-2:, 1] = np.nan

    err_msg = re.escape(
        "('item_2': 1 value(s), such as '2012-04-29'). ForecasterDirectMultiVariate "
        "with Ridge cannot use them"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(
            data    = data,
            profile = profile_wide,
            plan    = plan_wide_multivariate,
        )


def test_validate_last_window_InvalidInputError_when_long_series_missing_value():
    """
    Test that, in long format, the missing value read by a lag raises with
    Ridge, naming its series.
    """
    data = with_missing_long(data_long, "item_2", [4])

    with pytest.raises(InvalidInputError, match=_MISSING_ITEM_2_LONG):
        validate_last_window(data=data, profile=profile_long, plan=plan_long_ridge)


def test_validate_last_window_UserWarning_when_long_series_missing_value():
    """
    Test that, in long format, the missing value read by a lag gives a
    warning with LightGBM, naming its series.
    """
    data = with_missing_long(data_long, "item_2", [4])

    with pytest.warns(UserWarning, match=_MISSING_ITEM_2_LONG):
        validate_last_window(data=data, profile=profile_long, plan=plan_long_lgbm)


def test_validate_last_window_InvalidInputError_when_long_series_misses_a_date():
    """
    Test that, in long format, a date missing from a series inside its
    window (inserted as a missing value when the series are reshaped) counts
    as a missing value.
    """
    rows = data_long.index[data_long["series"] == "item_3"]
    data = data_long.drop(index=rows[-4])

    err_msg = re.escape("(series 'item_3': 1 value(s), such as '2012-04-26')")
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile_long, plan=plan_long_ridge)


def test_validate_last_window_no_error_when_target_not_in_data():
    """
    Test that data without the target of the profile (a profile passed with
    other data) is not checked: the generated code fails on it.
    """
    data = data_single.rename(columns={"y": "other"})

    validate_last_window(data=data, profile=profile_single, plan=plan_single_ridge)


def test_validate_last_window_no_error_when_long_data_and_multivariate():
    """
    Test that long-format data with several series and
    ForecasterDirectMultiVariate, whose generated code fails on its own
    (its `level` is not a series), is left to that error.
    """
    data = data_long.copy()
    data.loc[data["date"] >= "2012-04-28", "value"] = np.nan

    validate_last_window(data=data, profile=profile_long, plan=plan_long_multivariate)


def _series_of_script(data, profile, plan) -> dict:
    """
    Run on `data` the statements of the generated forecast script that read
    the target, as `forecast()` injects it, and return each series.
    """
    rendered = render_forecast_script(profile=profile, plan=plan)
    lines = rendered.core.splitlines()
    stop = next(
        position for position, line in enumerate(lines)
        if line.startswith((
            "window_features = ", "calendar_features = ", "# Create forecaster",
            "series_cols = ",
        ))
    )
    namespace = {"data": data.copy()}
    exec(rendered.imports + "\n" + "\n".join(lines[:stop]), namespace)
    if "series_dict" in namespace:
        return namespace["series_dict"]
    targets = profile.target if isinstance(profile.target, list) else [profile.target]

    return {target: namespace["data"][target] for target in targets}


def _expected_from_script(series: dict, plan) -> str | None:
    """
    Return the missing values the predictions read, worked out on the series
    of the script and written as the message writes them, or None.
    """
    last_value = max(
        values.last_valid_index() for values in series.values()
        if values.notna().any()
    )
    positions, order, _ = _read_positions(
        plan, limit=max(len(values) for values in series.values())
    )
    found = []
    for name, values in series.items():
        if plan.forecaster == "ForecasterRecursiveMultiSeries":
            if values.last_valid_index() != last_value:
                continue
            values = values.loc[values.first_valid_index():]
        read, _ = _missing_read(
            values.isna().to_numpy()[::-1], positions, order, plan, inverse=True
        )
        if read:
            dates = ", ".join(
                repr(_fmt_timestamp(date))
                for date in sorted(values.index[-p] for p in read)
            )
            found.append(f"{name!r}: {len(read)} value(s), such as {dates}")

    return "; ".join(found) or None


_wide_missing = data_wide.copy()
_wide_missing.loc["2012-04-26":, "item_2"] = np.nan
_wide_missing.loc["2012-04-25", "item_1"] = np.nan


@pytest.mark.parametrize(
    "data, kwargs",
    [
        (with_missing(data_single, [5]).sample(frac=1, random_state=1), {}),
        (data_single.drop(index=[55, 57]), {}),
        (
            pd.concat([with_missing(data_single, [4]), data_single.iloc[[30]]]),
            {},
        ),
        (with_missing(data_single, [2, 5]), {"forecaster": "ForecasterDirect"}),
        (_wide_missing, {}),
        (
            with_missing_long(data_long, "item_1", [3])
            .drop(index=[355, 239])
            .sample(frac=1, random_state=2),
            {},
        ),
    ],
    ids=["shuffled", "missing_dates", "repeated_row", "direct", "wide",
         "long_shuffled_with_gap_and_early_series"],
)
def test_validate_last_window_dates_equal_those_of_generated_script(data, kwargs):
    """
    Test that the missing values reported are those of the series the
    generated forecast script builds from the data (sorted, without repeated
    rows, with the missing dates inserted, the series of long-format data
    reshaped), with the positions read worked out on them, so the check
    cannot drift from the script.
    """
    long_format = "series" in data.columns
    wide_format = "item_1" in data.columns
    assistant = ForecastingAssistant()
    # skforecast warns about the missing values when it profiles them and when
    # the script inserts the missing dates; nothing else may warn.
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        # The upstream numpy 2.5 deprecation ignored in pyproject.toml, which
        # "always" would record.
        warnings.filterwarnings(
            "ignore",
            message  = "The 'generic' unit for NumPy timedelta is deprecated",
            category = DeprecationWarning,
        )
        profile = assistant.profile(
            data,
            target           = (
                "value" if long_format else list(data.columns) if wide_format
                else "y"
            ),
            date_column      = None if wide_format else "date",
            series_id_column = "series" if long_format else None,
        )
        plan = assistant.plan(
            profile,
            estimator       = "Ridge",
            steps           = 3,
            lags            = [1, 5],
            window_features = [{"stats": ["mean"], "window_size": 3}],
            **kwargs,
        )
        expected = _expected_from_script(
            _series_of_script(data, profile.data_profile, plan), plan
        )

    assert {warning.category for warning in record} <= {MissingValuesWarning}
    assert expected is not None
    with pytest.raises(InvalidInputError) as exc_info:
        validate_last_window(data=data, profile=profile.data_profile, plan=plan)
    series = "series " if long_format else ""
    assert f"to predict ({series}{expected})." in str(exc_info.value)


def _with_kwargs(plan, steps=None, drop=(), **forecaster_kwargs):
    """Return `plan` with other forecaster arguments (and `steps`)."""
    kwargs = {
        key: value for key, value in plan.forecaster_kwargs.items() if key not in drop
    }
    update = {"forecaster_kwargs": {**kwargs, **forecaster_kwargs}}
    if steps is not None:
        update["steps"] = steps
    return plan.model_copy(update=update)


@pytest.mark.parametrize("data_format", ["wide", "long"])
def test_validate_last_window_UserWarning_when_window_feature_longer_than_lags(
    data_format,
):
    """
    Test that a window feature longer than the lags plus the differentiation
    is read over its whole window in long format as in wide format: item_3
    without the 2 dates before the last one, lags 1 and 2, a rolling mean of
    3 and differentiation 1 read both (it failed with IndexError in long
    format, or counted one of them).
    """
    kwargs = {
        "steps": 1, "lags": 2, "differentiation": 1, "drop": ("calendar_features",),
        "window_features": [{"stats": ["mean"], "window_size": 3}],
    }
    if data_format == "wide":
        data = data_wide.copy()
        data.iloc[[-3, -2], 2] = np.nan
        profile, plan = profile_wide, _with_kwargs(plan_wide_lgbm, **kwargs)
        found = "('item_3': 2 value(s), such as '2012-04-27', '2012-04-28')."
    else:
        rows = data_long.index[data_long["series"] == "item_3"]
        data = data_long.drop(index=rows[[-3, -2]])
        profile, plan = profile_long, _with_kwargs(plan_long_lgbm, **kwargs)
        found = "(series 'item_3': 2 value(s), such as '2012-04-27', '2012-04-28')."

    with pytest.warns(UserWarning, match=re.escape(found)):
        validate_last_window(data=data, profile=profile, plan=plan)


@pytest.mark.parametrize("plan", [plan_wide_multivariate, plan_wide_lgbm],
                         ids=["ridge", "lgbm"])
def test_validate_last_window_no_error_when_multivariate_differentiation_other_series(
    plan,
):
    """
    Test that ForecasterDirectMultiVariate with differentiation does not
    take the last value of a series other than its level (item_1) as read
    by the inverse of the differentiation: only the level is predicted, and
    lags 3 and 7 do not read it.
    """
    plan = _with_kwargs(
        plan, forecaster="ForecasterDirectMultiVariate", lags=[3, 7],
        differentiation=1, drop=("window_features",),
    ).model_copy(update={"forecaster": "ForecasterDirectMultiVariate"})
    data = data_wide.copy()
    data.iloc[-1, 1] = np.nan

    _no_warning(data, profile_wide, plan)


def test_validate_last_window_InvalidInputError_when_multivariate_level_last_missing():
    """
    Test that ForecasterDirectMultiVariate with differentiation raises for
    the last value of its level (item_1), which the inverse of the
    differentiation reads, also with LightGBM.
    """
    plan = _with_kwargs(
        plan_wide_lgbm, lags=[3, 7], differentiation=1, drop=("window_features",),
    ).model_copy(update={
        "forecaster": "ForecasterDirectMultiVariate", "task_type": "multivariate",
    })
    data = data_wide.copy()
    data.iloc[-1, 0] = np.nan

    err_msg = re.escape(
        "('item_1': 1 value(s), such as '2012-04-29'). The differentiation of "
        "ForecasterDirectMultiVariate reads the last 1 value(s)"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile_wide, plan=plan)


def test_validate_last_window_InvalidInputError_when_baseline_without_offset():
    """
    Test that a ForecasterEquivalentDate plan without `offset` is read with
    the offset of the generated code (1): with 2 offsets it reads positions
    1 and 2, so a missing value at position 2 raises.
    """
    plan = plan_single_baseline.model_copy(
        update={"forecaster_kwargs": {"n_offsets": 2}}
    )

    with pytest.raises(InvalidInputError, match=re.escape("repeats them as missing")):
        validate_last_window(
            data    = with_missing(data_single, [2]),
            profile = profile_single,
            plan    = plan,
        )


def test_validate_last_window_InvalidInputError_counts_final_rows_of_the_data():
    """
    Test that the final rows are the rows of the data after the last value,
    without the dates `asfreq` inserts between them (2023-03-02 is missing).
    """
    future = pd.DataFrame({
        "date": pd.to_datetime(["2023-03-03", "2023-03-04"]), "y": np.nan,
    })
    data = pd.concat([data_single, future], ignore_index=True)

    err_msg = re.escape(
        _final_rows_message("2023-03-01", "2 row(s) (2023-03-03 to 2023-03-04)")
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile_single, plan=plan_single_ridge)


def test_validate_last_window_InvalidInputError_names_integer_series_ids():
    """
    Test that integer series ids are written as numbers, not numpy reprs.
    """
    data = with_missing_long(data_long, "item_2", [4])
    data["series"] = data["series"].map({"item_1": 1, "item_2": 2, "item_3": 3})
    # skforecast warns about the missing value when profiling it.
    with pytest.warns(MissingValuesWarning):
        profile = ForecastingAssistant().profile(
            data, target="value", date_column="date", series_id_column="series"
        ).data_profile

    with pytest.raises(InvalidInputError, match=re.escape("(series 2: 1 value(s)")):
        validate_last_window(data=data, profile=profile, plan=plan_long_ridge)


def test_validate_last_window_InvalidInputError_lists_five_series_at_most():
    """
    Test that the message lists 5 series and counts the others.
    """
    ids = [f"s{number}" for number in range(7)]
    dates = pd.date_range("2023-01-01", periods=30, freq="D")
    data = pd.DataFrame({
        "date": np.tile(dates, len(ids)),
        "series": np.repeat(ids, len(dates)),
        "value": np.tile(np.arange(30.0) % 7, len(ids)),
    })
    data.loc[data["date"] == dates[-5], "value"] = np.nan
    # skforecast warns about the missing values when profiling them.
    with pytest.warns(MissingValuesWarning):
        profile = ForecastingAssistant().profile(
            data, target="value", date_column="date", series_id_column="series"
        ).data_profile

    err_msg = re.escape(
        "'s4': 1 value(s), such as '2023-01-26'; and 2 more series)."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile, plan=plan_long_ridge)


def test_validate_last_window_no_error_when_date_unreadable_with_saved_profile():
    """
    Test that a date the generated code cannot read (data passed with the
    profile of other data) is left to the error of the generated code.
    """
    data = data_single.assign(date=data_single["date"].dt.strftime("%Y-%m-%d"))
    data.loc[data.index[-1], "date"] = "not a date"

    validate_last_window(data=data, profile=profile_single, plan=plan_single_ridge)


def test_validate_last_window_no_error_when_window_feature_huge():
    """
    Test that a plan with a window feature far longer than the data is
    checked over the data only (skforecast fails on it on its own).
    """
    plan = _with_kwargs(
        plan_single_ridge, window_features=[{"stats": ["mean"], "window_size": 10**7}]
    )

    validate_last_window(
        data    = with_missing(data_single, [30]),
        profile = profile_single,
        plan    = plan,
    )


@pytest.mark.parametrize(
    "data, profile_data, kwargs",
    [
        (
            data_single.set_index(pd.period_range("2023-01", periods=60, freq="M"))
            .drop(columns="date"),
            None, {"target": "y"},
        ),
        (
            data_single.drop(columns="date").set_index(pd.Index(np.arange(0, 120, 2))),
            None, {"target": "y"},
        ),
        (
            data_long.set_index("date"), data_long,
            {"target": "value", "date_column": "date", "series_id_column": "series"},
        ),
    ],
    ids=["period_index", "integer_index", "long_dates_in_index"],
)
def test_validate_last_window_no_error_when_layout_unreadable_by_script(
    data, profile_data, kwargs
):
    """
    Test that data the generated code cannot read (a PeriodIndex, an
    integer index that is not a RangeIndex, long-format data with its dates
    in the index) is left to the error of the generated code, even with
    final rows without a target.
    """
    profile = ForecastingAssistant().profile(
        profile_data if profile_data is not None else data, **kwargs
    ).data_profile
    data = data.copy()
    data.iloc[-1, data.columns.get_loc(kwargs["target"])] = np.nan
    plan = plan_long_ridge if profile.data_format == "long" else plan_single_ridge

    validate_last_window(data=data, profile=profile, plan=plan)


def test_validate_last_window_InvalidInputError_when_multivariate_single_target():
    """
    Test that ForecasterDirectMultiVariate on a single target takes it as
    its level (as the generated code does), so the inverse of the
    differentiation reads its last values, also with LightGBM.
    """
    plan = _with_kwargs(plan_single_lgbm, differentiation=2).model_copy(
        update={"forecaster": "ForecasterDirectMultiVariate"}
    )

    with pytest.raises(InvalidInputError, match=re.escape("The differentiation of")):
        validate_last_window(
            data    = with_missing(data_single, [2]),
            profile = profile_single,
            plan    = plan,
        )


def test_validate_last_window_InvalidInputError_names_column_of_single_long_series():
    """
    Test that a single series in long format, read as wide data, is named by
    its target column, not as a series id.
    """
    item_1 = data_long[data_long["series"] == "item_1"]
    profile = ForecastingAssistant().profile(
        item_1, target="value", date_column="date", series_id_column="series"
    ).data_profile
    data = with_missing_long(item_1, "item_1", [4])
    plan = plan_single_ridge.model_copy()

    err_msg = re.escape("to predict ('value': 1 value(s), such as '2012-04-26').")
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile, plan=plan)


def test_validate_last_window_no_error_when_final_row_off_grid_has_value():
    """
    Test that a final row off the grid of the frequency that has a value (data
    passed with a saved profile), which the generated code drops (`asfreq`),
    is not taken for a final row without a target value.
    """
    future = pd.DataFrame({"date": [pd.Timestamp("2023-03-01 12:00")], "y": [9.0]})
    data = pd.concat([data_single, future], ignore_index=True)

    _no_warning(data, profile_single, plan_single_ridge)


def test_validate_last_window_no_error_when_long_row_off_grid_has_value():
    """
    Test that, in long format, a row off the grid of the frequency (data
    passed with a saved profile), which the reshape of the series drops,
    neither moves the last date nor makes a series of it.
    """
    future = pd.DataFrame({
        "date": [pd.Timestamp("2012-04-29 12:00")], "series": ["item_2"],
        "value": [21.0],
    })
    data = pd.concat([data_long, future], ignore_index=True)

    _no_warning(data, profile_long, plan_long_ridge)


def test_validate_last_window_InvalidInputError_when_last_row_off_grid():
    """
    Test that a last row off the grid of the frequency (data passed with a
    saved profile), which makes `asfreq` end the target with a date without
    a value (2023-03-02), raises, naming that row to drop.
    """
    future = pd.DataFrame({"date": [pd.Timestamp("2023-03-02 12:00")], "y": [9.0]})
    data = pd.concat([data_single, future], ignore_index=True)

    err_msg = re.escape(
        _final_rows_message("2023-03-01", "1 row(s) (2023-03-02 12:00:00)")
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(data=data, profile=profile_single, plan=plan_single_lgbm)


def test_validate_last_window_InvalidInputError_when_wide_last_row_off_grid():
    """
    Test that, in wide format, a last row off the grid of the frequency ends
    every series without a value on the grid: ForecasterRecursiveMultiSeries
    ignores it with a warning, instead of taking every series for one that
    ends early, and the lags of item_1 then read its missing value.
    """
    future = pd.DataFrame(
        {"item_1": [1.0], "item_2": [2.0], "item_3": [3.0]},
        index=pd.DatetimeIndex(["2012-04-30 12:00"], name="date"),
    )
    data = pd.concat([data_wide, future])
    data.iloc[-4, 0] = np.nan

    warn_msg = re.escape(
        _ignored_rows_message("2012-04-29", "1 row(s) (2012-04-30 12:00:00)")
    )
    err_msg = re.escape(
        "The forecaster reads missing values of the target to predict ('item_1': 1 "
        "value(s), such as '2012-04-27')."
    )
    with pytest.warns(UserWarning, match=warn_msg):
        with pytest.raises(InvalidInputError, match=err_msg):
            validate_last_window(
                data=data, profile=profile_wide, plan=plan_wide_ridge
            )


def test_validate_last_window_UserWarning_when_long_series_starts_off_grid():
    """
    Test that, in long format, each series is put on the grid of its own first
    date (as `asfreq` does in `reshape_series_long_to_dict`): a row off the
    grid at the start of item_2 does not hide the final dates without a value
    of the other series.
    """
    stray = pd.DataFrame({
        "date": [pd.Timestamp("2011-12-31 12:00")], "series": ["item_2"],
        "value": [21.0],
    })
    future = pd.DataFrame({
        "date": np.repeat(pd.date_range("2012-04-30", periods=3, freq="D"), 3),
        "series": ["item_1", "item_2", "item_3"] * 3,
        "value": np.nan,
    })
    data = pd.concat([data_long, stray, future], ignore_index=True)

    warn_msg = re.escape(
        _ignored_rows_message(
            "2012-04-29", "9 row(s) (2012-04-30 to 2012-05-02)", " in any series"
        )
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_last_window(data=data, profile=profile_long, plan=plan_long_ridge)


def test_validate_last_window_UserWarning_when_long_repeated_date_first_empty():
    """
    Test that, of a repeated date of a series, the first row is the one read
    (as the generated code drops the others): an empty first row and a value
    in the second leave the date without a value.
    """
    future = pd.DataFrame({
        "date": pd.to_datetime(["2012-04-30", "2012-04-30"]),
        "series": ["item_1", "item_1"],
        "value": [np.nan, 5.0],
    })
    data = pd.concat([data_long, future], ignore_index=True)

    warn_msg = re.escape(
        _ignored_rows_message("2012-04-29", "2 row(s) (2012-04-30)", " in any series")
    )
    with pytest.warns(UserWarning, match=warn_msg):
        validate_last_window(data=data, profile=profile_long, plan=plan_long_ridge)


def test_validate_last_window_InvalidInputError_when_only_differentiation_reads():
    """
    Test that, with Ridge, a missing value read only by the inverse of the
    differentiation names the differentiation, not the estimator: any
    estimator gives missing predictions.
    """
    plan = _with_kwargs(
        plan_single_ridge, steps=1, lags=[4], differentiation=2,
        drop=("window_features",),
    )

    err_msg = re.escape(
        "The differentiation of ForecasterRecursive reads the last 2 value(s)"
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        validate_last_window(
            data    = with_missing(data_single, [2]),
            profile = profile_single,
            plan    = plan,
        )
