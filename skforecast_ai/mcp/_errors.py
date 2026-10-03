################################################################################
#                              MCP server errors                               #
#                                                                              #
# Every failure of a tool reaches the agent as a ToolError with a JSON object  #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import json
import logging
import secrets
from typing import Any, Literal, get_args
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError
from ..exceptions import (
    ERROR_CODES,
    AllCandidatesFailedError,
    ForecastExecutionError,
    SkforecastAIError,
)
from ..schemas.errors import ErrorInfo, _format_location, _is_union_label

ServerErrorCode = Literal[
    "unknown_id",
    "inconsistent_ids",
    "invalid_path",
    "path_not_allowed",
    "url_not_allowed",
    "data_changed",
    "model_not_allowed",
]
"""Codes of the errors that only the server raises."""

SERVER_ERROR_CODES: tuple[str, ...] = get_args(ServerErrorCode)

logger = logging.getLogger("skforecast_ai.mcp")

# Longest message and hint sent to the agent. The messages of the core are
# forwarded as they are (they name at most 5 values of the data); this only
# bounds what one error can add to the context of the agent.
MAX_MESSAGE_CHARS = 4_000
MAX_HINT_CHARS = 1_000
# Texts of `details` (an id or a path given by the agent) are cut as well.
MAX_DETAIL_CHARS = 500

# The core names the argument of its Python API; the tools take ids and
# paths in their place.
FIELD_RENAMES = {
    "data": "data_path",
    "profile": "profile_id",
    "plan": "plan_id",
    "cv": "cv_id",
    "exog": "exog_path",
}


