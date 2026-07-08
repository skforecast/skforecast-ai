"""Unit tests for select_dropna_from_series."""

from skforecast_ai.recommendation import select_dropna_from_series


def test_select_dropna_true_when_missing_and_non_tolerant_estimator():
    """
    Test select_dropna_from_series returns True when missing values exist
    and the estimator does not tolerate NaN natively (Ridge).
    """
    result = select_dropna_from_series(
        estimator="Ridge",
        missing_target={"y": 3},
        missing_exog={},
        task_type="single_series",
    )

    assert result is True


def test_select_dropna_false_when_missing_and_nan_tolerant_estimator():
    """
    Test select_dropna_from_series returns False when missing values exist
    but the estimator handles NaN natively (LGBMRegressor).
    """
    result = select_dropna_from_series(
        estimator="LGBMRegressor",
        missing_target={"y": 5},
        missing_exog={},
        task_type="single_series",
    )

    assert result is False


def test_select_dropna_false_when_no_missing_values():
    """
    Test select_dropna_from_series returns False when no missing values
    exist, regardless of estimator.
    """
    result = select_dropna_from_series(
        estimator="Ridge",
        missing_target={},
        missing_exog={},
        task_type="single_series",
    )

    assert result is False


def test_select_dropna_none_when_statistical():
    """
    Test select_dropna_from_series returns None for statistical task types
    (the parameter does not apply).
    """
    result = select_dropna_from_series(
        estimator="Arima",
        missing_target={"y": 3},
        missing_exog={},
        task_type="statistical",
    )

    assert result is None
