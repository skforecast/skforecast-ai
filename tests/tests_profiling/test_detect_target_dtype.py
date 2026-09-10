# Unit test detect_target_dtype

import pandas as pd
import pytest

from skforecast_ai.profiling.data_profile import detect_target_dtype


@pytest.mark.parametrize(
    "values, expected",
    [
        (pd.Series([1.0, 2.0]), "numeric"),
        (pd.Series(["a", "b"], dtype="category"), "categorical"),
        (pd.Series(["a", "b"]), "categorical"),
        # pandas counts bool as numeric, so the numeric check wins.
        (pd.Series([True, False]), "numeric"),
        (pd.Series(pd.date_range("2023-01-01", periods=2)), "other"),
    ],
    ids=["float", "category", "object", "bool", "datetime"],
)
def test_detect_target_dtype_output(values, expected):
    """
    Test the dtype category reported for numeric, categorical, object,
    bool and datetime targets. A bool target is numeric for pandas, so it
    never reaches the categorical branch.
    """
    assert detect_target_dtype(pd.DataFrame({"y": values}), "y") == expected
