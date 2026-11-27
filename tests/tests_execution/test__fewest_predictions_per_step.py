# Unit test _fewest_predictions_per_step execution/backtesting_runner

import pandas as pd
import pytest

from skforecast_ai.execution.backtesting_runner import _fewest_predictions_per_step


@pytest.mark.parametrize(
    "predictions",
    [
        None,
        pd.DataFrame({"step": [1, 2], "pred": [1.0, 2.0]}),
        pd.DataFrame({"y_true": [1.0, 2.0], "pred": [1.0, 2.0]}),
        pd.DataFrame({"step": [1, 2], "y_true": [None, None], "pred": [1.0, 2.0]}),
    ],
    ids=["None", "without y_true", "without step", "no observed value"],
)
def test_fewest_predictions_per_step_output_None_when_cannot_count(predictions):
    """
    Test that _fewest_predictions_per_step returns None when the predictions
    are missing, lack `step` or `y_true`, or have no observed value.
    """
    assert _fewest_predictions_per_step(predictions) is None


def test_fewest_predictions_per_step_output_single_series():
    """
    Test that the count of a single series is the fewest predictions with an
    observed value of any step, leaving out a step that has none.
    """
    predictions = pd.DataFrame({
        "step": [1, 2, 1, 2, 1, 3],
        "y_true": [1.0, 2.0, 3.0, None, 5.0, None],
        "pred": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    })

    assert _fewest_predictions_per_step(predictions) == 1


def test_fewest_predictions_per_step_output_several_series():
    """
    Test that with several series the count is per series and step: a
    series with fewer folds sets it.
    """
    predictions = pd.DataFrame({
        "level": ["a", "a", "a", "a", "b", "b", "b", "b", "b", "b"],
        "step": [1, 2, 1, 2, 1, 2, 1, 2, 1, 2],
        "y_true": [1.0] * 10,
        "pred": [2.0] * 10,
    })

    assert _fewest_predictions_per_step(predictions) == 2
