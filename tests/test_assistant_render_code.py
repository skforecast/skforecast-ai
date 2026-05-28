# Unit test forecast_code ForecastingAssistant

from skforecast_ai import ForecastingAssistant
from skforecast_ai.schemas import CodeGenerationResult

from tests.fixtures_assistant import df_single, df_multi_long, df_no_exog


# =============================================================================
# Tests: render_code — basic output
# =============================================================================
def test_render_code_output_when_single_series():
    """
    Test that render_code() produces a valid Python script
    containing expected imports and forecaster class for single series.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    code = assistant.render_code(profile.data_profile, plan)

    assert isinstance(code, str)
    assert "import" in code
    assert "ForecasterRecursive" in code
    assert "fit" in code or "predict" in code


def test_render_code_output_when_multi_series():
    """
    Test that render_code() produces code containing the
    multi-series forecaster class for a multi-series plan.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.plan(profile, steps=5)

    code = assistant.render_code(profile.data_profile, plan)

    assert isinstance(code, str)
    assert "ForecasterRecursiveMultiSeries" in code


def test_render_code_output_when_statistical():
    """
    Test that render_code() produces code for statistical
    models (ForecasterStats).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats"
    )

    code = assistant.render_code(profile.data_profile, plan)

    assert isinstance(code, str)
    assert "ForecasterStats" in code


def test_render_code_contains_frequency():
    """
    Test that generated code includes the frequency assignment.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    code = assistant.render_code(profile.data_profile, plan)

    assert "freq" in code.lower() or "asfreq" in code


# =============================================================================
# Tests: forecast_code — basic output
# =============================================================================
def test_forecast_code_output_when_single_series():
    """
    Test that forecast_code() returns a CodeGenerationResult with all
    fields populated for a single-series dataset.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single, target="sales", date_column="date", steps=10
    )

    assert isinstance(result, CodeGenerationResult)
    assert isinstance(result.code, str)
    assert result.plan.steps == 10
    assert result.profile is not None
    assert "import" in result.code


def test_forecast_code_output_when_forecaster_selected():
    """
    Test that forecast_code() generates code for an explicitly selected
    forecaster.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single,
        target="sales",
        date_column="date",
        steps=10,
        forecaster="ForecasterDirect",
    )

    assert result.plan.forecaster == "ForecasterDirect"
    assert "ForecasterDirect" in result.code


def test_forecast_code_output_when_no_exog():
    """
    Test that forecast_code() works correctly for data without exogenous
    variables.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_no_exog, target="sales", date_column="date", steps=10
    )

    assert isinstance(result, CodeGenerationResult)
    assert result.plan.use_exog is False


def test_forecast_code_output_when_interval_requested():
    """
    Test that forecast_code() includes interval logic when interval is
    specified.
    """
    assistant = ForecastingAssistant()
    result = assistant.forecast_code(
        data=df_single,
        target="sales",
        date_column="date",
        steps=10,
        interval=[10, 90],
    )

    assert result.plan.interval == [10, 90]
    assert "interval" in result.code.lower() or "predict_interval" in result.code
