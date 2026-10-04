# Unit test _frame_fingerprint

import numpy as np
import pandas as pd
import pytest

from skforecast_ai.assistant import _frame_fingerprint

from tests.fixtures_datasets import df_h2o, df_h2o_long


def test_frame_fingerprint_output_same_for_equal_frames():
    """
    Test that two equal frames (a copy) have the same fingerprint, a hexadecimal
    SHA-256 of 64 characters.
    """
    fingerprint = _frame_fingerprint(df_h2o)

    assert fingerprint == _frame_fingerprint(df_h2o.copy())
    assert len(fingerprint) == 64
    assert _frame_fingerprint(df_h2o_long) == _frame_fingerprint(df_h2o_long.copy())


@pytest.mark.parametrize(
    "changed",
    [
        df_h2o.assign(x=df_h2o["x"].where(df_h2o.index != df_h2o.index[5], 0.5)),
        df_h2o.iloc[:-1],
        df_h2o.rename(columns={"x": "y"}),
        df_h2o.astype({"x": "float32"}),
        df_h2o.set_axis(df_h2o.index.tz_localize("UTC")),
        df_h2o.set_axis(df_h2o.index.shift(1)),
        df_h2o.set_axis(pd.DatetimeIndex(list(df_h2o.index), name="fecha")),
        df_h2o.rename_axis("date"),
    ],
    ids=[
        "value", "row", "column", "dtype", "time_zone", "dates",
        "index_without_freq", "index_name",
    ],
)
def test_frame_fingerprint_output_changes_with_the_data(changed):
    """
    Test that the fingerprint changes with a value, a row, a column name, a
    dtype, the time zone, the dates, the `freq` attribute and the name of
    the index.
    """
    assert _frame_fingerprint(changed) != _frame_fingerprint(df_h2o)


def test_frame_fingerprint_output_changes_with_int_and_float_columns():
    """
    Test that an integer column and a float column with the same values have
    different fingerprints.
    """
    ints = pd.DataFrame({"a": np.arange(5)})

    assert _frame_fingerprint(ints) != _frame_fingerprint(ints.astype(float))


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame({"a": [1, "1"]}),
        pd.DataFrame({"a": pd.Categorical([1, "1"])}),
        pd.DataFrame({"a": [1.0, 2.0]}, index=pd.Index([1, "x"])),
        pd.DataFrame(
            {"a": [1.0, 2.0]}, index=pd.MultiIndex.from_tuples([(1, 2), (3, 4)])
        ),
        pd.DataFrame(
            [[1.0, 2.0]], columns=pd.MultiIndex.from_tuples([("a", 1), ("a", 2)])
        ),
        pd.DataFrame({"a": [[1], [2]]}),
        pd.DataFrame({"a": ["x", "\ud800"]}),
    ],
    ids=[
        "mixed_object", "mixed_categories", "mixed_index", "multiindex",
        "multiindex_columns", "unhashable", "surrogate",
    ],
)
def test_frame_fingerprint_output_None_when_values_cannot_be_told_apart(frame):
    """
    Test that the fingerprint is None for object values that are not all
    text (pandas hashes `1` and `'1'` alike), a MultiIndex in the rows or
    the columns, values that cannot be hashed and text that cannot be
    encoded.
    """
    assert _frame_fingerprint(frame) is None


def test_frame_fingerprint_output_for_text_and_missing_values():
    """
    Test that object columns of text with missing values have a fingerprint,
    and that a missing value is told apart from a text.
    """
    frame = pd.DataFrame({"a": ["x", None, "y"]})

    assert _frame_fingerprint(frame) is not None
    assert _frame_fingerprint(frame) != _frame_fingerprint(
        pd.DataFrame({"a": ["x", "None", "y"]})
    )


def test_frame_fingerprint_output_changes_with_the_missing_marker():
    """
    Test that `None` and `NaN` in an object column, which pandas hashes
    alike, give different fingerprints.
    """
    with_none = pd.DataFrame({"a": ["x", None, "y"]})
    with_nan = pd.DataFrame({"a": ["x", np.nan, "y"]})

    assert _frame_fingerprint(with_none) != _frame_fingerprint(with_nan)


def test_frame_fingerprint_output_changes_with_many_categories():
    """
    Test that categorical columns with 200 categories, whose dtype repr is
    cut short, have different fingerprints when a category is added or the
    order of two ordered categories changes.
    """
    categories = [f"c{i}" for i in range(200)]
    values = categories[:10]
    base = pd.DataFrame({"a": pd.Categorical(values, categories=categories)})
    longer = [*categories[:100], "extra", *categories[100:]]
    added = pd.DataFrame({"a": pd.Categorical(values, categories=longer)})
    swapped = categories.copy()
    swapped[50], swapped[51] = swapped[51], swapped[50]
    ordered = pd.DataFrame({
        "a": pd.Categorical(values, categories=categories, ordered=True)
    })
    reordered = pd.DataFrame({
        "a": pd.Categorical(values, categories=swapped, ordered=True)
    })

    assert _frame_fingerprint(base) != _frame_fingerprint(added)
    assert _frame_fingerprint(ordered) != _frame_fingerprint(reordered)
    assert _frame_fingerprint(base) != _frame_fingerprint(ordered)


@pytest.mark.parametrize("as_index", [True, False], ids=["index", "date column"])
def test_frame_fingerprint_output_changes_with_the_rules_of_a_time_zone(as_index):
    """
    Test that the same instants in two time zones of the same name and other
    rules ('Europe/Madrid' and a fixed offset of one hour called
    'Europe/Madrid') have different fingerprints: pandas hashes the instants
    and the dtype only names the zone.
    """
    import datetime

    dates = pd.date_range("2023-01-01", periods=200, freq="D", tz="Europe/Madrid")
    fixed = dates.tz_convert(
        datetime.timezone(datetime.timedelta(hours=1), "Europe/Madrid")
    )
    values = np.arange(200, dtype=float)
    if as_index:
        first = pd.DataFrame({"y": values}, index=dates)
        second = pd.DataFrame({"y": values}, index=fixed)
    else:
        first = pd.DataFrame({"date": dates, "y": values})
        second = pd.DataFrame({"date": fixed, "y": values})

    assert repr(first.index.dtype) == repr(second.index.dtype)
    assert _frame_fingerprint(first) != _frame_fingerprint(second)
