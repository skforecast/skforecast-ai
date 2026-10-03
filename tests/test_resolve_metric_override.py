# Unit test resolve_metric_override

import re
import pytest

from skforecast_ai._validation import resolve_metric_override
from skforecast_ai.exceptions import InvalidInputError, InvalidInputTypeError


@pytest.mark.parametrize(
    "metric, expected",
    [
        (None, None),
        ("mean_squared_error", ["mean_squared_error"]),
        (
            ["median_absolute_error", "mean_absolute_error"],
            ["median_absolute_error", "mean_absolute_error"],
        ),
        (("mean_absolute_error",), ["mean_absolute_error"]),
    ],
    ids=["None", "str", "list", "tuple"],
)
def test_resolve_metric_override_output(metric, expected):
    """
    Test that None stays None and a metric or a sequence of them becomes a
    list in the order given.
    """
    assert resolve_metric_override(metric) == expected


@pytest.mark.parametrize(
    "metric, error, message",
    [
        ([], InvalidInputError, "`metric` must not be an empty list."),
        (
            ["mean_absolute_error", "mean_absolute_error"],
            InvalidInputError,
            "`metric` repeats ['mean_absolute_error']: list each metric once.",
        ),
        ("r2", InvalidInputError, "Unknown metric 'r2'."),
        (1.5, InvalidInputTypeError, "`metric` must be a metric name or a list"),
        ({"mean_absolute_error"}, InvalidInputTypeError, "`metric` must be a metric"),
        (["mean_absolute_error", None], InvalidInputTypeError, "`metric` must be"),
    ],
    ids=["empty", "repeated", "unknown", "float", "set", "None in list"],
)
def test_resolve_metric_override_error_when_invalid(metric, error, message):
    """
    Test that an empty list, a repeated or unknown metric and a value that
    is not a str or a list of str raise with `field='metric'`.
    """
    with pytest.raises(error, match=re.escape(message)) as info:
        resolve_metric_override(metric)

    assert info.value.field == "metric"
