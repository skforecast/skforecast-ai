# Unit test run ForecastingAssistant

import pandas as pd

from skforecast_ai import ForecastingAssistant, RunResult

from .fixtures_execution import df_single


# Tests: assistant.run()


def test_assistant_run_returns_RunResult():
    """
    Test that assistant.run() returns a RunResult instance with all fields
    populated.
    """
    assistant = ForecastingAssistant()
    result = assistant.run(
        data         = df_single,
        target       = "sales",
        date_column  = "date",
        horizon      = 10,
    )

    assert isinstance(result, RunResult)
    assert result.profile is not None
    assert result.plan is not None
    assert result.code is not None
    assert result.metric_value > 0
    assert result.metric_name == "mean_absolute_error"
    assert result.predictions is not None


def test_assistant_run_predictions_length_matches_horizon():
    """
    Test that the number of prediction rows matches the requested horizon.
    """
    horizon = 7
    assistant = ForecastingAssistant()
    result = assistant.run(
        data         = df_single,
        target       = "sales",
        date_column  = "date",
        horizon      = horizon,
    )

    assert len(result.predictions) == horizon


def test_assistant_run_includes_code_string():
    """
    Test that the generated code field is a non-empty string containing
    skforecast imports.
    """
    assistant = ForecastingAssistant()
    result = assistant.run(
        data         = df_single,
        target       = "sales",
        date_column  = "date",
        horizon      = 5,
    )

    assert isinstance(result.code, str)
    assert len(result.code) > 0
    assert "skforecast" in result.code
