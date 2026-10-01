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


def test_try_parse_first_date_column_reads_day_first_dates_as_the_script():
    """
    Test that the dates are parsed with the format of the first date, as
    pandas.to_datetime does in the generated script, so '01/02/2012' after
    '13/01/2012' is the first of February.
    """
    data = pd.DataFrame({
        "date": ["13/01/2012", "01/02/2012", "02/02/2012"],
        "y": [1.0, 2.0, 3.0],
    })

    parsed = _try_parse_first_date_column(data)

    expected = pd.Series(
        pd.to_datetime(["2012-01-13", "2012-02-01", "2012-02-02"]), name="date"
    )
    pd.testing.assert_series_equal(parsed["date"], expected)
