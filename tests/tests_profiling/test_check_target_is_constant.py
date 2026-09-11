# Unit test _check_target_is_constant

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import _check_target_is_constant


@pytest.mark.parametrize(
    "values, expected",
    [
        ([np.nan, np.nan], True),
        ([3.0, 3.0, 3.0], True),
        ([1.0, 2.0, 3.0], False),
        (["a", "a", np.nan], True),
        (["a", "b"], False),
    ],
    ids=["all NaN", "constant numeric", "varying numeric", "single category", "two categories"],
)
def test_check_target_is_constant_output(values, expected):
    """
    Test that an empty, zero-variance or single-category target is
    reported as constant.
    """
    assert _check_target_is_constant(pd.DataFrame({"y": values}), "y") is expected
