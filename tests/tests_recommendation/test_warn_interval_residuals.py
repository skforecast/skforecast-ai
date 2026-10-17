# Unit test warn_interval_residuals

import re

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation import warn_interval_residuals

from skforecast_ai.schemas import SeriesLengthInfo

from .fixtures_recommendation import (
    plan_h2o_interval_baseline,
    plan_h2o_interval_direct,
    plan_h2o_interval_recursive,
    plan_h2o_interval_stats,
    plan_h2o_no_interval,
    plan_h2o_staggered_interval,
    plan_h2o_wide_interval_multiseries,
    plan_h2o_wide_interval_multivariate,
    plan_h2o_wide_staggered_interval,
    profile_h2o_complete,
    profile_h2o_staggered,
    profile_h2o_wide,
    profile_h2o_wide_staggered,
)


def _create_strategy(plan, cv, data_profile):
    """Stand in for `create_cv()`, the caller of `warn_interval_residuals`."""
    warn_interval_residuals(plan, cv, data_profile)


def _cv(steps, initial_train_size):
    return TimeSeriesFold(
        steps              = steps,
        initial_train_size = initial_train_size,
        fold_stride        = 1,
        refit              = False,
        verbose            = False,
    )


def _message(n_rows, n_train, window_size, features=True, level=""):
    advice = ", or fewer lags or smaller window features" if features else ""
    return re.escape(
        f"The first training window of the strategy leaves {n_rows} row(s) to "
        f"train on{level} ({n_train} observations for a window size of "
        f"{window_size}), so the prediction intervals are estimated from "
        f"{n_rows} residual(s). skforecast spreads them over up to 10 bins, "
        f"and below 10 residuals per bin (100 rows) the intervals tend to be "
        f"too narrow; with a single residual in a bin the lower bound equals "
        f"the upper one. Read them with caution, or use a later "
        f"`initial_train_size`{advice}."
    )


@pytest.mark.parametrize(
    "plan, steps, n_train, n_rows, window_size, features",
    [
        (plan_h2o_interval_recursive, 1, 40, 4, 36, True),
        (plan_h2o_interval_recursive, 1, 37, 1, 36, True),
        (plan_h2o_interval_recursive, 1, 135, 99, 36, True),
        (plan_h2o_interval_direct, 3, 40, 2, 36, True),
        (plan_h2o_interval_direct, 3, 137, 99, 36, True),
        (plan_h2o_interval_baseline, 1, 50, 38, 12, False),
        (plan_h2o_interval_baseline, 1, 111, 99, 12, False),
    ],
    ids=[
        "recursive_4_rows",
        "recursive_1_row",
        "recursive_99_rows",
        "direct_2_rows",
        "direct_99_rows",
        "baseline_38_rows",
        "baseline_99_rows",
    ],
)
def test_warn_interval_residuals_UserWarning_when_few_training_rows(
    plan, steps, n_train, n_rows, window_size, features
):
    """
    Test that a plan with bootstrapped (lag forecasters) or conformal
    (baseline) intervals whose first training window leaves 1 to 99 rows
    warns, attributed to the caller of the caller of the helper (the caller
    of `create_cv()`). A direct forecaster loses `steps - 1` more rows, and
    the baseline message does not advise fewer lags.
    """
    warn_msg = _message(n_rows, n_train, window_size, features)
    with pytest.warns(UserWarning, match=warn_msg) as record:
        _create_strategy(plan, _cv(steps, n_train), profile_h2o_complete)

    assert len(record) == 1
    assert record[0].filename == __file__


def test_warn_interval_residuals_UserWarning_when_conformal_lag_forecaster():
    """
    Test that a lag forecaster with conformal intervals warns as with
    bootstrapped ones.
    """
    plan = plan_h2o_interval_recursive.model_copy(
        update={"interval_method": "conformal"}
    )

    with pytest.warns(UserWarning, match=_message(4, 40, 36)):
        _create_strategy(plan, _cv(1, 40), profile_h2o_complete)


