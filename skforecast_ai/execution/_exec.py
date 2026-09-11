################################################################################
#                          Rendered code execution                             #
#                                                                              #
# Shared exec() wrapper for the forecasting and backtesting runners            #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import io
import traceback
from contextlib import redirect_stdout
from typing import Any

from ..exceptions import ForecastExecutionError


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
    """

    compiled = compile(code, filename, "exec")

    try:
        with redirect_stdout(io.StringIO()):
            exec(compiled, namespace)  # noqa: S102
    except Exception as e:
        tb = traceback.format_exc()
        raise ForecastExecutionError(
            original_error=e,
            generated_code=code,
            execution_traceback=tb,
        ) from e

    return namespace
