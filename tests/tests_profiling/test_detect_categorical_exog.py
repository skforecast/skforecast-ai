# Unit test detect_categorical_exog

import pandas as pd

from skforecast_ai.profiling.data_profile import detect_categorical_exog


def test_detect_categorical_exog_output():
    """
    Test that category, object, text and bool columns are reported as
    categorical while numeric columns are not: text is `object` in pandas 2
    and `str` in pandas 3, and a `string` column (missing values as
    `pd.NA`) is text too.
    """
    data = pd.DataFrame({
        "cat":    pd.Series(["x", "y", "x"], dtype="category"),
        "obj":    pd.Series(["x", "y", "x"], dtype=object),
        "text":   ["x", "y", "x"],
        "string": pd.Series(["x", "y", None], dtype="string"),
        "flag":   [True, False, True],
        "num":    [1.0, 2.0, 3.0],
    })

    result = detect_categorical_exog(
        data, ["cat", "obj", "text", "string", "flag", "num"]
    )

    assert result == ["cat", "obj", "text", "string", "flag"]
