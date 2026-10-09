# Unit test warn_long_inference

import re
import warnings

import pytest
from skforecast.exceptions import LongTrainingWarning

from skforecast_ai._utils import warn_long_inference


def test_warn_long_inference_message_when_windows_exceed_threshold():
    """
    Test that more than 2000 inference windows emit a LongTrainingWarning
    that breaks them into series and folds and suggests fewer folds or
    fewer series (a foundation model has no `refit` to change).
    """
    msg = re.escape(
        "ForecasterFoundation will forecast up to 39500 inference windows (500 "
        "series x 79 folds), more than 2000. This can take minutes on a CPU. "
        "If not feasible, use a cross-validation strategy with fewer folds "
        "(a later `initial_train_size` or a larger `fold_stride`) or "
        "forecast fewer series."
    )
    with pytest.warns(LongTrainingWarning, match=msg):
        warn_long_inference(inference_windows=39500, n_series=500, n_folds=79)


@pytest.mark.parametrize(
    "inference_windows, n_series, n_folds",
    [(2000, 200, 10), (0, 3, 10)],
    ids=lambda value: f"{value}",
)
def test_warn_long_inference_no_warning_when_windows_within_threshold(
    inference_windows, n_series, n_folds
):
    """
    Test that no warning is emitted up to 2000 inference windows, nor for
    a forecaster that is not a foundation model (0 windows).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warn_long_inference(
            inference_windows=inference_windows, n_series=n_series, n_folds=n_folds
        )
