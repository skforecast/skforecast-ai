# Unit test refit_fits

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai._utils import RefitFits, refit_fits, run_estimator_fits

from .fixtures_compare import profile_h2o


def _count(forecasters):
    """Estimator fits of `forecasters` on h2o with 6 steps."""
    return run_estimator_fits(
               data_profile = profile_h2o.data_profile,
               forecasters  = forecasters,
               steps        = 6,
           )


def test_refit_fits_output_smallest_integer_at_or_below_the_threshold():
    """
    Test that a ForecasterDirect of 6 steps refitted in each of 14 folds
    (84 estimator fits) fits 6 estimators with `refit=False`, and that the
    smallest integer `refit` at or below 50 fits is 2 (7 trainings, 42).
    """
    cv = TimeSeriesFold(steps=6, initial_train_size=120, refit=True)

    result = refit_fits(cv=cv, n_folds=14, count=_count(["ForecasterDirect"]))

    assert result == RefitFits(train_once=6, refit=2, refit_fits=42)


def test_refit_fits_output_skips_an_integer_above_the_threshold():
    """
    Test that, for two ForecasterDirect and a ForecasterRecursive (13
    estimator fits per training), `refit=4` (4 trainings, 52 fits) is above
    50, so the smallest integer is 5 (3 trainings, 39 fits).
    """
    cv = TimeSeriesFold(steps=6, initial_train_size=120, refit=True)
    count = _count(["ForecasterDirect", "ForecasterDirect", "ForecasterRecursive"])

    result = refit_fits(cv=cv, n_folds=14, count=count)

    assert result == RefitFits(train_once=13, refit=5, refit_fits=39)


def test_refit_fits_output_when_no_integer_is_at_or_below_the_threshold():
    """
    Test that, when ForecasterStats (refitted in every fold whatever
    `refit` says) keeps every integer above 50, no integer is given, and
    `refit=False` still states its fits.
    """
    cv = TimeSeriesFold(steps=1, initial_train_size=150, fold_stride=1, refit=True)
    count = run_estimator_fits(
                data_profile = profile_h2o.data_profile,
                forecasters  = ["ForecasterStats", "ForecasterRecursive"],
                steps        = 1,
            )

    result = refit_fits(cv=cv, n_folds=54, count=count)

    assert result == RefitFits(train_once=55, refit=None, refit_fits=None)


def test_refit_fits_does_not_change_the_strategy():
    """
    Test that the strategy given keeps its `refit`: each value is counted
    on a copy.
    """
    cv = TimeSeriesFold(steps=6, initial_train_size=120, refit=True)

    refit_fits(cv=cv, n_folds=14, count=_count(["ForecasterDirect"]))

    assert cv.refit is True


def test_refit_fits_output_with_two_folds():
    """
    Test that, with 2 folds, `refit=2` (which trains once) is tried, so an
    integer is given when its fits are at or below 50.
    """
    cv = TimeSeriesFold(steps=6, initial_train_size=192, refit=True)

    result = refit_fits(cv=cv, n_folds=2, count=_count(["ForecasterDirect"]))

    assert result == RefitFits(train_once=6, refit=2, refit_fits=6)
