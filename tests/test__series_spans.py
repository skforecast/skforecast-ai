# Unit test _series_spans

import numpy as np
import pandas as pd

from skforecast_ai._last_window import _series_spans
from skforecast_ai.profiling import create_data_profile


def test_series_spans_output_when_long_rows_are_not_sorted():
    """
    Test that the span of each series of long data goes from its first to
    its last date whatever the order of the rows, with a value only on the
    dates it has one: series 'a' covers 60 days, and series 'b' the last 40
    with two dates missing and one value missing.
    """
    index = pd.date_range("2023-01-01", periods=60, freq="D")
    rows_b = pd.DataFrame({
        "date": index[20:], "series": "b", "value": np.arange(40, dtype=float)
    }).drop([5, 6])
    rows_b.loc[10, "value"] = np.nan
    data = pd.concat([
        pd.DataFrame({
            "date": index, "series": "a", "value": np.arange(60, dtype=float)
        }),
        rows_b,
    ])
    shuffled = data.sample(frac=1, random_state=123)
    profile = create_data_profile(
        data, target="value", date_column="date", series_id_column="series"
    )

    result = _series_spans(shuffled, profile)

    assert sorted(result) == ["a", "b"]
    dates_a, present_a = result["a"]
    dates_b, present_b = result["b"]
    pd.testing.assert_index_equal(dates_a, index, check_names=False)
    pd.testing.assert_index_equal(dates_b, index[20:], check_names=False)
    assert present_a.all()
    expected_b = np.ones(40, dtype=bool)
    expected_b[[5, 6, 10]] = False
    np.testing.assert_array_equal(present_b, expected_b)
