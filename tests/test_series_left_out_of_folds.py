# Unit test series_left_out_of_folds

import pandas as pd
import pytest

from skforecast_ai._last_window import series_left_out_of_folds

from tests.fixtures_last_window import (
    cv_items_sales,
    data_long,
    long_starting_late,
    plan_long_foundation,
    plan_long_ridge,
    plan_single_ridge,
    profile_long,
    profile_single,
    data_single,
)

# The strategy of the fixtures has 12 test folds of 3 days on the 120 days of
# the items_sales data, starting at the positions 84, 87, ..., 117.
_SERIES = ["item_1", "item_2", "item_3"]


def _predictions(folds_of: dict) -> pd.DataFrame:
    """
    Return backtest predictions with the `level` and `fold` columns of
    skforecast, one row per series and fold of `folds_of`.
    """
    rows = [
        {"level": level, "fold": fold, "pred": 0.0}
        for level, folds in folds_of.items() for fold in folds
    ]
    return pd.DataFrame(rows)


def test_series_left_out_of_folds_output_when_a_fold_left_a_series_out():
    """
    Test that a series that the predictions leave out of a test fold where
    it has values is returned with the folds that forecast it and the folds
    where it has values (11 of 12), and that the others are not.
    """
    predictions = _predictions({
        "item_1": range(12), "item_2": range(1, 12), "item_3": range(12)
    })

    result = series_left_out_of_folds(
        data_long, profile_long, plan_long_ridge, cv_items_sales(), predictions
    )

    assert result == {"item_2": (11, 12)}


def test_series_left_out_of_folds_counts_only_folds_where_the_series_has_values():
    """
    Test that the folds where a series has no value to evaluate do not
    count: item_2 has its last 20 values (from position 100), so it has
    values in the 7 test folds from position 99; forecast in 6 of them, it
    is returned, and forecast in those 7 it is not, although the first 5
    folds do not forecast it.
    """
    data = long_starting_late(data_long, "item_2", 20)
    all_folds = {"item_1": range(12), "item_3": range(12)}

    left_out = series_left_out_of_folds(
        data, profile_long, plan_long_ridge, cv_items_sales(),
        _predictions({**all_folds, "item_2": range(6, 12)}),
    )
    complete = series_left_out_of_folds(
        data, profile_long, plan_long_ridge, cv_items_sales(),
        _predictions({**all_folds, "item_2": range(5, 12)}),
    )

    assert left_out == {"item_2": (6, 7)}
    assert complete == {}


def test_series_left_out_of_folds_output_when_foundation_on_several_series():
    """
    Test that a ForecasterFoundation model on several series is read as
    ForecasterRecursiveMultiSeries is: item_2, with values in the 7 last
    test folds, forecast in 6 of them.
    """
    data = long_starting_late(data_long, "item_2", 20)
    predictions = _predictions({
        "item_1": range(12), "item_2": range(6, 12), "item_3": range(12)
    })

    result = series_left_out_of_folds(
        data, profile_long, plan_long_foundation, cv_items_sales(), predictions
    )

    assert result == {"item_2": (6, 7)}


@pytest.mark.parametrize(
    "predictions",
    [None, pd.DataFrame({"pred": [0.0]}), pd.DataFrame({"level": ["item_1"]})],
    ids=["none", "without_level", "without_fold"],
)
def test_series_left_out_of_folds_empty_when_predictions_cannot_be_read(predictions):
    """
    Test that predictions without the `level` and `fold` columns of a
    backtest of several series give an empty result.
    """
    assert series_left_out_of_folds(
        data_long, profile_long, plan_long_ridge, cv_items_sales(), predictions
    ) == {}


def test_series_left_out_of_folds_empty_when_forecaster_is_not_multiseries():
    """
    Test that a plan of a single series is not read: its forecaster has no
    series to leave out of a fold.
    """
    predictions = pd.DataFrame({"pred": [0.0], "fold": [0]})

    assert series_left_out_of_folds(
        data_single, profile_single, plan_single_ridge, cv_items_sales(),
        predictions,
    ) == {}
