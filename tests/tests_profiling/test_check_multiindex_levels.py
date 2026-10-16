# Unit test check_multiindex_levels

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.exceptions import InvalidInputError
from skforecast_ai.profiling.data_profile import check_multiindex_levels

_dates = pd.date_range("2023-01-01", periods=2, freq="D")
_index = pd.MultiIndex.from_arrays(
    [["a", "a"], _dates], names=["series", "date"]
)
_index_three = pd.MultiIndex.from_arrays(
    [["a", "a"], _dates, ["north", "north"]], names=["series", "date", "region"]
)

_LEVELS_HINT_DATA = (
    "Keep the series id and the date in the index and move the other levels "
    "into columns with `data.reset_index(level=...)`, or turn every level into "
    "a column with `data.reset_index()` and pass `series_id_column` and "
    "`date_column`."
)
_LEVELS_HINT_EXOG = (
    "Keep the series id and the date in the index and move the other levels "
    "into columns with `exog.reset_index(level=...)`, or turn every level into "
    "a column with `exog.reset_index()`."
)
_NAMES_HINT_DATA = (
    "Name the levels with text, as in `data.rename_axis(['series_id', 'date'])`, "
    "or turn them into columns with `data.reset_index()` and pass their names "
    "as `series_id_column` and `date_column`."
)
_NAMES_HINT_EXOG = (
    "Name the levels as the series id and date columns of the data, as in "
    "`exog.rename_axis(['series_id', 'date'])`, and pass it as it is or with "
    "`reset_index()`."
)


@pytest.mark.parametrize(
    "data, field, err_msg, hint",
    [
        (
            pd.DataFrame({"y": [1.0, 2.0]}, index=_index_three),
            "data",
            "`data` is indexed by a MultiIndex with 3 levels (names ['series', "
            "'date', 'region']). A MultiIndex is read as the series id and the "
            "date, `(series_id, date)`, so it must have two levels.",
            _LEVELS_HINT_DATA,
        ),
        (
            pd.DataFrame(
                {"x": [1.0, 2.0]},
                index=_index_three.reorder_levels(["region", "series", "date"]),
            ),
            "exog",
            "`exog` is indexed by a MultiIndex with 3 levels (names ['region', "
            "'series', 'date']).",
            _LEVELS_HINT_EXOG,
        ),
        (
            pd.DataFrame(
                {"y": [1.0, 2.0]},
                index=pd.MultiIndex.from_arrays([["a", "b"]], names=["series"]),
            ),
            "data",
            "`data` is indexed by a MultiIndex with 1 level (names ['series']).",
            _LEVELS_HINT_DATA,
        ),
        (
            pd.DataFrame({"y": [1.0, 2.0]}, index=_index.rename(["series", None])),
            "data",
            "`data` is indexed by a MultiIndex with levels without a name "
            "(names ['series', None]). The levels are read as columns of the "
            "same name, and `to_csv()` writes an empty header for a level "
            "without a name, so the generated script could not read it from "
            "the saved file.",
            _NAMES_HINT_DATA,
        ),
        (
            pd.Series([1.0, 2.0], index=_index.rename([None, None])),
            "exog",
            "`exog` is indexed by a MultiIndex with levels without a name "
            "(names [None, None]).",
            _NAMES_HINT_EXOG,
        ),
        (
            pd.DataFrame({"y": [1.0, 2.0]}, index=_index.rename([0, "date"])),
            "data",
            "`data` is indexed by a MultiIndex with levels not named with text "
            "(names [0, 'date']). The levels are read as columns of the same "
            "name, and the generated script names its columns with text.",
            _NAMES_HINT_DATA,
        ),
    ],
    ids=[
        "three levels",
        "three levels, exog",
        "one level",
        "level without a name",
        "series without names, exog",
        "level named with a number",
    ],
)
def test_check_multiindex_levels_InvalidInputError_when_levels_invalid(
    data, field, err_msg, hint
):
    """
    Test that a MultiIndex of a DataFrame or a Series raises when it does not
    have two levels, or a level has no name or a name that is not text, with
    the argument at fault as `field` and the hint of the problem for that
    argument.
    """
    with pytest.raises(InvalidInputError, match=re.escape(err_msg)) as exc_info:
        check_multiindex_levels(data, field=field)

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
    ids=["none", "no multiindex", "two named levels", "series, two named levels"],
)
def test_check_multiindex_levels_output_when_nothing_to_reject(data):
    """
    Test that None, data without a MultiIndex and a MultiIndex of two levels
    named with text pass.
    """
    assert check_multiindex_levels(data) is None
