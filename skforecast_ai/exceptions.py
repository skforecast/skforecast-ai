"""Custom exceptions for skforecast-ai."""


class LLMRequiredError(Exception):
    """
    Raised when a method that requires an LLM is called without one.

    Parameters
    ----------
    method_name : str
        Name of the method that requires an LLM.
    """

    def __init__(self, method_name: str) -> None:
        super().__init__(
            f"`{method_name}()` requires an LLM. "
            "Pass `llm=...` when creating ForecastingAssistant."
        )
