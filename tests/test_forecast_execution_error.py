# Unit test ForecastExecutionError

from skforecast_ai.exceptions import ForecastExecutionError


def test_forecast_execution_error_init_location_is_none_by_default():
    """
    Test that a ForecastExecutionError built without a location, as code
    written for previous versions does, has None as failed line and
    statement, and that the message only shows the original error.
    """
    error = ForecastExecutionError(
        original_error      = ValueError("boom"),
        generated_code      = "x = 1",
        execution_traceback = "Traceback",
    )

    assert error.failed_line is None
    assert error.failed_statement is None
    assert str(error) == (
        "Error executing generated forecasting code.\n\n  ValueError: boom"
    )
