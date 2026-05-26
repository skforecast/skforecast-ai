# Unit test __init__ ForecastingAssistant

from skforecast_ai import ForecastingAssistant


# =============================================================================
# Tests: constructor
# =============================================================================
def test_init_stores_attributes():
    """
    Test that ForecastingAssistant stores llm, base_url, api_key, and
    send_data_to_llm attributes correctly.
    """
    assistant = ForecastingAssistant(
        llm="openai:gpt-4o-mini",
        base_url="http://localhost:8080/v1",
        api_key="sk-test-key-123",
        send_data_to_llm=True,
    )
    assert assistant.llm == "openai:gpt-4o-mini"
    assert assistant.base_url == "http://localhost:8080/v1"
    assert assistant.api_key == "sk-test-key-123"
    assert assistant.send_data_to_llm is True


def test_init_defaults():
    """
    Test that ForecastingAssistant uses correct defaults when no arguments
    are provided: llm=None, base_url=None, api_key=None,
    send_data_to_llm=False.
    """
    assistant = ForecastingAssistant()
    assert assistant.llm is None
    assert assistant.base_url is None
    assert assistant.api_key is None
    assert assistant.send_data_to_llm is False
