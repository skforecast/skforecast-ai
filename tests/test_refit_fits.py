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


def _budget_count(n_folds, steps, budget=500):
    """
    Estimator fits of a comparison of ForecasterRecursive and
    ForecasterDirect on `n_folds` folds, as `compare()` without candidates
    counts them: the direct one (one estimator per step) is left out while
    its fits are above `budget`, so a larger `refit` lets it back in.
    """

    def count(cv):
        trainings = 1 if cv.refit is False else -(-n_folds // cv.refit)
        direct = steps * trainings
        if direct > budget:
            return trainings, ("ForecasterRecursive",)
        return trainings + direct, ("ForecasterRecursive", "ForecasterDirect")

    return count


def test_refit_fits_output_when_a_larger_refit_lets_a_candidate_back_in():
    """
    Test the comparison of the 0.5.0 review (bike_sharing hourly, 24 steps,
    220 folds): ForecasterDirect is left out up to `refit=11` and runs from
    `refit=12`, so the fits jump up there. The smallest integer at or below
    50 fits is 5 (44 trainings of ForecasterRecursive alone), not 110 (2 +
    48 with ForecasterDirect back in), which a single bisection returned.
    """
    cv = TimeSeriesFold(steps=24, initial_train_size=120, refit=True)

    result = refit_fits(cv=cv, n_folds=220, count=_budget_count(220, steps=24))

    assert result == RefitFits(train_once=25, refit=5, refit_fits=44)


def test_refit_fits_output_when_the_integer_is_after_the_jump():
    """
    Test that, when no integer before the jump is at or below 50 fits, the
    smallest one after it is given: with 5264 folds of 1 step,
    ForecasterRecursive alone needs `refit=106` (50 fits) but
    ForecasterDirect is back in from `refit=11`, so both run there and the
    smallest integer is 211 (25 + 25 fits).
    """
    cv = TimeSeriesFold(steps=1, initial_train_size=120, refit=True)

    result = refit_fits(cv=cv, n_folds=5264, count=_budget_count(5264, steps=1))

    assert result == RefitFits(train_once=2, refit=211, refit_fits=50)


def test_refit_fits_counts_few_strategies_when_no_integer_fits():
    """
    Test that, when no integer is at or below 50 fits (a ForecasterStats
    plan, refitted in every one of 5264 folds), the answer comes from a
    few counts, about the logarithm of the folds, and not one per fold.
    """
    cv = TimeSeriesFold(steps=1, initial_train_size=120, refit=True)
    calls = []

    def count(strategy):
        calls.append(strategy.refit)
        return 5264, None

    result = refit_fits(cv=cv, n_folds=5264, count=count)

    assert result == RefitFits(train_once=5264, refit=None, refit_fits=None)
    assert len(calls) == 3
