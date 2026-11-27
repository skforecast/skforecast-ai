# Unit test _describe_error_by_step execution/backtesting_runner

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.execution.backtesting_runner import _describe_error_by_step

HEADER = "Mean absolute error by step of the horizon (error_by_step)"


def _frame(rows: list[tuple]) -> pd.DataFrame:
    """Build `error_by_step` from `(level, step, error)` tuples."""
    return pd.DataFrame(rows, columns=["level", "step", "mean_absolute_error"])


# Tests: _describe_error_by_step: nothing to describe


@pytest.mark.parametrize(
    "error_by_step",
    [
        None,
        pd.DataFrame({"step": [1, 2], "other": [1.0, 2.0]}),
        pd.DataFrame({"step": [], "mean_absolute_error": []}),
        pd.DataFrame({"step": [1, 2], "mean_absolute_error": [np.nan, np.nan]}),
        pd.DataFrame({"step": [1, 2], "mean_absolute_error": [None, None]}),
        _frame([("a", 1, np.nan), ("b", 1, np.nan)]),
    ],
    ids=["None", "no error column", "empty", "all NaN", "all None", "all NaN series"],
)
def test_describe_error_by_step_returns_None_when_there_is_nothing_to_describe(
    error_by_step,
):
    """
    Test that `_describe_error_by_step` returns None when the table is missing,
    has no `mean_absolute_error` column, is empty or has every error missing.
    """
    assert _describe_error_by_step(error_by_step) is None


# Tests: _describe_error_by_step: a single series


def test_describe_error_by_step_single_series_lists_every_step_with_4_decimals():
    """
    Test that a table without `level` is listed step by step, sorted by step
    and with 4 decimals, and says nothing about the number of steps shown.
    """
    error_by_step = pd.DataFrame(
        {"step": [3, 1, 2], "mean_absolute_error": [2.25, 1.0, 1.23456]}
    )

    result = _describe_error_by_step(error_by_step)

    assert result == (
        f"{HEADER}: step 1: 1.0000, step 2: 1.2346, step 3: 2.2500."
    )


def test_describe_error_by_step_single_series_with_exactly_12_steps_shows_all():
    """
    Test that a table of exactly 12 steps (`MAX_SUMMARY_STEPS`) lists all of
    them and does not add the count of steps shown.
    """
    error_by_step = pd.DataFrame(
        {"step": range(1, 13), "mean_absolute_error": np.arange(1, 13) * 0.5}
    )

    result = _describe_error_by_step(error_by_step)

    assert result == (
        f"{HEADER}: step 1: 0.5000, step 2: 1.0000, step 3: 1.5000, "
        f"step 4: 2.0000, step 5: 2.5000, step 6: 3.0000, step 7: 3.5000, "
        f"step 8: 4.0000, step 9: 4.5000, step 10: 5.0000, step 11: 5.5000, "
        f"step 12: 6.0000."
    )


def test_describe_error_by_step_single_series_with_more_than_12_steps_spreads_them():
    """
    Test that with more than 12 steps, 12 of them are named, spread evenly
    from the first to the last (1, 3, 5, 7, 9, 11, 14, 16, 18, 20, 22 and 24
    of 24), and the sentence says how many are shown.
    """
    error_by_step = pd.DataFrame(
        {"step": range(1, 25), "mean_absolute_error": np.arange(1, 25) * 0.5}
    )

    result = _describe_error_by_step(error_by_step)

    assert result == (
        f"{HEADER} (12 of 24 steps shown): step 1: 0.5000, step 3: 1.5000, "
        f"step 5: 2.5000, step 7: 3.5000, step 9: 4.5000, step 11: 5.5000, "
        f"step 14: 7.0000, step 16: 8.0000, step 18: 9.0000, step 20: 10.0000, "
        f"step 22: 11.0000, step 24: 12.0000."
    )


def test_describe_error_by_step_single_level_is_listed_like_one_series():
    """
    Test that a table with a `level` column that holds a single level (the
    multivariate case) is listed step by step, as for one series, without
    the name of the level.
    """
    error_by_step = _frame([("a", 2, 3.0), ("a", 1, 1.5)])

    result = _describe_error_by_step(error_by_step)

    assert result == f"{HEADER}: step 1: 1.5000, step 2: 3.0000."


