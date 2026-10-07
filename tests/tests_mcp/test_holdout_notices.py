# Unit test _holdout_notices

import pandas as pd
import pytest

from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.mcp.server import _holdout_notices


@pytest.mark.parametrize(
    "test_size", [12, 0.1, "2008-06-01"], ids=lambda dt: f"test_size: {dt!r}"
)
def test_holdout_notices_names_the_dates_of_an_evaluation(test_size):
    """
    Test that a forecast run with `test_size` gets one notice saying that
    its predictions are for dates already in the data, which it names, and
    not a forecast of the future.
    """
    predictions = pd.DataFrame(
        {"pred": [1.0, 2.0, 3.0]},
        index=pd.date_range("2008-04-01", periods=3, freq="MS"),
    )

    notices = _holdout_notices(predictions, test_size)

    assert notices == [
        ToolNotice(
            source   = "runtime",
            category = "HoldoutEvaluationNotice",
            message  = (
                "Say in your answer that these predictions are for 2008-04-01 "
                "00:00:00 to 2008-06-01 00:00:00, dates already in the data: "
                "with `test_size` this is an evaluation of the model on its "
                "last observations, not a forecast of the future. Never title "
                "or describe it as the next periods; the future needs "
                "`forecast` without `test_size`."
            ),
            count    = 1,
        )
    ]


def test_holdout_notices_without_predictions():
    """
    Test that the notice is given without dates when the result has no
    predictions.
    """
    notices = _holdout_notices(None, 12)

    assert notices[0].message.startswith(
        "Say in your answer that these predictions are for dates already in "
        "the data: with `test_size` this is an evaluation"
    )


def test_holdout_notices_empty_for_a_forecast_of_the_future():
    """
    Test that a forecast without `test_size` gets no notice.
    """
    predictions = pd.DataFrame({"pred": [1.0]}, index=pd.RangeIndex(1))

    assert _holdout_notices(predictions, None) == []
