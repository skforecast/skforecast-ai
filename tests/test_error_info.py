# Unit test ErrorInfo.from_exception

import pytest
from pydantic import ValidationError

from skforecast_ai import ForecastingAssistant, ForecastingProfile, ForecastPlan
from skforecast_ai.exceptions import (
    AllCandidatesFailedError,
    DataNotFoundError,
    ForecastExecutionError,
    InvalidInputError,
    InvalidInputTypeError,
)
from skforecast_ai.schemas import CandidateFailure, ErrorInfo

# Fixtures
from .fixtures_assistant import df_single


def _profile_and_plan_dump() -> tuple[ForecastingProfile, dict]:
    """
    Profile `df_single` and return the profile with the dump of a 7-step plan.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")

    return profile, assistant.plan(profile, steps=7).model_dump()


@pytest.mark.parametrize(
    "error, expected",
    [
        (
            InvalidInputError("`steps` must be positive.", field="steps"),
            ErrorInfo(
                code    = "invalid_argument",
                message = "`steps` must be positive.",
                field   = "steps",
            ),
        ),
        (
            InvalidInputTypeError("`test_size` must be an int.", field="test_size"),
            ErrorInfo(
                code    = "invalid_argument",
                message = "`test_size` must be an int.",
                field   = "test_size",
            ),
        ),
        (
            DataNotFoundError("CSV file not found: 'x.csv'.", field="data"),
            ErrorInfo(
                code    = "data_not_found",
                message = "CSV file not found: 'x.csv'.",
                field   = "data",
            ),
        ),
        (
            InvalidInputError(
                "Too few folds.", code="insufficient_data", hint="Use less."
            ),
            ErrorInfo(
                code    = "insufficient_data",
                message = "Too few folds.",
                hint    = "Use less.",
            ),
        ),
        (
            ForecastExecutionError(
                original_error      = KeyError("x"),
                generated_code      = "secret = 1",
                execution_traceback = "Traceback (most recent call last)",
            ),
            ErrorInfo(
                code    = "execution_failed",
                message = (
                    "Error executing generated forecasting code.\n\n"
                    "  KeyError: 'x'"
                ),
            ),
        ),
    ],
    ids=["invalid", "type", "not_found", "hint", "execution"],
)
def test_error_info_from_exception_skforecast_ai_error(error, expected):
    """
    Test that a SkforecastAIError keeps its code, message, field and hint,
    and that the generated code and the traceback of an execution error are
    left out.
    """
    info = ErrorInfo.from_exception(error)

    assert info == expected


def test_error_info_from_exception_AllCandidatesFailedError_without_failures():
    """
    Test that the message of an AllCandidatesFailedError keeps the summary
    of every candidate and leaves out how to inspect `exc.failures`, which
    a reader outside Python cannot reach.
    """
    failures = {
        "lgbm": CandidateFailure(
            error_type="ValueError", message="bad value\nmore", traceback="tb"
        ),
        "ridge": CandidateFailure(
            error_type="ImportError", message="no module", traceback="tb"
        ),
    }
    info = ErrorInfo.from_exception(AllCandidatesFailedError(failures))

    assert info == ErrorInfo(
        code    = "all_candidates_failed",
        message = (
            "All 2 candidate configuration(s) failed to run, so there is no "
            "ranking to report.\n\n"
            "  - lgbm: ValueError: bad value\n"
            "  - ridge: ImportError: no module"
        ),
    )


@pytest.mark.parametrize(
    "update, expected",
    [
        (
            {"steps": 0},
            ErrorInfo(
                code    = "invalid_argument",
                message = (
                    "`steps` must be an integer greater than or equal to 1, "
                    "got 0."
                ),
                field   = "steps",
            ),
        ),
        (
            {"interval": "x"},
            ErrorInfo(
                code    = "invalid_argument",
                message = "Input should be a valid list",
                field   = "interval",
            ),
        ),
        (
            {"steps": 0, "interval": "x"},
            ErrorInfo(
                code    = "invalid_argument",
                message = (
                    "`steps` must be an integer greater than or equal to 1, "
                    "got 0. (1 more validation error(s) not shown.)"
                ),
                field   = "steps",
            ),
        ),
        (
            {"forecaster_kwargs": {"bogus": 1}},
            ErrorInfo(
                code    = "invalid_argument",
                message = (
                    "`forecaster_kwargs` of 'ForecasterRecursive' cannot "
                    "contain ['bogus']. Allowed keys: ['calendar_features', "
                    "'categorical_features', 'differentiation', "
                    "'dropna_from_series', 'lags', 'transformer_exog', "
                    "'transformer_y', 'window_features']."
                ),
                field   = "forecaster_kwargs",
            ),
        ),
    ],
    ids=["field_validator", "pydantic_type", "several", "model_validator"],
)
def test_error_info_from_exception_ValidationError_of_plan(update, expected):
    """
    Test that a ValidationError is described through its first error: the
    code, message and field of the SkforecastAIError raised by the
    validator, the location of the error as field, the field of the inner
    error when the check is on the whole model, pydantic's message when no
    error of ours is involved, and the number of errors not shown.
    """
    _, plan_dump = _profile_and_plan_dump()
    if "forecaster_kwargs" in update:
        update = {
            "forecaster_kwargs": {
                **plan_dump["forecaster_kwargs"], **update["forecaster_kwargs"]
            }
        }
    with pytest.raises(ValidationError) as exc_info:
        ForecastPlan.model_validate({**plan_dump, **update})

    info = ErrorInfo.from_exception(exc_info.value)

    assert info == expected


def test_error_info_from_exception_ValidationError_nested_location():
    """
    Test that the field of an error in a nested model is its full location.
    """
    profile, _ = _profile_and_plan_dump()
    dumped = profile.model_dump()
    dumped["data_profile"]["frequency"] = "D\n"
    with pytest.raises(ValidationError) as exc_info:
        ForecastingProfile.model_validate(dumped)

    info = ErrorInfo.from_exception(exc_info.value)

    assert info == ErrorInfo(
        code    = "invalid_argument",
        message = (
            "`frequency` must be a pandas frequency alias made of letters, "
            "digits and hyphens, for example 'D', '15min' or 'W-SUN', got "
            "'D\\n'."
        ),
        field   = "data_profile.frequency",
    )


@pytest.mark.parametrize(
    "error, expected_message",
    [
        (KeyError("sid"), "KeyError: 'sid'"),
        (ValueError("\n  first line\nsecond line"), "ValueError: first line"),
        (RuntimeError(), "RuntimeError"),
        (ValueError("x" * 300), "ValueError: " + "x" * 185 + "..."),
    ],
    ids=["key_error", "first_line", "empty", "truncated"],
)
def test_error_info_from_exception_internal_error(error, expected_message):
    """
    Test that an exception skforecast-ai did not raise is an internal error
    described by its type and the first line of its message, truncated to
    200 characters.
    """
    info = ErrorInfo.from_exception(error)

    assert info == ErrorInfo(code="internal_error", message=expected_message)
    assert len(info.message) <= 200


def test_error_info_from_exception_serializes_to_json():
    """
    Test that the description is plain data that serializes to JSON.
    """
    info = ErrorInfo.from_exception(
        InvalidInputError("Bad `lags`.", field="lags", hint="Use an int.")
    )

    assert info.model_dump_json() == (
        '{"code":"invalid_argument","message":"Bad `lags`.","field":"lags",'
        '"hint":"Use an int."}'
    )


@pytest.mark.parametrize(
    "update, expected",
    [
        (
            {"metrics_to_compute": ["nope"]},
            ErrorInfo(
                code    = "invalid_argument",
                message = (
                    "Unknown metric 'nope'. Supported metrics: "
                    "['mean_squared_error', 'mean_absolute_error', "
                    "'mean_absolute_percentage_error', 'mean_squared_log_error', "
                    "'mean_absolute_scaled_error', "
                    "'root_mean_squared_scaled_error', 'median_absolute_error', "
                    "'symmetric_mean_absolute_percentage_error']."
                ),
                field   = "metrics_to_compute",
            ),
        ),
        (
            {"forecaster_kwargs": {"lags": 0}},
            ErrorInfo(
                code    = "invalid_argument",
                message = "`lags` must be positive integers (>= 1), got 0.",
                field   = "forecaster_kwargs",
            ),
        ),
    ],
    ids=["metrics_to_compute", "forecaster_kwargs_lags"],
)
def test_error_info_from_exception_ValidationError_names_the_plan_field(
    update, expected
):
    """
    Test that an invalid entry of `metrics_to_compute`, or invalid lags inside
    `forecaster_kwargs`, are blamed on that field of the plan, not on the
    `metric` or `lags` argument of plan().
    """
    _, plan_dump = _profile_and_plan_dump()
    if "forecaster_kwargs" in update:
        update = {
            "forecaster_kwargs": {
                **plan_dump["forecaster_kwargs"], **update["forecaster_kwargs"]
            }
        }
    with pytest.raises(ValidationError) as exc_info:
        ForecastPlan.model_validate({**plan_dump, **update})

    info = ErrorInfo.from_exception(exc_info.value)

    assert info == expected


def test_error_info_from_exception_ValidationError_of_union_value():
    """
    Test that a value matching no member of a union is one error: the field
    is the location of the value, without the member pydantic appends, and
    the message joins the message of each member.
    """
    profile, _ = _profile_and_plan_dump()
    dumped = profile.model_dump()
    dumped["data_profile"]["target"] = 5
    with pytest.raises(ValidationError) as exc_info:
        ForecastingProfile.model_validate(dumped)

    info = ErrorInfo.from_exception(exc_info.value)

    assert info == ErrorInfo(
        code    = "invalid_argument",
        message = "Input should be a valid string; Input should be a valid list",
        field   = "data_profile.target",
    )


def test_error_info_from_exception_ValidationError_sibling_fields_not_a_union():
    """
    Test that errors on two different fields that received the same object
    (None) are not taken for the members of a union: the field is the first
    one and the other error is counted as not shown.
    """
    profile, plan_dump = _profile_and_plan_dump()
    with pytest.raises(ValidationError) as exc_info:
        ForecastPlan.model_validate(
            {**plan_dump, "forecaster": None, "use_exog": None}
        )
    dumped = profile.model_dump()
    dumped["data_profile"]["n_series"] = None
    dumped["data_profile"]["target_dtype"] = None
    with pytest.raises(ValidationError) as exc_info_nested:
        ForecastingProfile.model_validate(dumped)

    info = ErrorInfo.from_exception(exc_info.value)
    info_nested = ErrorInfo.from_exception(exc_info_nested.value)

    assert info == ErrorInfo(
        code    = "invalid_argument",
        message = (
            "Input should be a valid string (1 more validation error(s) not "
            "shown.)"
        ),
        field   = "forecaster",
    )
    assert info_nested == ErrorInfo(
        code    = "invalid_argument",
        message = (
            "Input should be a valid integer (1 more validation error(s) not "
            "shown.)"
        ),
        field   = "data_profile.n_series",
    )
