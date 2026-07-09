################################################################################
#                               Exceptions                                     #
#                                                                              #
# Custom exceptions for skforecast-ai                                          #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################


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


class ForecastExecutionError(Exception):
    """
    Raised when the generated forecasting code fails during exec().

    The short message surfaces the original error. The full generated
    code and traceback are available as attributes for debugging.

    Parameters
    ----------
    original_error : Exception
        The exception raised during code execution.
    generated_code : str
        The generated Python code that was executed.
    execution_traceback : str
        The full formatted traceback from execution.

    Attributes
    ----------
    original_error : Exception
        The exception raised during code execution.
    generated_code : str
        The generated Python code that was executed.
    execution_traceback : str
        The full formatted traceback from execution.
    """

    def __init__(
        self,
        original_error: Exception,
        generated_code: str,
        execution_traceback: str,
    ) -> None:
        self.original_error = original_error
        self.generated_code = generated_code
        self.execution_traceback = execution_traceback

        error_type = type(original_error).__name__
        error_msg = str(original_error)
        message = (
            f"Error executing generated forecasting code.\n\n"
            f"  {error_type}: {error_msg}"
        )
        super().__init__(message)
