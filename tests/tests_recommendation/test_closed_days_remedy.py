# Unit test closed_days_remedy recommendation/missing_values

from skforecast_ai.recommendation.missing_values import closed_days_remedy


def test_closed_days_remedy_output():
    """
    Test the advice for missing values on the days a business is closed
    (D9), shared by the errors of the evaluated dates, of the last windows
    and of the training rows: fill them with 0, after asking the user.
    """
    assert closed_days_remedy("Saturdays and Sundays") == (
        "If the business is closed on Saturdays and Sundays, fill them with 0 "
        "in the data, after asking the user"
    )
