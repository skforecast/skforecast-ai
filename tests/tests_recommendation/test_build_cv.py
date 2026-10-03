# Unit test build_cv recommendation/backtesting

import re

import pandas as pd
import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai.exceptions import InvalidInputError, InvalidInputTypeError
from skforecast_ai.recommendation.backtesting import build_cv

from tests.tests_recommendation.fixtures_recommendation import (
    profile_single_daily_100,
)


def _make_cv_params(initial_train_size, steps: int = 10) -> dict:
    """Build a resolved CV parameter dict around `initial_train_size`."""
    return {
        "steps": steps,
        "initial_train_size": initial_train_size,
        "refit": True,
        "fixed_train_size": False,
        "gap": 0,
        "fold_stride": None,
        "skip_folds": None,
        "allow_incomplete_fold": True,
        "differentiation": None,
    }


def test_build_cv_ValueError_when_initial_train_size_bool():
    """
    Test that a boolean initial_train_size is rejected instead of being
    read by TimeSeriesFold as the integer 1.
    """
    err_msg = re.escape(
        "`initial_train_size` must be an int, a float in (0, 1), a date "
        "string or a pandas Timestamp, got True."
    )
    with pytest.raises(ValueError, match=err_msg):
        build_cv(_make_cv_params(True), profile_single_daily_100)


@pytest.mark.parametrize("value", [0.0, 1.0, -0.1, 1.5], ids=lambda v: f"{v}")
def test_build_cv_ValueError_when_initial_train_size_float_out_of_range(value):
    """
    Test that a float initial_train_size outside the open interval (0, 1)
    raises ValueError.
    """
    err_msg = re.escape(
        f"initial_train_size as float must satisfy 0 < value < 1, got {value}."
    )
    with pytest.raises(ValueError, match=err_msg):
        build_cv(_make_cv_params(value), profile_single_daily_100)


def test_build_cv_ValueError_when_fewer_than_min_folds():
    """
    Test that a configuration producing a single fold raises ValueError
    listing the resolved parameters without the private `_reasoning` key.
    """
    cv_params = _make_cv_params(95)
    cv_params["_reasoning"] = "LLM narrative"

    err_msg = re.escape(
        "The resolved CV configuration produces only 1 fold(s). At least 2 "
        "are required. Resolved parameters: {'steps': 10, "
        "'initial_train_size': 95, 'refit': True, 'fixed_train_size': False, "
        "'gap': 0, 'fold_stride': None, 'skip_folds': None, "
        "'allow_incomplete_fold': True, 'differentiation': None}."
    )
    with pytest.raises(ValueError, match=err_msg):
        build_cv(cv_params, profile_single_daily_100)


def test_build_cv_output_when_integer_initial_train_size():
    """
    Test that the returned TimeSeriesFold carries the resolved parameters
    with `verbose` disabled.
    """
    cv = build_cv(_make_cv_params(60), profile_single_daily_100)

    assert isinstance(cv, TimeSeriesFold)
    assert cv.steps == 10
    assert cv.initial_train_size == 60
    assert cv.refit is True
    assert cv.fixed_train_size is False
    assert cv.verbose is False


def test_build_cv_output_when_float_initial_train_size():
    """
    Test that a fractional initial_train_size becomes an absolute count of
    the dataset span, updated in the parameter dict as well.
    """
    cv_params = _make_cv_params(0.6)

    cv = build_cv(cv_params, profile_single_daily_100)

    assert cv.initial_train_size == 60
    assert cv_params["initial_train_size"] == 60


@pytest.mark.parametrize(
    "value, expected",
    [
        (pd.Timestamp("2023-03-01"), "2023-03-01"),
        (pd.Timestamp("2023-03-01 06:30:00"), "2023-03-01 06:30:00"),
    ],
    ids=["midnight", "with_time"],
)
def test_build_cv_output_when_timestamp_initial_train_size(value, expected):
    """
    Test that a pandas Timestamp is stored as a date string, dropping the
    time only when it is midnight, so the rendered snippet stays valid.
    """
    cv_params = _make_cv_params(value)

    cv = build_cv(cv_params, profile_single_daily_100)

    assert cv.initial_train_size == expected
    assert cv_params["initial_train_size"] == expected


def test_build_cv_output_when_min_folds_relaxed():
    """
    Test that `min_folds=1` accepts a configuration that produces a single
    fold.
    """
    cv = build_cv(_make_cv_params(95), profile_single_daily_100, min_folds=1)

    assert cv.initial_train_size == 95


