# Unit test exog_as_injected

import pandas as pd

from skforecast_ai.execution.forecast_runner import exog_as_injected

from tests.fixtures_future_exog import profile_business, profile_daily

_DATES = pd.date_range("2023-04-11", periods=3, freq="D")


def test_exog_as_injected_output_when_data_has_date_column():
    """
    Test that, when the data has a date column, the index of the future
    exogenous variables becomes that column (whatever its name), as the
    generated code sets it as the index, and the input is not modified.
    """
    exog = pd.DataFrame(
        {"promo": [0.0, 1.0, 0.0]}, index=_DATES.rename("fecha")
    )

    result = exog_as_injected(exog, profile_daily)

    expected = pd.DataFrame({"date": _DATES, "promo": [0.0, 1.0, 0.0]})
    pd.testing.assert_frame_equal(result, expected)
    assert exog.index.name == "fecha"


def test_exog_as_injected_output_when_exog_has_date_column():
    """
    Test that future exogenous variables that already hold the date column
    of the data are returned as they are.
    """
    exog = pd.DataFrame({"date": _DATES, "promo": [0.0, 1.0, 0.0]})

    result = exog_as_injected(exog, profile_daily)

    assert result is exog


def test_exog_as_injected_output_when_data_has_no_date_column():
    """
    Test that, when the data is indexed by date (no date column), the future
    exogenous variables are returned as they are, indexed by date.
    """
    exog = pd.DataFrame({"x": [0.0, 1.0, 0.0]}, index=_DATES)

    result = exog_as_injected(exog, profile_business)

    assert result is exog
