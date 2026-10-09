################################################################################
#                               Error schemas                                  #
#                                                                              #
# Plain-data description of an error, shared by the CLI and the MCP server    #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from pydantic import BaseModel, ConfigDict, ValidationError
from ..exceptions import (
    AllCandidatesFailedError,
    ErrorCode,
    SkforecastAIError,
    _all_candidates_failed_summary,
)
from .results import _one_line_summary

# Longest message of an error that skforecast-ai did not raise itself; the
# first line of a third-party message is enough to say what failed.
_INTERNAL_MESSAGE_MAX_LENGTH = 200

# Labels pydantic gives to the members of a union that are plain types. The
# other labels are class names or contain brackets or hyphens
# ('list[str]', 'function-after[...]'), unlike the snake_case field names.
_UNION_TYPE_LABELS = frozenset({
    "str", "int", "float", "bool", "bytes", "list", "dict", "tuple", "set",
    "frozenset", "none", "date", "datetime", "time", "timedelta", "decimal",
})


class ErrorInfo(BaseModel):
    """
    Plain-data description of an error, for a reader outside Python.

    Built with `ErrorInfo.from_exception()`. It never holds a traceback or
    generated code: only a stable code, the message, the argument at fault
    and an optional remedy.

    Attributes
    ----------
    code : str
        One of `skforecast_ai.exceptions.ERROR_CODES`. `'internal_error'`
        for an exception that skforecast-ai did not raise itself.
    message : str
        Error message. For an internal error, the exception type and the
        first line of its message, at most 200 characters.
    field : str, None
        Name of the argument (or the field of a plan, profile or CV) at
        fault, when the error is tied to one.
    hint : str, None
        Optional remedy.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ErrorCode
    message: str
    field: str | None = None
    hint: str | None = None

    @classmethod
    def from_exception(cls, exc: Exception) -> ErrorInfo:
        """
        Describe an exception raised by a skforecast-ai call.

        - A `SkforecastAIError` keeps its code, message, field and hint.
          The message of an `AllCandidatesFailedError` leaves out how to
          inspect `exc.failures`, which only exists in Python.
        - A pydantic `ValidationError` (a plan or a profile that does not
          validate) is `'invalid_argument'`. When the validator raised a
          `SkforecastAIError`, its code, message and hint are used. The
          field is the location of the first error, or the field of that
          error when the location is empty (a check on the whole model).
          When there are several errors, the message says how many are
          not shown.
        - Any other exception is `'internal_error'`, described by its type
          and the first line of its message.

        Parameters
        ----------
        exc : Exception
            Exception to describe.

        Returns
        -------
        info : ErrorInfo
            Plain-data description of `exc`.
        """

        if isinstance(exc, ValidationError):
            return cls._from_validation_error(exc)
        if isinstance(exc, AllCandidatesFailedError):
            return cls(
                code    = exc.code,
                message = _all_candidates_failed_summary(exc.failures),
                field   = exc.field,
                hint    = exc.hint,
            )
        if isinstance(exc, SkforecastAIError):
            return cls(
                code    = exc.code,
                message = str(exc),
                field   = exc.field,
                hint    = exc.hint,
            )

        return cls(
            code    = "internal_error",
            message = _one_line_summary(
                          error_type = type(exc).__name__,
                          message    = str(exc),
                          max_length = _INTERNAL_MESSAGE_MAX_LENGTH,
                      ),
        )

    @classmethod
    def _from_validation_error(cls, exc: ValidationError) -> ErrorInfo:
        """
        Describe a pydantic `ValidationError` through its first error.
        """

        errors = exc.errors(include_url=False)
        first = errors[0]
        inner = first.get("ctx", {}).get("error")
        field = _format_location(first["loc"])
        n_described = 1
        if isinstance(inner, SkforecastAIError):
            code = inner.code
            message = str(inner)
            field = field or inner.field
            hint = inner.hint
        else:
            code = "invalid_argument"
            message = str(inner) if isinstance(inner, Exception) else first["msg"]
            hint = None
            branches = _union_branch_errors(errors)
            if len(branches) > 1:
                # One value that matches no member of a union: pydantic adds
                # the member to the location, which is not a field.
                field = _format_location(first["loc"][:-1])
                message = "; ".join(dict.fromkeys(e["msg"] for e in branches))
                n_described = len(branches)
        if len(errors) > n_described:
            message = (
                f"{message} ({len(errors) - n_described} more validation "
                f"error(s) not shown.)"
            )

        return cls(code=code, message=message, field=field, hint=hint)


def _union_branch_errors(errors: list[dict]) -> list[dict]:
    """
    Errors that pydantic reports for the members of one union, starting with
    the first error.

    They share the location of the value plus a last element that labels
    the member (a type, not a field name), and the value itself; each has
    its own error type.
    """

    first = errors[0]
    if len(first["loc"]) < 2 or not _is_union_label(first["loc"][-1]):
        return [first]
    branches = [first]
    for error in errors[1:]:
        if (
            len(error["loc"]) == len(first["loc"])
            and error["loc"][:-1] == first["loc"][:-1]
            and _is_union_label(error["loc"][-1])
            and error.get("input") is first.get("input")
            and error["type"] not in {e["type"] for e in branches}
        ):
            branches.append(error)

    return branches


def _is_union_label(part: str | int) -> bool:
    """
    Whether an element of a pydantic location labels a member of a union
    rather than naming a field or an item.
    """

    return isinstance(part, str) and (
        part in _UNION_TYPE_LABELS
        or not part.isidentifier()
        or part[:1].isupper()
    )


def _format_location(loc: tuple[str | int, ...]) -> str | None:
    """
    Format a pydantic error location as `'a.b[0].c'`, or None when empty.
    """

    parts = []
    for part in loc:
        if isinstance(part, int) and parts:
            parts[-1] = f"{parts[-1]}[{part}]"
        else:
            parts.append(str(part))

    return ".".join(parts) or None
