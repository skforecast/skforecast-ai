# Unit test check_multiindex_names

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import check_multiindex_names

_index = pd.MultiIndex.from_arrays(
    [["a", "a"], pd.date_range("2023-01-01", periods=2, freq="D"), [1, 2]],
    names=["series", "date", "store"],
)


@pytest.mark.parametrize(
    "data, field, names, hint",
    [
        (
            pd.DataFrame({"y": [1.0, 2.0]}, index=_index[:2].droplevel(2))
            .rename_axis(["series", None]),
            "data",
            ["series", None],
            "Name the levels, as in `data.rename_axis(['series_id', 'date'])`, "
            "or turn them into columns with `data.reset_index()` and pass their "
            "names as `series_id_column` and `date_column`.",
        ),
        (
            pd.Series([1.0, 2.0], index=_index.rename([None, "date", "store"])),
            "data",
            [None, "date", "store"],
            "Name the levels, as in `data.rename_axis(['series_id', 'date'])`, "
            "or turn them into columns with `data.reset_index()` and pass their "
            "names as `series_id_column` and `date_column`.",
        ),
        (
            pd.DataFrame(
                {"x": [1.0, 2.0]}, index=_index.rename(["series", "date", None])
            ),
            "exog",
            ["series", "date", None],
            "Name the levels as the series id and date columns of the data, as "
            "in `exog.rename_axis(['series_id', 'date'])`, and pass it as it is "
            "or with `reset_index()`.",
        ),
    ],
    ids=["dataframe, date level", "series, first level", "exog, third level"],
)
def test_check_multiindex_names_InvalidInputError_when_level_unnamed(
    data, field, names, hint
):
    """
    Test that a MultiIndex with any level without a name raises, for a
    DataFrame or a Series, with the argument at fault as `field` and the
    hint of that argument.
    """
    err_msg = re.escape(
        f"`{field}` is indexed by a MultiIndex with levels without a name "
        f"(names {names})."
    )
    with pytest.raises(InvalidInputError, match=err_msg) as exc_info:
        check_multiindex_names(data, field=field)

    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == field
    assert exc_info.value.hint == hint


@pytest.mark.parametrize(
    "data",
    [
        None,
        pd.DataFrame({"y": [1.0, 2.0]}),
        pd.DataFrame({"y": [1.0, 2.0]}, index=_index),
        pd.Series(np.array([1.0, 2.0]), index=_index),
    ],
    ids=["none", "no multiindex", "named levels", "series, named levels"],
)
def test_check_multiindex_names_output_when_nothing_to_reject(data):
    """
    Test that None, data without a MultiIndex and a MultiIndex whose levels
    all have names pass.
    """
    assert check_multiindex_names(data) is None
