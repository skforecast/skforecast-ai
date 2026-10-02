# Unit test warn_long_training

import re
import warnings

import pytest
from skforecast.exceptions import LongTrainingWarning

from skforecast_ai._utils import warn_long_training


def test_warn_long_training_message_when_forecaster_is_stats():
    """
    Test that for ForecasterStats the warning tells that skforecast refits
    it in every fold whatever `refit` says, and suggests fewer folds
    instead of `refit`.
    """
    msg = re.escape(
        "ForecasterStats will be fit 60 times. This can take substantial "
        "amounts of time. If not feasible, skforecast refits it in every "
        "fold whatever `refit` says, so use a cross-validation strategy "
        "with fewer folds (a later `initial_train_size`, a larger "
        "`fold_stride` or `skip_folds`)."
    )
    with pytest.warns(LongTrainingWarning, match=msg):
        warn_long_training(
            estimator_fits=60, n_fits=60, forecaster="ForecasterStats", steps=10
        )


def test_warn_long_training_message_when_forecaster_is_direct():
    """
    Test that for another forecaster the warning suggests `refit=False` or
    an integer `refit`.
    """
    msg = re.escape(
        "ForecasterDirect will be fit 60 times (6 trainings x 10 "
        "estimators). This can take substantial amounts of time. If not "
        "feasible, use a cross-validation strategy with `refit=False` "
        "(train once) or an integer `refit` (retrain every n folds)."
    )
    with pytest.warns(LongTrainingWarning, match=msg):
        warn_long_training(
            estimator_fits=60, n_fits=6, forecaster="ForecasterDirect", steps=10
        )


def test_warn_long_training_no_warning_when_fits_within_threshold():
    """
    Test that no warning is emitted when the estimator fits do not exceed
    the threshold of 50.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warn_long_training(
            estimator_fits=50, n_fits=50, forecaster="ForecasterStats", steps=10
        )
