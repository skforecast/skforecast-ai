# Unit test _mape_notices

import pandas as pd
import pytest

from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.mcp.server import _mape_notices, _metric_notices

MAPE_NOTICE = ToolNotice(
    source   = "runtime",
    category = "MetricUnitNotice",
    message  = (
        "`mean_absolute_percentage_error` is a fraction, not a percentage: "
        "0.05 is 5 %, and 1.245 is 124.5 %. Multiply it by 100 before you "
        "write it with a % sign."
    ),
    count    = 1,
)


@pytest.mark.parametrize(
    "columns",
    [
        ["mean_absolute_error", "mean_absolute_percentage_error"],
        ["series", "MAE", "MAPE"],
        ["rank", "name", "mean_absolute_percentage_error"],
    ],
    ids=lambda dt: f"columns: {dt}",
)
def test_mape_notices_unit_of_mape(columns):
    """
    Test that the metrics of a backtest (names of skforecast), of a forecast
    (short names) or the leaderboard of a comparison with MAPE get one
    notice saying that it is a fraction, not a percentage.
    """
    metrics = pd.DataFrame([[1.245] * len(columns)], columns=columns)

    assert _mape_notices(metrics) == [MAPE_NOTICE]


@pytest.mark.parametrize(
    "metrics",
    [None, pd.DataFrame({"mean_absolute_error": [0.5], "MASE": [0.1]})],
    ids=["no metrics", "no MAPE"],
)
def test_mape_notices_empty_without_mape(metrics):
    """
    Test that a result without metrics or without MAPE gets no notice.
    """
    assert _mape_notices(metrics) == []


def test_mape_notices_follow_the_reference_of_the_scaled_metrics():
    """
    Test that `_metric_notices` gives the notice of MAPE after the one of
    the scaled metrics, and alone when no scaled metric was computed.
    """
    both = pd.DataFrame(
        {"mean_absolute_scaled_error": [0.5], "mean_absolute_percentage_error": [1.2]}
    )
    alone = pd.DataFrame({"mean_absolute_percentage_error": [1.2]})

    assert [notice.category for notice in _metric_notices(both)] == [
        "MetricReferenceNotice", "MetricUnitNotice",
    ]
    assert _metric_notices(alone) == [MAPE_NOTICE]
