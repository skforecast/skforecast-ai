# Unit test check_exog_covers_horizon

import re

import pandas as pd
import pytest

from skforecast_ai._utils import check_exog_covers_horizon
from skforecast_ai.exceptions import InvalidInputError

from tests.fixtures_future_exog import exog_range


def test_check_exog_covers_horizon_InvalidInputError_when_fewer_rows_than_steps():
    """
    Test that future exogenous variables with fewer rows than the steps of
    the horizon raise `InvalidInputError` on `exog`, saying how many rows
    are needed.
    """
    err_msg = re.escape(
        "`exog` must cover the forecast horizon: 10 rows are required but only "
        "7 were provided."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        check_exog_covers_horizon(exog_range, steps=10)
    assert exc_info.value.field == "exog"


@pytest.mark.parametrize("steps", [5, 7], ids=lambda steps: f"steps: {steps}")
def test_check_exog_covers_horizon_output_when_rows_cover_steps(steps):
    """
    Test that future exogenous variables with as many rows as the steps of
    the horizon, or more, pass without an error.
    """
    assert check_exog_covers_horizon(exog_range, steps=steps) is None


def test_check_exog_covers_horizon_InvalidInputError_when_empty():
    """
    Test that an empty frame raises: it covers no step of the horizon.
    """
    err_msg = re.escape(
        "`exog` must cover the forecast horizon: 1 rows are required but only "
        "0 were provided."
    )
    with pytest.raises(InvalidInputError, match=err_msg):
        check_exog_covers_horizon(pd.DataFrame({"x": []}), steps=1)
