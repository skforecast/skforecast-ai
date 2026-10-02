# Unit test cv_as_executed recommendation/backtesting

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.recommendation.backtesting import cv_as_executed


@pytest.mark.parametrize(
    "forecaster",
    ["ForecasterRecursive", "ForecasterDirect", "ForecasterEquivalentDate", None],
    ids=lambda value: f"{value}",
)
def test_cv_as_executed_returns_same_object_when_forecaster_is_not_stats(forecaster):
    """
    Test that cv_as_executed returns the splitter itself, unchanged, for any
    forecaster other than ForecasterStats and when the forecaster is None
    (strategy shared by several forecasters).
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=60, refit=False)

    result = cv_as_executed(cv, forecaster)

    assert result is cv
    assert result.refit is False
    assert result.fixed_train_size is True


def test_cv_as_executed_returns_same_object_when_stats_refits_every_fold():
    """
    Test that cv_as_executed returns the splitter itself for
    ForecasterStats when `refit=True`, since that is what skforecast runs.
    """
    cv = TimeSeriesFold(
        steps=10, initial_train_size=60, refit=True, fixed_train_size=False
    )

    result = cv_as_executed(cv, "ForecasterStats")

    assert result is cv
    assert result.fixed_train_size is False


def test_cv_as_executed_returns_copy_when_stats_does_not_refit():
    """
    Test that for ForecasterStats with `refit=False` a copy with
    `refit=True` and `fixed_train_size=True` is returned (the window that
    runs when refit is off), and the input splitter is not modified.
    """
    cv = TimeSeriesFold(
        steps=10, initial_train_size=60, refit=False, fixed_train_size=False
    )

    result = cv_as_executed(cv, "ForecasterStats")

    assert result is not cv
    assert result.refit is True
    assert result.fixed_train_size is True
    assert result.steps == 10
    assert result.initial_train_size == 60
    assert cv.refit is False
    assert cv.fixed_train_size is False


def test_cv_as_executed_keeps_window_type_when_stats_refits_every_n_folds():
    """
    Test that for ForecasterStats with an integer `refit` other than 1 the
    copy has `refit=True` and keeps the `fixed_train_size` the user chose.
    """
    cv = TimeSeriesFold(
        steps=10, initial_train_size=60, refit=2, fixed_train_size=False
    )

    result = cv_as_executed(cv, "ForecasterStats")

    assert result is not cv
    assert result.refit is True
    assert result.fixed_train_size is False
    assert cv.refit == 2


def test_cv_as_executed_returns_same_object_when_stats_refit_is_one():
    """
    Test that an integer `refit=1` (equal to True) is already what runs, so
    the splitter itself is returned.
    """
    cv = TimeSeriesFold(steps=10, initial_train_size=60, refit=1)

    assert cv_as_executed(cv, "ForecasterStats") is cv


def test_cv_as_executed_treats_integer_zero_as_no_refit():
    """
    Test that `refit=0` (falsy) behaves like `refit=False` for
    ForecasterStats: a copy with `refit=True` and `fixed_train_size=True`.
    """
    cv = TimeSeriesFold(
        steps=10, initial_train_size=60, refit=0, fixed_train_size=False
    )

    result = cv_as_executed(cv, "ForecasterStats")

    assert result is not cv
    assert result.refit is True
    assert result.fixed_train_size is True
