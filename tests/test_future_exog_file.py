# Unit test future_exog_file

import pandas as pd
import pytest

from skforecast_ai._future_exog import future_exog_file
from skforecast_ai.schemas import FutureExogFile

from tests.fixtures_future_exog import exog_day_first, profile_day_first

_EXOG = pd.DataFrame(
    {"zona": ["Cádiz", "Peñíscola"]},
    index=pd.DatetimeIndex(["2023-03-02", "2023-03-03"], name="fecha"),
)


def test_future_exog_file_output_when_exog_is_None():
    """
    Test that without future exogenous variables the file is
    `exog_future.csv` with the defaults of `to_csv()`.
    """
    assert future_exog_file(None, profile_day_first) == FutureExogFile()


@pytest.mark.parametrize(
    "attrs",
    [
        {},
        {
            "exog_file": FutureExogFile(
                path="/data/futuro.csv", sep=";", decimal=",", encoding="cp1252"
            )
        },
        {"exog_file": "/data/futuro.csv"},
        {"encoding": "cp1252", "date_format": "%d/%m/%Y"},
    ],
    ids=["no attrs", "FutureExogFile", "path", "loose keys"],
)
def test_future_exog_file_output_is_exog_future_csv_whatever_the_attrs(attrs):
    """
    Test that a frame is read from `exog_future.csv`, which `to_csv()` writes
    with ',', '.' and UTF-8, whatever its `attrs` hold, a `FutureExogFile`
    included: a file reaches the script only by its path (see
    `read_future_exog`), so a frame derived from one read before is not
    taken for that file.
    """
    exog = _EXOG.copy()
    exog.attrs.update(attrs)

    assert future_exog_file(exog, profile_day_first) == FutureExogFile()


def test_future_exog_file_output_when_frame_in_memory_has_text_dates():
    """
    Test that a frame passed in memory with text dates written day first is
    read from `exog_future.csv` with the format of its own dates (see
    `exog_date_format`).
    """
    expected = FutureExogFile(date_format="%d/%m/%Y")

    assert future_exog_file(exog_day_first, profile_day_first) == expected
