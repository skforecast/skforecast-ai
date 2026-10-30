# Unit test cost_remedies

import pytest

from skforecast_ai._utils import RefitFits, cost_remedies

_REFIT = "an integer `refit` (retrain every n folds)"
_FOLDS_SKIP = (
    "fewer folds (a later `initial_train_size`, a larger `fold_stride` or "
    "`skip_folds`)"
)
_FOLDS = "fewer folds (a later `initial_train_size` or a larger `fold_stride`)"
_NO_REFIT = "`refit=False` (train once)"
_HORIZON = "a shorter horizon (a direct forecaster fits one estimator per step)"


@pytest.mark.parametrize(
    "forecasters, n_fits, steps, expected",
    [
        (["ForecasterRecursive"], 6, 5, [_REFIT, _FOLDS_SKIP, _NO_REFIT]),
        (["ForecasterDirect"], 6, 5, [_REFIT, _FOLDS_SKIP, _NO_REFIT]),
        (["ForecasterRecursive", "ForecasterDirect"], 6, 5,
         [_REFIT, _FOLDS_SKIP, _NO_REFIT]),
        (["ForecasterRecursive"], 1, 5, []),
        (["ForecasterStats"], 1, 5, [_FOLDS]),
        (["ForecasterStats"], 9, 5, [_FOLDS]),
        (["ForecasterFoundation"], 1, 5, [_FOLDS_SKIP, "fewer series"]),
        (["ForecasterFoundation"], 9, 5, [_FOLDS_SKIP, "fewer series"]),
        (["ForecasterDirect"], 1, 5, [_HORIZON]),
        (["ForecasterDirect"], 1, 1, []),
        (["ForecasterDirect", "ForecasterStats"], 1, 5, [_FOLDS]),
        (["ForecasterEquivalentDate"], 6, 5, []),
        (["ForecasterEquivalentDate"], 1, 5, []),
    ],
    ids=lambda value: f"{value}",
)
def test_cost_remedies_output(forecasters, n_fits, steps, expected):
    """
    Test that cost_remedies names only the changes that lower the cost of
    the forecasters given, in a fixed order: an integer `refit`, fewer
    folds and `refit=False` only for a forecaster trained more than once,
    fewer folds for ForecasterStats (without `skip_folds`) and
    ForecasterFoundation, a shorter horizon only for a direct forecaster
    trained once next to no ForecasterStats or ForecasterFoundation, and
    fewer series for ForecasterFoundation.
    """
    result = cost_remedies(forecasters=forecasters, n_fits=n_fits, steps=steps)

    assert result == expected


def test_cost_remedies_output_when_false_is_lowercase():
    """
    Test that `false` sets how `refit=False` is written, as the JSON
    arguments of the MCP server need.
    """
    result = cost_remedies(
        forecasters = ["ForecasterRecursive"],
        n_fits      = 6,
        steps       = 5,
        false       = "false",
    )

    assert result == [_REFIT, _FOLDS_SKIP, "`refit=false` (train once)"]


def test_cost_remedies_output_when_skip_folds_is_false():
    """
    Test that `skip_folds=False` removes `skip_folds` from the phrase on
    fewer folds, for a forecaster trained more than once and for
    ForecasterFoundation.
    """
    refits = cost_remedies(
        forecasters = ["ForecasterRecursive"],
        n_fits      = 6,
        steps       = 5,
        skip_folds  = False,
    )
    foundation = cost_remedies(
        forecasters = ["ForecasterFoundation"],
        n_fits      = 1,
        steps       = 5,
        skip_folds  = False,
    )

    assert refits == [_REFIT, _FOLDS, _NO_REFIT]
    assert foundation == [_FOLDS, "fewer series"]


@pytest.mark.parametrize(
    "fits, expected",
    [
        (
            RefitFits(train_once=6, refit=2, refit_fits=36),
            [
                "`refit=2` (retrain every 2 folds: 36 estimator fits)",
                _FOLDS_SKIP,
                "`refit=False` (train once: 6 estimator fits)",
            ],
        ),
        (
            RefitFits(train_once=56, refit=None, refit_fits=None),
            [
                "an integer `refit` (retrain every n folds: none fits 50 "
                "estimators or fewer)",
                _FOLDS_SKIP,
                "`refit=False` (train once: 56 estimator fits)",
            ],
        ),
    ],
    ids=["integer_found", "no_integer"],
)
def test_cost_remedies_output_with_the_fits_of_refit(fits, expected):
    """
    Test that, with the estimator fits of the cheaper values of `refit`,
    the remedies name the smallest integer `refit` at or below the
    threshold with its fits (or say that none is) and `refit=False` with
    its fits; the other remedies do not change.
    """
    result = cost_remedies(
        forecasters = ["ForecasterDirect"],
        n_fits      = 11,
        steps       = 6,
        fits        = fits,
    )

    assert result == expected


def test_cost_remedies_output_with_fits_when_refit_lowers_nothing():
    """
    Test that the fits of `refit` change nothing when `refit` lowers
    nothing (ForecasterStats, refitted in every fold whatever it says).
    """
    result = cost_remedies(
        forecasters = ["ForecasterStats"],
        n_fits      = 9,
        steps       = 5,
        fits        = RefitFits(train_once=9, refit=None, refit_fits=None),
    )

    assert result == [_FOLDS]
