# Unit test guessed_date_format

import re

import numpy as np
import pandas as pd
import pytest

from skforecast_ai._dates import guessed_date_format


@pytest.mark.parametrize(
    "values, expected",
    [
        (["2012-01-13", "2012-01-14"], "%Y-%m-%d"),
        (["13/01/2012", "01/02/2012"], "%d/%m/%Y"),
        ([None, "NaT", "", "2012-01-13T10:00:00+01:00"], "%Y-%m-%dT%H:%M:%S%z"),
        ([pd.Timestamp("2012-01-12"), "13/01/2012"], None),
        (list(np.array(["2012-01-13"], dtype=str)), None),
        (["09:30", "10:30"], None),
        ([None, np.nan], None),
    ],
    ids=[
        "iso", "day_first", "after_missing_values",
        "timestamp_first", "numpy_str", "time_of_day", "no_date",
    ],
)
def test_guessed_date_format_output(values, expected):
    """
    Test that the format is guessed from the first date as pandas guesses it
    (skipping missing values and the text read as no date), only when that
    date is exactly a str, and without the pandas warning on day-first
    formats.
    """
    assert guessed_date_format(pd.Series(values, dtype=object)) == expected


def test_guessed_date_format_FutureWarning_when_zone_name():
    """
    Test that the pandas warning about a zone name it drops ('CET') is not
    hidden, as the generated script shows it too.
    """
    warn_msg = re.escape(
        'Parsed string "2012-03-20 00:00:00 CET" included an un-recognized '
        'timezone "CET".'
    )
    with pytest.warns(FutureWarning, match=warn_msg):
        date_format = guessed_date_format(
            pd.Series(["2012-03-20 00:00:00 CET"], dtype=object)
        )

    assert date_format == "%Y-%m-%d %H:%M:%S CET"
