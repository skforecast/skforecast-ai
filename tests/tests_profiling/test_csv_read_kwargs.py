# Unit test csv_read_kwargs

import pytest

from skforecast_ai.profiling.data_profile import csv_read_kwargs


@pytest.mark.parametrize(
    "sep, decimal, expected",
    [
        (",", ".", {}),
        (";", ".", {"sep": ";", "decimal": "."}),
        (";", ",", {"sep": ";", "decimal": ","}),
        ("\t", ".", {"sep": "\t", "decimal": "."}),
        ("\t", ",", {"sep": "\t", "decimal": ","}),
    ],
    ids=lambda dt: f"{dt!r}",
)
def test_csv_read_kwargs_output(sep, decimal, expected):
    """
    Test that no argument is returned for the default dialect (so the file is
    read with exactly `pd.read_csv(path)`), and both `sep` and `decimal`
    otherwise.
    """
    assert csv_read_kwargs(sep, decimal) == expected
