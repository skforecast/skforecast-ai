# Unit test exog_encoding

import pandas as pd
import pytest

from skforecast_ai._future_exog import exog_encoding

_EXOG = pd.DataFrame(
    {"zona": ["Cádiz", "Peñíscola"]},
    index=pd.DatetimeIndex(["2023-03-02", "2023-03-03"], name="fecha"),
)


def test_exog_encoding_output_when_exog_is_None():
    """
    Test that without future exogenous variables the encoding is UTF-8: the
    script reads no `exog_future.csv`.
    """
    assert exog_encoding(None) == "utf-8"


@pytest.mark.parametrize("encoding", ["utf-8", "cp1252"], ids=lambda dt: dt)
def test_exog_encoding_output_when_encoding_kept_in_attrs(encoding):
    """
    Test that the encoding `load_exog` keeps in `attrs` is the one the
    script reads `exog_future.csv` with.
    """
    exog = _EXOG.copy()
    exog.attrs["encoding"] = encoding

    assert exog_encoding(exog) == encoding


@pytest.mark.parametrize(
    "attrs",
    [{}, {"encoding": "latin-1"}, {"encoding": "utf-16"}, {"encoding": None}],
    ids=["no attrs", "latin-1", "utf-16", "None"],
)
def test_exog_encoding_output_is_utf8_when_frame_not_read_by_load_exog(attrs):
    """
    Test that a frame not read by `load_exog`, which `to_csv()` saves in
    UTF-8, is read in UTF-8, also when its `attrs` name an encoding that is
    not read here (a frame read by another tool): it never reaches the
    script.
    """
    exog = _EXOG.copy()
    exog.attrs.update(attrs)

    assert exog_encoding(exog) == "utf-8"
