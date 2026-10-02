# Unit test count_estimator_fits recommendation/backtesting

import pytest

from skforecast_ai.recommendation.backtesting import count_estimator_fits


@pytest.mark.parametrize(
    "forecaster, expected",
    [
        ("ForecasterRecursive", 20),
        ("ForecasterRecursiveMultiSeries", 20),
        ("ForecasterStats", 20),
        ("ForecasterDirect", 480),
        ("ForecasterDirectMultiVariate", 480),
        ("ForecasterFoundation", 0),
        ("ForecasterEquivalentDate", 0),
    ],
    ids=lambda value: f"{value}",
)
def test_count_estimator_fits_output(forecaster, expected):
    """
    Test that count_estimator_fits returns one fit per training, one per
    step and training for the direct forecasters, and none for the
    foundation model (never trained) and the baseline (no estimator).
    """
    result = count_estimator_fits(n_fits=20, forecaster=forecaster, steps=24)

    assert result == expected


@pytest.mark.parametrize(
    "forecaster, n_folds, expected",
    [
        ("ForecasterStats", 6, 6),
        ("ForecasterStats", None, 20),
        ("ForecasterRecursive", 6, 20),
        ("ForecasterDirect", 6, 480),
        ("ForecasterFoundation", 6, 0),
    ],
    ids=lambda value: f"{value}",
)
def test_count_estimator_fits_output_when_n_folds_given(
    forecaster, n_folds, expected
):
    """
    Test that count_estimator_fits returns `n_folds` for ForecasterStats
    (skforecast refits it in every fold) and `n_fits` when it is None,
    while the other forecasters ignore `n_folds`.
    """
    result = count_estimator_fits(
        n_fits=20, forecaster=forecaster, steps=24, n_folds=n_folds
    )

    assert result == expected
