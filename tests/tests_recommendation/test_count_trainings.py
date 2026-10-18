# Unit test count_trainings recommendation/backtesting

import pytest

from skforecast_ai.recommendation.backtesting import count_trainings


@pytest.mark.parametrize(
    "forecaster, expected",
    [
        ("ForecasterRecursive", 6),
        ("ForecasterRecursiveMultiSeries", 6),
        ("ForecasterDirect", 6),
        ("ForecasterDirectMultiVariate", 6),
        ("ForecasterStats", 41),
        ("ForecasterFoundation", 0),
        ("ForecasterEquivalentDate", 6),
    ],
    ids=lambda value: f"{value}",
)
def test_count_trainings_output(forecaster, expected):
    """
    Test that count_trainings returns `n_fits` for the forecasters trained
    as the strategy says, `n_folds` for ForecasterStats (skforecast refits
    it in every fold whatever `refit` says) and 0 for ForecasterFoundation
    (never trained).
    """
    result = count_trainings(n_fits=6, forecaster=forecaster, n_folds=41)

    assert result == expected
