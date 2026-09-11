# Unit test detect_categorical_exog

import pandas as pd

from skforecast_ai.profiling.data_profile import detect_categorical_exog


def test_detect_categorical_exog_output():
    """
    Test that category, object and bool columns are reported as
    categorical while numeric columns are not.
    """
    data = pd.DataFrame({
        "cat":  pd.Series(["x", "y", "x"], dtype="category"),
        "obj":  ["x", "y", "x"],
        "flag": [True, False, True],
        "num":  [1.0, 2.0, 3.0],
    })

    assert detect_categorical_exog(data, ["cat", "obj", "flag", "num"]) == ["cat", "obj", "flag"]
