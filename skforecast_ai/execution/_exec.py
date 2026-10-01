################################################################################
#                          Rendered code execution                             #
#                                                                              #
# Shared exec() wrapper for the forecasting and backtesting runners            #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import ast
import io
import re
import textwrap
import traceback
from contextlib import redirect_stdout
from typing import Any

from ..exceptions import ForecastExecutionError

# Line breaks as the Python tokenizer counts them.
_LINE_BREAK = re.compile(r"\r\n|\r|\n")

# Statements whose failing line is reported alone: their clauses (`except`,
# `case`) are not statements, so the innermost statement is the whole block.
_LINE_ONLY_STATEMENTS = tuple(
    getattr(ast, name) for name in ("Try", "TryStar", "Match") if hasattr(ast, name)
)


def exec_rendered(
    code: str,
    namespace: dict[str, Any],
    filename: str,
) -> dict[str, Any]:
    """
    Execute rendered script code inside a pre-populated namespace.

    Compiles and runs `code` with `namespace` as its globals, so any
    variables injected by the caller (for example `data`) are visible to
    the script and every variable the script defines is returned. Output
    printed by the script is discarded rather than shown.

    Parameters
    ----------
    code : str
        Python source to execute, typically `RenderedScript.executable`.
    namespace : dict
        Globals for the execution. Mutated in place and returned.
    filename : str
        Name reported in tracebacks for the compiled code, for example
        `'<forecast>'` or `'<backtesting>'`.

    Returns
    -------
    namespace : dict
        The same dictionary, now holding every variable the code defined.

    Raises
    ------
    ForecastExecutionError
        When the code does not compile or raises while running. It locates
        the line and the statement of `code` that failed.
    """

    # The tree is parsed once and kept to locate the failed statement, so
    # a warning raised while parsing is not emitted a second time.
    tree = None
    try:
        tree = ast.parse(code, filename)
        compiled = compile(tree, filename, "exec")
        with redirect_stdout(io.StringIO()):
            exec(compiled, namespace)  # noqa: S102
    except Exception as e:
        tb = traceback.format_exc()
        failed_line = _find_failed_line(e, filename)
        raise ForecastExecutionError(
            original_error      = e,
            generated_code      = code,
            execution_traceback = tb,
            failed_line         = failed_line,
            failed_statement    = _find_failed_statement(code, failed_line, tree),
        ) from e

    return namespace


def _find_failed_line(error: Exception, filename: str) -> int | None:
    """
    Locate the line of the executed code where `error` was raised.

    Parameters
    ----------
    error : Exception
        Exception raised while compiling or executing the code.
    filename : str
        Name the code was compiled with, which identifies its frames.

    Returns
    -------
    failed_line : int, None
        1-based line of the code: the last frame of the code in the
        traceback (the statement that called into the library where the
        error was raised), or, when the code did not run, the line of its
        `SyntaxError`. None when neither is found.
    """

    failed_line = None
    for frame, lineno in traceback.walk_tb(error.__traceback__):
        if frame.f_code.co_filename == filename:
            failed_line = lineno
    if failed_line is None and isinstance(error, SyntaxError):
        if error.filename == filename:
            failed_line = error.lineno

    return failed_line


def _find_failed_statement(
    code: str,
    failed_line: int | None,
    tree: ast.Module | None,
) -> str | None:
    """
    Return the source of the innermost statement of `code` holding a line.

    Parameters
    ----------
    code : str
        Executed code.
    failed_line : int, None
        1-based line where the error was raised.
    tree : ast.Module, None
        Parsed code. None when the code does not parse.

    Returns
    -------
    failed_statement : str, None
        Source of the smallest statement spanning `failed_line`, all its
        lines included. For a compound statement (`for`, `if`, `with`), only
        its header, where the error was raised. Only the line itself when
        the code does not parse, when several statements share the line, or
        for a `try` or `match` statement. None when `failed_line` is None or
        outside the code.
    """

    # The lines as Python numbers them: `str.splitlines` would also split
    # on form feeds and other characters the tokenizer does not count.
    lines = _LINE_BREAK.split(code)
    if failed_line is None or not 1 <= failed_line <= len(lines):
        return None
    line = lines[failed_line - 1].strip()
    if tree is None:
        return line

    statements = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.stmt)
        and node.lineno <= failed_line <= node.end_lineno
    ]
    if not statements:
        return line
    span = min(node.end_lineno - node.lineno for node in statements)
    innermost = [
        node for node in statements if node.end_lineno - node.lineno == span
    ]
    # Several statements on the line, or one whose failing line is a clause
    # (`except`, `case`) rather than a header: the line says more.
    if len(innermost) > 1 or isinstance(innermost[0], _LINE_ONLY_STATEMENTS):
        return line
    statement = innermost[0]
    body = getattr(statement, "body", None)
    if isinstance(body, list) and body:
        # No statement of the body spans the line, so it is in the header;
        # comments and blank lines before the body are not part of it.
        header = lines[statement.lineno - 1 : body[0].lineno - 1]
        while header and (
            not header[-1].strip() or header[-1].strip().startswith("#")
        ):
            header = header[:-1]
        if header:
            return textwrap.dedent("\n".join(header)).strip()

    return ast.get_source_segment(code, statement)
