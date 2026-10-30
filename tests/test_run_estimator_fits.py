# Unit test run_estimator_fits

import pytest
from skforecast.model_selection import TimeSeriesFold

from skforecast_ai._utils import run_estimator_fits

from .fixtures_compare import profile_h2o


@pytest.mark.parametrize(
    "forecasters, refit, expected",
    [
        (["ForecasterDirect"], True, 84),
        (["ForecasterDirect"], 2, 42),
        (["ForecasterDirect"], False, 6),
        (["ForecasterRecursive"], 3, 5),
        (["ForecasterStats"], False, 14),
        (["ForecasterFoundation", "ForecasterEquivalentDate"], True, 0),
        (["ForecasterDirect", "ForecasterRecursive", "ForecasterStats"], 2, 63),
    ],
    ids=lambda value: f"{value}",
)
def test_run_estimator_fits_output(forecasters, refit, expected):
    """
    Test that the function returned counts the estimator fits of the runs
    of `forecasters` on a strategy of 14 folds of 6 steps (h2o from 120
    observations), added up: one estimator per step and training for a
    direct forecaster, every fold for ForecasterStats whatever `refit`
    says, none for a foundation model or the baseline.
    """
    count = run_estimator_fits(
                data_profile = profile_h2o.data_profile,
                forecasters  = forecasters,
                steps        = 6,
            )
    cv = TimeSeriesFold(steps=6, initial_train_size=120, refit=refit)

    assert count(cv) == expected
