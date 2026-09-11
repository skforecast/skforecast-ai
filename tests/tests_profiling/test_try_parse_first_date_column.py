# Unit test _try_parse_first_date_column

import pandas as pd

from skforecast_ai.profiling.data_profile import _try_parse_first_date_column


def test_try_parse_first_date_column_skips_unparseable_columns():
    """
    Test that a leading text column that is not a date is left untouched
    and the next parseable column is converted instead.
    """
    data = pd.DataFrame({
        "name": ["a", "b", "c"],
        "date": ["2023-01-01", "2023-01-02", "2023-01-03"],
        "y": [1.0, 2.0, 3.0],
    })

    parsed = _try_parse_first_date_column(data)

    assert parsed["name"].tolist() == ["a", "b", "c"]
    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])


def test_try_parse_first_date_column_converts_only_the_first_date_column():
    """
    Test that once a column is parsed the remaining text columns are left
    as they are, even when they would also parse.
    """
    data = pd.DataFrame({
        "date": ["2023-01-01", "2023-01-02"],
        "other": ["2024-01-01", "2024-01-02"],
    })

    parsed = _try_parse_first_date_column(data)

    assert pd.api.types.is_datetime64_any_dtype(parsed["date"])
    assert parsed["other"].tolist() == ["2024-01-01", "2024-01-02"]