def test_describe_error_by_step_drops_NaN_errors():
    """
    Test that a step whose error is NaN is left out of the list, and that the
    steps of the count are those that remain.
    """
    error_by_step = pd.DataFrame(
        {"step": [1, 2, 3], "mean_absolute_error": [1.0, np.nan, 3.0]}
    )

    result = _describe_error_by_step(error_by_step)

    assert result == f"{HEADER}: step 1: 1.0000, step 3: 3.0000."


# Tests: _describe_error_by_step: several series


def test_describe_error_by_step_several_series_with_same_first_and_last_step():
    """
    Test that several series with the same first and last step name the steps
    once in the header and give the error of each series at them.
    """
    error_by_step = _frame([
        ("a", 1, 1.0), ("a", 2, 2.0), ("a", 3, 3.0),
        ("b", 1, 0.5), ("b", 2, 0.75), ("b", 3, 1.25),
    ])

    result = _describe_error_by_step(error_by_step)

    assert result == (
        f"{HEADER} of each series, at steps 1 and 3: a: 1.0000 and 3.0000; "
        f"b: 0.5000 and 1.2500."
    )


def test_describe_error_by_step_several_series_with_a_single_step():
    """
    Test that several series whose first and last step is the same one are
    described at that one step.
    """
    error_by_step = _frame([("a", 1, 1.0), ("b", 1, 0.5)])

    result = _describe_error_by_step(error_by_step)

    assert result == f"{HEADER} of each series, at step 1: a: 1.0000; b: 0.5000."


def test_describe_error_by_step_more_than_5_series_names_the_first_5():
    """
    Test that with more than 5 series (`MAX_SUMMARY_SERIES`) only the first 5,
    in order of appearance, are named, and the header says how many there are.
    """
    rows = [
        (f"s{i}", step, float(i + step))
        for i in range(7)
        for step in (1, 2)
    ]

    result = _describe_error_by_step(_frame(rows))

    assert result == (
        f"{HEADER} of the first 5 of 7 series, at steps 1 and 2: "
        f"s0: 1.0000 and 2.0000; s1: 2.0000 and 3.0000; "
        f"s2: 3.0000 and 4.0000; s3: 4.0000 and 5.0000; "
        f"s4: 5.0000 and 6.0000."
    )


def test_describe_error_by_step_series_with_different_steps_gives_each_its_steps():
    """
    Test that when the first or last step differs between series, each series
    gives its error with the step it belongs to, and a series with a single
    step gives it once.
    """
    error_by_step = _frame([
        ("a", 1, 1.0), ("a", 2, 2.0), ("a", 3, 3.0),
        ("b", 1, 0.5), ("b", 2, 0.75),
        ("c", 4, 2.0),
    ])

    result = _describe_error_by_step(error_by_step)

    assert result == (
        f"{HEADER}, at the first and the last step of each series: "
        f"a: 1.0000 at step 1 and 3.0000 at step 3; "
        f"b: 0.5000 at step 1 and 0.7500 at step 2; "
        f"c: 2.0000 at step 4."
    )


def test_describe_error_by_step_steps_of_series_beyond_the_first_5_are_not_compared():
    """
    Test that the steps of a series after the first 5 do not change how the
    first 5 are described: they share the steps, so the header names them once.
    """
    rows = [(f"s{i}", step, 1.0) for i in range(5) for step in (1, 2)]
    rows += [("s5", 1, 1.0), ("s5", 9, 1.0)]

    result = _describe_error_by_step(_frame(rows))

    assert result == (
        f"{HEADER} of the first 5 of 6 series, at steps 1 and 2: "
        f"s0: 1.0000 and 1.0000; s1: 1.0000 and 1.0000; "
        f"s2: 1.0000 and 1.0000; s3: 1.0000 and 1.0000; "
        f"s4: 1.0000 and 1.0000."
    )


def test_describe_error_by_step_several_series_drops_NaN_errors_and_empty_series():
    """
    Test that NaN errors are dropped before describing several series: a
    series with every error missing is not named, and the first or last step
    of another is the first or last one that has a value.
    """
    error_by_step = _frame([
        ("a", 1, np.nan), ("a", 2, 2.0), ("a", 3, 3.0),
        ("b", 1, np.nan), ("b", 2, np.nan),
        ("c", 2, 0.5), ("c", 3, 1.5), ("c", 4, np.nan),
    ])

    result = _describe_error_by_step(error_by_step)

    assert result == (
        f"{HEADER} of each series, at steps 2 and 3: a: 2.0000 and 3.0000; "
        f"c: 0.5000 and 1.5000."
    )
