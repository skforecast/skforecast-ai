# Unit test SkforecastAIError

import pickle
import re

import pytest

import skforecast_ai
from skforecast_ai.exceptions import (
    ERROR_CODES,
    AllCandidatesFailedError,
    DataContentError,
    DataNotFoundError,
    ForecastExecutionError,
    InvalidInputError,
    InvalidInputTypeError,
    LLMCallError,
    LLMRequiredError,
    SkforecastAIError,
    _reported_type_name,
)


def test_skforecast_ai_error_codes_are_the_closed_set():
    """
    Test that the codes are the closed set of the error model, in order.
    """
    assert ERROR_CODES == (
        "invalid_argument",
        "insufficient_data",
        "data_not_found",
        "data_unreadable",
        "missing_dependency",
        "execution_failed",
        "all_candidates_failed",
        "llm_required",
        "llm_call_failed",
        "internal_error",
    )


@pytest.mark.parametrize(
    "error_class, builtin, expected_code",
    [
        (InvalidInputError, ValueError, "invalid_argument"),
        (InvalidInputTypeError, TypeError, "invalid_argument"),
        (DataContentError, ValueError, "invalid_argument"),
        (DataNotFoundError, FileNotFoundError, "data_not_found"),
    ],
    ids=lambda dt: f"{dt.__name__ if isinstance(dt, type) else dt}",
)
def test_skforecast_ai_error_init_subclass_of_builtin_with_default_code(
    error_class, builtin, expected_code
):
    """
    Test that each error class derives from SkforecastAIError and from the
    built-in exception raised before the hierarchy existed, so existing
    `except` clauses still catch it, and that it has its default code, no
    field and no hint, with the message as `str(exc)`.
    """
    error = error_class("Something is wrong.")

    assert isinstance(error, SkforecastAIError)
    assert isinstance(error, builtin)
    assert error.code == expected_code
    assert error.field is None
    assert error.hint is None
    assert str(error) == "Something is wrong."
    assert error.args == ("Something is wrong.",)


def test_skforecast_ai_error_init_InvalidInputTypeError_is_InvalidInputError():
    """
    Test that InvalidInputTypeError is also an InvalidInputError and a
    ValueError, so catching InvalidInputError covers every invalid input.
    """
    error = InvalidInputTypeError("Bad type.")

    assert isinstance(error, InvalidInputError)
    assert isinstance(error, ValueError)
    assert isinstance(error, TypeError)


def test_skforecast_ai_error_init_hint_not_in_message():
    """
    Test that code, field and hint are stored as given and that the hint is
    not part of `str(exc)`.
    """
    error = InvalidInputError(
        "Not enough observations.",
        code  = "insufficient_data",
        field = "steps",
        hint  = "Pass a smaller `steps`.",
    )

    assert error.code == "insufficient_data"
    assert error.field == "steps"
    assert error.hint == "Pass a smaller `steps`."
    assert str(error) == "Not enough observations."


def test_skforecast_ai_error_init_ValueError_when_code_unknown():
    """
    Test that a code outside the closed set raises ValueError.
    """
    err_msg = re.escape(
        f"Unknown error code 'bad_code'. Valid codes: {list(ERROR_CODES)}."
    )
    with pytest.raises(ValueError, match=err_msg):
        InvalidInputError("Message.", code="bad_code")


@pytest.mark.parametrize(
    "error_class",
    [InvalidInputError, InvalidInputTypeError, DataContentError, DataNotFoundError],
    ids=lambda dt: dt.__name__,
)
def test_skforecast_ai_error_pickle_keeps_code_field_and_hint(error_class):
    """
    Test that an error survives a pickle round trip with its message, code,
    field and hint.
    """
    error = error_class(
        "Message.", code="insufficient_data", field="data", hint="Remedy."
    )
    restored = pickle.loads(pickle.dumps(error))

    assert type(restored) is error_class
    assert str(restored) == "Message."
    assert restored.code == "insufficient_data"
    assert restored.field == "data"
    assert restored.hint == "Remedy."


def test_skforecast_ai_error_existing_errors_derive_from_base_with_their_code():
    """
    Test that the errors that existed before the hierarchy derive from
    SkforecastAIError, keep their message and carry their own code.
    """
    errors = {
        "llm_required": LLMRequiredError("ask"),
        "llm_call_failed": LLMCallError("openai:gpt-5.5", RuntimeError("boom")),
        "execution_failed": ForecastExecutionError(
            original_error      = ValueError("boom"),
            generated_code      = "x = 1",
            execution_traceback = "Traceback",
        ),
        "all_candidates_failed": AllCandidatesFailedError({}),
    }

    for code, error in errors.items():
        assert isinstance(error, SkforecastAIError)
        assert error.code == code
        assert error.field is None
        assert error.hint is None
    assert str(errors["llm_required"]) == (
        "`ask()` requires an LLM. Pass `llm=...` when creating "
        "ForecastingAssistant."
    )


@pytest.mark.parametrize(
    "name",
    [
        "SkforecastAIError",
        "InvalidInputError",
        "InvalidInputTypeError",
        "DataContentError",
        "DataNotFoundError",
    ],
    ids=lambda dt: f"name: {dt}",
)
def test_skforecast_ai_error_importable_from_package_root(name):
    """
    Test that the new error classes are importable from the package root,
    like the other exceptions.
    """
    assert getattr(skforecast_ai, name) is getattr(skforecast_ai.exceptions, name)
    assert name in skforecast_ai.__all__


def test_skforecast_ai_error_init_DataContentError_is_InvalidInputError():
    """
    Test that DataContentError is also an InvalidInputError and a
    ValueError, so the `except` clauses written for those still catch it,
    and that failure summaries report it as a ValueError.
    """
    error = DataContentError("The data has missing values.", field="data")

    assert isinstance(error, InvalidInputError)
    assert isinstance(error, ValueError)
    assert not isinstance(error, InvalidInputTypeError)
    assert (error.code, error.field, error.hint) == (
        "invalid_argument", "data", None
    )
    assert _reported_type_name(error) == "ValueError"
