# Unit test count_inference_windows recommendation/backtesting

import pytest

from skforecast_ai.recommendation.backtesting import count_inference_windows


@pytest.mark.parametrize(
    "forecaster, expected",
    [
        ("ForecasterFoundation", 39500),
        ("ForecasterRecursive", 0),
        ("ForecasterRecursiveMultiSeries", 0),
        ("ForecasterDirect", 0),
        ("ForecasterStats", 0),
        ("ForecasterEquivalentDate", 0),
    ],
    ids=lambda value: f"{value}",
)
def test_count_inference_windows_output(forecaster, expected):
    """
    Test that count_inference_windows returns one window per series and
    fold for the foundation model, which is never trained, and 0 for the
    other forecasters, whose cost is counted in estimator fits.
    """
    result = count_inference_windows(
        n_folds=79, n_series=500, forecaster=forecaster
    )

    assert result == expected
