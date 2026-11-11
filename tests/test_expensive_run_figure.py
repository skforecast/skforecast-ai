# Unit test expensive_run_figure

import pytest

from skforecast_ai._utils import expensive_run_figure


@pytest.mark.parametrize(
    "estimator_fits, inference_windows, expected",
    [
        (0, 0, None),
        (50, 0, None),
        (51, 0, 51),
        (50, 2000, None),
        (50, 2001, 2001),
        (0, 2000, None),
        (0, 2001, 2001),
        (51, 2001, 51),
        (60, 3000, 60),
    ],
    ids=lambda value: f"{value}",
)
def test_expensive_run_figure_output(estimator_fits, inference_windows, expected):
    """
    Test that the figure is the estimator fits when above 50, else the
    inference windows when above 2000, else None, so the thresholds
    themselves (50 and 2000) need no confirmation, a run above both takes
    the estimator fits, and a foundation model that fits nothing (0 fits)
    takes the windows.
    """
    result = expensive_run_figure(
        estimator_fits    = estimator_fits,
        inference_windows = inference_windows,
    )

    assert result == expected
