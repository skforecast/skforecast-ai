# Unit test _read_positions

import numpy as np
import pytest
from sklearn.linear_model import Ridge

from skforecast.direct import ForecasterDirect
from skforecast.exceptions import MissingValuesWarning
from skforecast.preprocessing import RollingFeatures
from skforecast.recursive import ForecasterEquivalentDate, ForecasterRecursive

from skforecast_ai._last_window import _missing_read, _read_positions

from tests.fixtures_last_window import (
    data_single,
    plan_single_baseline,
    plan_single_direct,
    plan_single_ridge,
    plans_single_without_lags,
)

_y = data_single.set_index("date")["y"].asfreq("D")


def _plan(plan, steps, **forecaster_kwargs):
    """Return `plan` with other `steps` and forecaster arguments."""
    return plan.model_copy(
        update={"steps": steps, "forecaster_kwargs": forecaster_kwargs}
    )


@pytest.mark.parametrize(
    "plan, expected",
    [
        (plan_single_ridge, ([1, 3, 4, 5], 0, 5)),
        (plan_single_direct, ([1, 5], 0, 5)),
        (plan_single_baseline, ([5, 6, 7], 0, 7)),
        (plans_single_without_lags["stats"], ([], 0, 0)),
        (plans_single_without_lags["foundation"], ([], 0, 0)),
        (_plan(plan_single_ridge, 1, lags=3), ([1, 2, 3], 0, 3)),
        (_plan(plan_single_ridge, 3, lags=[12]), ([10, 11, 12], 0, 12)),
        (_plan(plan_single_ridge, 3, lags=[1, 5], differentiation=1),
         ([1, 2, 3, 4, 5, 6], 1, 6)),
        (_plan(plan_single_direct, 3, lags=[3], differentiation=1),
         ([3, 4], 1, 4)),
        (_plan(plan_single_baseline, 10, offset=3, n_offsets=2),
         ([1, 2, 3, 4, 5, 6], 0, 6)),
        (_plan(plan_single_baseline, 3, n_offsets=2), ([1, 2], 0, 2)),
    ],
    ids=["recursive", "direct", "baseline", "stats", "foundation", "lags_int",
         "steps_below_lag", "differentiation", "direct_differentiation",
         "baseline_n_offsets", "baseline_default_offset"],
)
def test_read_positions_output(plan, expected):
    """
    Test the positions of the last window (1 is the last value) whose
    missing values the lags read, the order of the differentiation and the
    size of the window: lag `k` of a recursive forecaster reads positions
    `k - steps + 1` to `k`, a direct one position `k`, the differentiation
    the next `order` values too, ForecasterEquivalentDate its equivalent
    dates (offset 1 when the plan has none, as the generated code), and the
    forecasters without lags none.
    """
    positions, order, size = _read_positions(plan, limit=1000)

    np.testing.assert_array_equal(positions, np.array(expected[0], dtype=int))
    assert order == expected[1]
    assert size == expected[2]


def test_read_positions_output_when_window_longer_than_limit():
    """
    Test that the window is cut at `limit` (the length of the longest
    series), so a plan with a huge lag or window feature costs no more than
    the data: skforecast fails on a series shorter than its window.
    """
    plan = _plan(
        plan_single_ridge, 3, lags=[12],
        window_features=[{"stats": ["mean"], "window_size": 10**7}],
    )

    positions, order, size = _read_positions(plan, limit=11)

    np.testing.assert_array_equal(positions, np.array([10, 11]))
    assert (order, size) == (0, 11)


def test_read_positions_output_when_lags_int_huge():
    """
    Test that an integer `lags` far longer than the data is read up to the
    window only (it would build the whole list of lags otherwise).
    """
    plan = _plan(plan_single_ridge, 3, lags=10**9)

    positions, order, size = _read_positions(plan, limit=4)

    np.testing.assert_array_equal(positions, np.array([1, 2, 3, 4]))
    assert (order, size) == (0, 4)


def test_read_positions_output_when_n_offsets_huge():
    """
    Test that a ForecasterEquivalentDate plan with a huge `n_offsets` is read
    up to the window only.
    """
    plan = _plan(plan_single_baseline, 3, offset=7, n_offsets=10**9)

    positions, order, size = _read_positions(plan, limit=10)

    np.testing.assert_array_equal(positions, np.array([5, 6, 7]))
    assert (order, size) == (0, 10)


@pytest.mark.parametrize("direct", [False, True], ids=["recursive", "direct"])
@pytest.mark.parametrize(
    "lags, windows, differentiation, steps",
    [
        ([1, 5], [3], None, 3),
        ([2, 6], [], None, 2),
        ([3], [2], 1, 1),
        ([1, 4], [2, 5], 2, 4),
        ([7], [], 1, 8),
    ],
)
def test_read_positions_output_equals_skforecast_missing_predictions(
    direct, lags, windows, differentiation, steps
):
    """
    Test that a missing value at a position gives missing predictions with
    Ridge in skforecast exactly when the position is read (the positions of
    `_read_positions` and the window features of `_missing_read`), for
    recursive and direct forecasters, so the check cannot drift from
    skforecast.
    """
    plan = _plan(
        plan_single_direct if direct else plan_single_ridge,
        steps,
        lags            = lags,
        window_features = [
            {"stats": ["mean"], "window_size": size} for size in windows
        ],
        differentiation = differentiation,
    )
    positions, order, size = _read_positions(plan, limit=len(_y))

    for position in range(1, size + 2):
        missing_window = np.arange(1, size + 2) == position
        read, _ = _missing_read(missing_window, positions, order, plan, inverse=True)
        y = _y.copy()
        y.iloc[-position] = np.nan
        kwargs = {
            "estimator": Ridge(),
            "lags": lags,
            "window_features": RollingFeatures(
                stats=["mean"] * len(windows), window_sizes=windows
            ) if windows else None,
            "differentiation": differentiation,
            "dropna_from_series": True,
        }
        forecaster = (
            ForecasterDirect(steps=steps, **kwargs) if direct
            else ForecasterRecursive(**kwargs)
        )
        # skforecast warns about the missing value the test inserts.
        with pytest.warns(MissingValuesWarning):
            forecaster.fit(y=y)
            predictions = forecaster.predict(steps=steps)

        assert (read == [position]) == bool(predictions.isna().any()), position


@pytest.mark.parametrize(
    "offset, n_offsets, steps",
    [(7, 1, 3), (3, 2, 4), (3, 3, 1), (1, 2, 5)],
)
def test_read_positions_output_equals_skforecast_equivalent_date(
    offset, n_offsets, steps
):
    """
    Test that a missing value gives a missing prediction of
    ForecasterEquivalentDate exactly at the positions read.
    """
    plan = _plan(plan_single_baseline, steps, offset=offset, n_offsets=n_offsets)
    positions, _, _ = _read_positions(plan, limit=len(_y))

    for position in range(1, offset * n_offsets + 2):
        y = _y.copy()
        y.iloc[-position] = np.nan
        forecaster = ForecasterEquivalentDate(offset=offset, n_offsets=n_offsets)
        # skforecast warns about the missing value the test inserts.
        with pytest.warns(MissingValuesWarning):
            forecaster.fit(y=y)
            predictions = forecaster.predict(steps=steps)

        assert (position in positions) == bool(predictions.isna().any()), position
