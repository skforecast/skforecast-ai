# Unit test _metric_notices

import pandas as pd
import pytest

from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.mcp.server import _metric_notices


@pytest.mark.parametrize(
    "columns",
    [
        ["mean_absolute_error", "mean_absolute_scaled_error"],
        ["series", "MAE", "MASE"],
    ],
    ids=lambda dt: f"columns: {dt}",
)
def test_metric_notices_reference_of_mase(columns):
    """
    Test that the metrics of a backtest (names of skforecast) or of a
    forecast (short names) with MASE get one notice saying that it is scaled
    by the one-step naive forecast on the training data, not by a seasonal
    naive forecast nor by the baseline of `compare`.
    """
    metrics = pd.DataFrame([[0.5] * len(columns)], columns=columns)

    notices = _metric_notices(metrics)

    assert notices == [
        ToolNotice(
            source   = "runtime",
            category = "MetricReferenceNotice",
            message  = (
                "`mean_absolute_scaled_error` divides the error by that of "
                "the one-step naive forecast (repeat the previous value) on "
                "the training data: below 1 the error is smaller than that "
                "reference. The reference is not a seasonal naive forecast "
                "nor the baseline of `compare`, so do not report a value "
                "below 1 as beating either."
            ),
            count    = 1,
        )
    ]


def test_metric_notices_names_both_scaled_metrics():
    """
    Test that the notice names MASE and RMSSE when both were computed.
    """
    metrics = pd.DataFrame(
        {"root_mean_squared_scaled_error": [0.9], "mean_absolute_scaled_error": [0.8]}
    )

    notices = _metric_notices(metrics)

    assert len(notices) == 1
    assert notices[0].message.startswith(
        "`root_mean_squared_scaled_error` and `mean_absolute_scaled_error` "
        "divide the error by that of the one-step naive forecast"
    )


@pytest.mark.parametrize(
    "metrics",
    [None, pd.DataFrame({"mean_absolute_error": [0.5], "mean_squared_error": [0.1]})],
    ids=["no metrics", "no scaled metric"],
)
def test_metric_notices_empty_without_scaled_metrics(metrics):
    """
    Test that a forecast of the future (no metrics) and a result without a
    scaled metric get no notice.
    """
    assert _metric_notices(metrics) == []