class ServerError(Exception):
    """
    Error raised by the server itself, outside the core.

    It never leaves a tool: every tool turns it into the JSON of its error.
    Its codes are not those of `SkforecastAIError`, which form a closed set
    of the core.

    Parameters
    ----------
    message : str
        Error message.
    code : str
        One of `SERVER_ERROR_CODES`, or a code of the core
        (`skforecast_ai.exceptions.ERROR_CODES`) when the server checks
        something the core also checks (`'invalid_argument'`,
        `'data_not_found'`).
    field : str, default None
        Argument of the tool at fault.
    hint : str, default None
        Optional remedy.
    details : dict, default None
        Plain data about the error (the id or the path at fault).

    Attributes
    ----------
    code : str
        Code of the error.
    field : str, None
        Argument of the tool at fault.
    hint : str, None
        Optional remedy.
    details : dict, None
        Plain data about the error.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        field: str | None = None,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if code not in SERVER_ERROR_CODES and code not in ERROR_CODES:
            raise ValueError(f"Unknown error code {code!r}.")
        super().__init__(message)
        self.code = code
        self.field = field
        self.hint = hint
        self.details = details


# Attribute an exception of the core gets when the server adds details to
# its error (the id of the failure that keeps its traceback).
_DETAILS_ATTRIBUTE = "_skforecast_ai_mcp_details"


def attach_details(exc: Exception, details: dict[str, Any]) -> None:
    """
    Add details to the error an exception of the core is reported as.

    Parameters
    ----------
    exc : Exception
        Exception raised by the core.
    details : dict
        Plain data to send in `details`.

    Returns
    -------
    None
    """

    setattr(exc, _DETAILS_ATTRIBUTE, details)


def failure_text(exc: Exception) -> str | None:
    """
    Describe in full a failed run of a generated script: what failed, where,
    the traceback and the code that ran. Never sent in a response; the
    `get_failure` tool returns it on request.

    Parameters
    ----------
    exc : Exception
        Exception raised by the core.

    Returns
    -------
    text : str, None
        The description, or None when the exception is not the failure of a
        script (`ForecastExecutionError`) or of every candidate of a
        comparison (`AllCandidatesFailedError`).
    """

    if isinstance(exc, ForecastExecutionError):
        parts = [str(exc)]
        if exc.failed_line is not None:
            parts.append(f"Failed line of the code that ran: {exc.failed_line}")
        if exc.failed_statement is not None:
            parts.append(f"Failed statement:\n{exc.failed_statement}")
        parts.append(f"Traceback:\n{exc.execution_traceback}")
        parts.append(f"Code that ran:\n{exc.generated_code}")
        return "\n\n".join(parts)
    if isinstance(exc, AllCandidatesFailedError):
        return "\n\n".join(
            candidate_failure_text(name, failure)
            for name, failure in exc.failures.items()
        )

    return None


def candidate_failure_text(name: str, failure: Any) -> str:
    """
    Describe in full the failure of one candidate of a comparison.

    Parameters
    ----------
    name : str
        Name of the candidate.
    failure : CandidateFailure
        Its failure.

    Returns
    -------
    text : str
        Error, traceback and code that ran.
    """

    parts = [
        f"Candidate {name!r} failed: {failure.error_type}: {failure.message}",
        f"Traceback:\n{failure.traceback}",
    ]
    if failure.generated_code is not None:
        parts.append(f"Code that ran:\n{failure.generated_code}")

    return "\n\n".join(parts)


def _cut(text: str | None, max_chars: int) -> str | None:
    """
    Cut a text to `max_chars` characters, saying how many were left out.
    """

    if text is None or len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]} ... ({omitted} more characters)"


def error_payload(exc: Exception) -> dict[str, Any]:
    """
    Describe an exception as the JSON object the tools send.

    Parameters
    ----------
    exc : Exception
        Exception raised while a tool ran: a `ServerError`, an error of the
        core, a pydantic `ValidationError` or any other exception (an
        `'internal_error'`, described as `ErrorInfo` does; `tool_error`
        sends `internal_error_payload` instead).

    Returns
    -------
    payload : dict
        Keys `code`, `message`, `field`, `hint` and `details`.
    """

    if isinstance(exc, ServerError):
        code, message, field, hint = exc.code, str(exc), exc.field, exc.hint
        details = None
        if exc.details is not None:
            details = {
                key: _cut(value, MAX_DETAIL_CHARS) if isinstance(value, str) else value
                for key, value in exc.details.items()
            }
    else:
        info = ErrorInfo.from_exception(exc)
        code, message, field, hint = info.code, info.message, info.field, info.hint
        details = getattr(exc, _DETAILS_ATTRIBUTE, None)
        if field is not None:
            head, _, rest = field.partition(".")
            if head in FIELD_RENAMES:
                field = FIELD_RENAMES[head] + (f".{rest}" if rest else "")

    return {
        "code": code,
        "message": _cut(message, MAX_MESSAGE_CHARS),
        "field": field,
        "hint": _cut(hint, MAX_HINT_CHARS),
        "details": details,
    }


def argument_error_payload(exc: ValidationError) -> dict[str, Any]:
    """
    Describe the arguments of a tool call that do not match its schema.

    Like `error_payload`, with the field written as the path of the argument
    (`'overrides.steps'`, `'lags[0]'`) without the members of a union that
    pydantic adds to the location (`'lags.int'`).

    Parameters
    ----------
    exc : ValidationError
        Error of the argument model of the tool.

    Returns
    -------
    payload : dict
        Keys `code`, `message`, `field`, `hint` and `details`.
    """

    payload = error_payload(exc)
    location = exc.errors(include_url=False)[0]["loc"]
    # The first part is always the name of an argument, even one named like a
    # type ('date').
    payload["field"] = _format_location(
        location[:1] + tuple(part for part in location[1:] if not _is_union_label(part))
    )

    return payload


def tool_error(exc: Exception) -> ToolError:
    """
    Build the `ToolError` that reports an exception to the agent.

    The SDK of MCP sends the text of a `ToolError` to the agent (prefixed
    with "Error executing tool <name>: ") and hides the text of any other
    exception, so every failure of a tool goes through here.

    Parameters
    ----------
    exc : Exception
        Exception raised while the tool ran.

    Returns
    -------
    error : ToolError
        Error whose text is the JSON of `error_payload(exc)`, or of
        `internal_error_payload(exc)` for an exception that neither the
        server nor skforecast-ai raised. ASCII only, so no line break or
        separator of the data reaches the agent unescaped.
    """

    # Classified by type, not by code: a `SkforecastAIError` with the code
    # 'internal_error' was raised by skforecast-ai and keeps its message.
    if isinstance(exc, (ServerError, SkforecastAIError, ValidationError)):
        payload = error_payload(exc)
    else:
        payload = internal_error_payload(exc)

    return ToolError(json.dumps(payload, ensure_ascii=True))


def internal_error_payload(exc: Exception) -> dict[str, Any]:
    """
    Describe an unexpected exception to the agent by its type and an id
    only, and write its message and traceback to the log of the server.

    The message of an exception that skforecast-ai did not raise can quote
    a value of the data (pandas: "could not convert string to float:
    '...'"), so it never reaches the agent; the user finds it in the log
    (stderr) by the id.

    Parameters
    ----------
    exc : Exception
        Exception that neither the server nor skforecast-ai raised.

    Returns
    -------
    payload : dict
        Keys `code` (`'internal_error'`), `message`, `field` (None), `hint`
        and `details` (`error_id` and `error_type`).
    """

    error_id = f"error-{secrets.token_hex(6)}"
    error_type = type(exc).__name__
    logger.error(
        "internal_error %s: %s: %s", error_id, error_type, exc, exc_info=exc
    )

    return {
        "code": "internal_error",
        "message": (
            f"Unexpected {error_type}. Its message and traceback are in the "
            f"log of the server (stderr) under the id {error_id}."
        ),
        "field": None,
        "hint": (
            "Report it to the user with the id; do not retry with the same "
            "inputs."
        ),
        "details": {"error_id": error_id, "error_type": error_type},
    }
