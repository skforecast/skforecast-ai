# Unit test forecast_code ForecastingAssistant

from skforecast_ai import ForecastingAssistant
from skforecast_ai.schemas import CodeGenerationResult

from tests.fixtures_assistant import df_single, df_multi_long, df_no_exog


# =============================================================================
# Tests: forecast_code with pre-computed profile and plan
# =============================================================================
def test_forecast_code_with_profile_and_plan_when_single_series():
    """
    Test that forecast_code() with pre-computed profile and plan produces
    a valid Python script for single series.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.forecast_code(
        data=df_single, target="sales", steps=10, profile=profile, plan=plan
    )

    assert isinstance(result, CodeGenerationResult)
    assert isinstance(result.code, str)
    assert "import" in result.code
    assert "ForecasterRecursive" in result.code
    assert "fit" in result.code or "predict" in result.code


def test_forecast_code_with_profile_and_plan_when_multi_series():
    """
    Test that forecast_code() with pre-computed profile and plan produces
    code containing the multi-series forecaster class.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(
        data=df_multi_long,
        target="value",
        date_column="date",
        series_id_column="series_id",
    )
    plan = assistant.plan(profile, steps=5)

    result = assistant.forecast_code(
        data=df_multi_long, target="value", steps=5, profile=profile, plan=plan
    )

    assert isinstance(result, CodeGenerationResult)
    assert "ForecasterRecursiveMultiSeries" in result.code


def test_forecast_code_with_profile_and_plan_when_statistical():
    """
    Test that forecast_code() with pre-computed profile and plan produces
    code for statistical models (ForecasterStats).
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(
        profile, steps=10, forecaster="ForecasterStats"
    )

    result = assistant.forecast_code(
        data=df_single, target="sales", steps=10, profile=profile, plan=plan
    )

    assert isinstance(result, CodeGenerationResult)
    assert "ForecasterStats" in result.code


def test_forecast_code_with_profile_and_plan_contains_frequency():
    """
    Test that generated code includes the frequency assignment.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=10)

    result = assistant.forecast_code(
        data=df_single, target="sales", steps=10, profile=profile, plan=plan
    )

    assert "freq" in result.code.lower() or "asfreq" in result.code


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