@pytest.mark.parametrize(
    "plan, steps, n_train",
    [
        (plan_h2o_interval_recursive, 1, 136),
        (plan_h2o_interval_recursive, 1, 150),
        (plan_h2o_interval_recursive, 1, 36),
        (plan_h2o_interval_recursive, 1, 20),
        (plan_h2o_interval_direct, 3, 138),
        (plan_h2o_interval_direct, 3, 38),
        (plan_h2o_interval_baseline, 1, 112),
        (plan_h2o_interval_baseline, 1, 12),
        (plan_h2o_no_interval, 1, 40),
        (plan_h2o_interval_stats, 1, 40),
    ],
    ids=[
        "100_rows",
        "many_rows",
        "no_rows",
        "window_shorter_than_forecaster",
        "direct_100_rows",
        "direct_no_rows",
        "baseline_100_rows",
        "baseline_no_rows",
        "no_interval",
        "stats",
    ],
)
def test_warn_interval_residuals_no_warning_when_no_case(plan, steps, n_train):
    """
    Test that there is no warning (warnings are errors in this suite) with 100
    rows or more, when the window leaves no rows (`warn_first_window` reports
    it), without interval and for a forecaster with native intervals.
    """
    _create_strategy(plan, _cv(steps, n_train), profile_h2o_complete)


def test_warn_interval_residuals_no_warning_when_strategy_cannot_be_split():
    """
    Test that a strategy that cannot be split on the data returns without
    warning (`build_cv()` reports it).
    """
    _create_strategy(
        plan_h2o_interval_recursive, _cv(1, 500), profile_h2o_complete
    )


def _series_message(scope, shown):
    return re.escape(
        f"The first training window of the strategy leaves fewer than 100 rows "
        f"to train on in {scope} ({shown}), for a window size of 36. "
        f"skforecast estimates the prediction intervals of each series from "
        f"the residuals of its own rows, spread over up to 10 bins, and below "
        f"10 residuals per bin (100 rows) the intervals tend to be too narrow; "
        f"with a single residual in a bin the lower bound equals the upper "
        f"one. Read the intervals of those series with caution, or use a "
        f"later `initial_train_size`, or fewer lags or smaller window features."
    )


def _without_encoding(plan):
    kwargs = {**plan.forecaster_kwargs, "encoding": None}
    return plan.model_copy(update={"forecaster_kwargs": kwargs})


@pytest.mark.parametrize(
    "n_train, n_rows",
    [(40, 4), (135, 99)],
    ids=["4_rows", "99_rows"],
)
def test_warn_interval_residuals_UserWarning_when_several_series_have_few_rows(
    n_train, n_rows
):
    """
    Test that a ForecasterRecursiveMultiSeries plan on two series in wide
    format, whose first training window leaves 1 to 99 rows of each, warns
    naming both series, attributed to the caller of `create_cv()`.
    """
    shown = (
        f"'a': {n_rows} row(s) of {n_train} observations; "
        f"'b': {n_rows} row(s) of {n_train} observations"
    )
    warn_msg = _series_message("all 2 series", shown)
    with pytest.warns(UserWarning, match=warn_msg) as record:
        _create_strategy(
            plan_h2o_wide_interval_multiseries, _cv(1, n_train), profile_h2o_wide
        )

    assert len(record) == 1
    assert record[0].filename == __file__


@pytest.mark.parametrize(
    "n_train, scope, shown",
    [
        (
            80,
            "all 2 series",
            "'b': 24 row(s) of 60 observations; 'a': 44 row(s) of 80 observations",
        ),
        (140, "1 of the 2 series", "'b': 84 row(s) of 120 observations"),
        (40, "1 of the 2 series", "'a': 4 row(s) of 40 observations"),
    ],
    ids=["both_fewest_first", "later_series", "later_series_without_rows"],
)
@pytest.mark.parametrize(
    "plan, profile",
    [
        (plan_h2o_staggered_interval, profile_h2o_staggered),
        (plan_h2o_wide_staggered_interval, profile_h2o_wide_staggered),
    ],
    ids=["long", "wide"],
)
def test_warn_interval_residuals_UserWarning_when_series_starts_later(
    n_train, scope, shown, plan, profile
):
    """
    Test that the rows of each series are counted on its own observations in
    the first training window: the series 'b', which starts 20 observations
    after the span (its first rows in long format, its first values in wide
    format), has 20 fewer. The series with fewest rows come first, those
    with 100 or more are not named, and a series without rows in the window
    (not trained in it) is left out.
    """
    with pytest.warns(UserWarning, match=_series_message(scope, shown)):
        _create_strategy(plan, _cv(1, n_train), profile)