_STRATEGY_HINT = (
    "Change the arguments of the strategy (`initial_train_size`, "
    "`fold_stride`, `gap`, `skip_folds`) or the `steps` of the plan so that "
    "at least two folds fit in the data."
)


@pytest.mark.parametrize(
    "changes, field, reason",
    [
        (
            {"gap": -1},
            "gap",
            "`gap` must be an integer greater than or equal to 0. Got -1.",
        ),
        (
            {"fold_stride": 0},
            "fold_stride",
            "`fold_stride` must be an integer greater than 0. Got 0.",
        ),
        (
            {"initial_train_size": 500},
            "initial_train_size",
            "The time series must have more than `initial_train_size + gap` "
            "observations to create at least one fold. Time series length: "
            "100 Required > 500 initial_train_size: 500 gap: 0",
        ),
        (
            {"skip_folds": [0]},
            "skip_folds",
            "`skip_folds` list must contain integers greater than or equal "
            "to 1. The first fold is always needed to train the forecaster. "
            "Got [0].",
        ),
    ],
    ids=["gap", "fold_stride", "initial_train_size", "skip_folds"],
)
def test_build_cv_InvalidInputError_when_strategy_cannot_be_built(
    changes, field, reason
):
    """
    Test that an argument that TimeSeriesFold rejects raises an
    InvalidInputError that names it in `field`, keeps the message of
    skforecast on one line and carries a hint: the folds when the
    strategy does not fit in the data, the argument otherwise.
    """
    cv_params = {**_make_cv_params(70, steps=5), **changes}

    err_msg = re.escape(f"The cross-validation strategy cannot be built: {reason}")
    with pytest.raises(InvalidInputError, match="^" + err_msg + "$") as exc_info:
        build_cv(cv_params, profile_single_daily_100)

    assert isinstance(exc_info.value, ValueError)
    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == field
    assert exc_info.value.hint == (
        _STRATEGY_HINT if field == "initial_train_size"
        else f"Pass a value that `TimeSeriesFold` accepts for `{field}`."
    )


@pytest.mark.parametrize(
    "skip_folds, beyond",
    [
        ([100], "[100]"),
        ([1, 6], "[6]"),
        ([7, 100], "[7, 100]"),
        (list(range(7, 14)), "[7, 8, 9, 10, 11] and 2 more"),
    ],
    ids=["far beyond", "first fold beyond", "several beyond", "more than 5"],
)
def test_build_cv_InvalidInputError_when_skip_folds_do_not_exist(skip_folds, beyond):
    """
    Test that `skip_folds` with indexes beyond the folds of the strategy
    (6 folds, numbered from 0 to 5), which TimeSeriesFold ignores, raises
    naming at most 5 of them, with the field 'skip_folds'.
    """
    cv_params = {**_make_cv_params(70, steps=5), "skip_folds": skip_folds}

    err_msg = re.escape(
        f"`skip_folds` names folds that do not exist ({beyond}): the "
        f"strategy has 6 folds, numbered from 0 to 5."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        build_cv(cv_params, profile_single_daily_100)

    assert exc_info.value.field == "skip_folds"


def test_build_cv_output_when_skip_folds_in_range():
    """
    Test that `skip_folds` within the folds of the strategy are kept.
    """
    cv_params = {**_make_cv_params(70, steps=5), "skip_folds": [1, 5]}

    cv = build_cv(cv_params, profile_single_daily_100)

    assert cv.skip_folds == [1, 5]


@pytest.mark.parametrize(
    "changes, field, reason",
    [
        (
            {"refit": "x"},
            "refit",
            "`refit` must be a boolean or an integer equal or greater than 0. "
            "Got x.",
        ),
        (
            {"fixed_train_size": "x"},
            "fixed_train_size",
            "`fixed_train_size` must be a boolean: `True`, `False`. Got x.",
        ),
    ],
    ids=["refit", "fixed_train_size"],
)
def test_build_cv_InvalidInputTypeError_when_argument_has_wrong_type(
    changes, field, reason
):
    """
    Test that an argument of the wrong type that TimeSeriesFold rejects with
    a TypeError raises InvalidInputTypeError, still a TypeError, naming it.
    """
    cv_params = {**_make_cv_params(70, steps=5), **changes}

    err_msg = re.escape(f"The cross-validation strategy cannot be built: {reason}")
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        build_cv(cv_params, profile_single_daily_100)

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.field == field
    assert exc_info.value.hint == (
        _STRATEGY_HINT if field == "initial_train_size"
        else f"Pass a value that `TimeSeriesFold` accepts for `{field}`."
    )