@pytest.mark.parametrize(
    "n_train, n_rows",
    [(40, 2), (137, 99)],
    ids=["2_rows", "99_rows"],
)
def test_warn_interval_residuals_UserWarning_when_direct_multivariate(
    n_train, n_rows
):
    """
    Test that a ForecasterDirectMultiVariate plan warns for its level, the
    only series it predicts and keeps residuals of, losing `steps - 1` rows
    as a direct forecaster.
    """
    warn_msg = _message(
        n_rows, n_train, 36,
        level = " for 'a', the only series ForecasterDirectMultiVariate predicts",
    )
    with pytest.warns(UserWarning, match=warn_msg) as record:
        _create_strategy(
            plan_h2o_wide_interval_multivariate, _cv(3, n_train), profile_h2o_wide
        )

    assert len(record) == 1
    assert record[0].filename == __file__


def test_warn_interval_residuals_UserWarning_when_series_pooled_without_encoding():
    """
    Test that a ForecasterRecursiveMultiSeries plan with `encoding=None`, whose
    residuals skforecast pools across the series, counts the rows of every
    series together.
    """
    warn_msg = re.escape(
        "The first training window of the strategy leaves 68 row(s) to train "
        "on across its 2 series ('a': 34 row(s) of 70 observations; 'b': 34 "
        "row(s) of 70 observations), for a window size of 36. With "
        "`encoding=None` skforecast estimates the prediction intervals of "
        "every series from the residuals of all of them together, spread over "
        "up to 10 bins, and below 10 residuals per bin (100 rows) the "
        "intervals tend to be too narrow; with a single residual in a bin the "
        "lower bound equals the upper one. Read them with caution, or use a "
        "later `initial_train_size`, or fewer lags or smaller window features."
    )
    with pytest.warns(UserWarning, match=warn_msg) as record:
        _create_strategy(
            _without_encoding(plan_h2o_wide_interval_multiseries),
            _cv(1, 70),
            profile_h2o_wide,
        )

    assert len(record) == 1
    assert record[0].filename == __file__


def test_warn_interval_residuals_UserWarning_names_five_series_and_counts_the_rest():
    """
    Test that the warning names the first five series with few rows and
    counts the others.
    """
    names = [f"s{i}" for i in range(7)]
    info = profile_h2o_wide.series_lengths["a"]
    data_profile = profile_h2o_wide.model_copy(
        update={
            "n_series": 7,
            "target": names,
            "series_lengths": {
                name: SeriesLengthInfo(**info.model_dump()) for name in names
            },
        }
    )
    shown = "; ".join(f"'s{i}': 4 row(s) of 40 observations" for i in range(5))
    warn_msg = _series_message("all 7 series", f"{shown}; and 2 more series")
    with pytest.warns(UserWarning, match=warn_msg):
        _create_strategy(plan_h2o_wide_interval_multiseries, _cv(1, 40), data_profile)


@pytest.mark.parametrize(
    "plan, profile, steps, n_train",
    [
        (plan_h2o_wide_interval_multiseries, profile_h2o_wide, 1, 136),
        (plan_h2o_wide_interval_multiseries, profile_h2o_wide, 1, 36),
        (plan_h2o_staggered_interval, profile_h2o_staggered, 1, 156),
        (plan_h2o_wide_staggered_interval, profile_h2o_wide_staggered, 1, 156),
        (
            _without_encoding(plan_h2o_wide_interval_multiseries),
            profile_h2o_wide,
            1,
            86,
        ),
        (plan_h2o_wide_interval_multivariate, profile_h2o_wide, 3, 138),
        (plan_h2o_wide_interval_multivariate, profile_h2o_wide, 3, 38),
    ],
    ids=[
        "multiseries_100_rows",
        "multiseries_no_rows",
        "later_series_100_rows",
        "later_wide_series_100_rows",
        "pooled_100_rows",
        "multivariate_100_rows",
        "multivariate_no_rows",
    ],
)
def test_warn_interval_residuals_no_warning_when_series_have_enough_rows(
    plan, profile, steps, n_train
):
    """
    Test that there is no warning with several series when every series has
    100 rows or more (all of them together with `encoding=None`, 50 each), or
    when the window leaves no rows of any series.
    """
    _create_strategy(plan, _cv(steps, n_train), profile)
