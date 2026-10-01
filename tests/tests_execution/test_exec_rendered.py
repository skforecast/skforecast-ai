# Unit test exec_rendered execution/_exec

import json
import re
import warnings

import pytest

from skforecast_ai.exceptions import ForecastExecutionError
from skforecast_ai.execution._exec import (
    _find_failed_line,
    _find_failed_statement,
    exec_rendered,
)


def test_exec_rendered_ForecastExecutionError_when_code_does_not_compile():
    """
    Test that code that does not compile raises ForecastExecutionError,
    wrapping the SyntaxError instead of letting it escape, with the line and
    the text of the line that does not compile.
    """
    code = "a = 1\nb = (\nc = 3\n"

    with pytest.raises(
        ForecastExecutionError, match=re.escape("SyntaxError")
    ) as exc_info:
        exec_rendered(code, {}, "<forecast>")

    error = exc_info.value
    assert isinstance(error.original_error, SyntaxError)
    assert error.generated_code == code
    assert error.failed_line == 2
    assert error.failed_statement == "b = ("


@pytest.mark.parametrize(
    "code, error_type, failed_line, failed_statement",
    [
        (
            "a = 1\nb = undefined_name\nc = 3\n",
            NameError,
            2,
            "b = undefined_name",
        ),
        (
            "x = dict(\n    a = 1,\n    b = 1 / 0,\n)\ny = 2\n",
            ZeroDivisionError,
            3,
            "x = dict(\n    a = 1,\n    b = 1 / 0,\n)",
        ),
        (
            "import json\nvalues = [1, 2]\nfor value in values:\n"
            "    parsed = json.loads('{')\n",
            json.JSONDecodeError,
            4,
            "parsed = json.loads('{')",
        ),
        (
            "values = {k: 1 / k for k in [1, 0]}\n",
            ZeroDivisionError,
            1,
            "values = {k: 1 / k for k in [1, 0]}",
        ),
        (
            "values = {'a': 1}\nfor key in values['b']:\n    print(key)\n",
            KeyError,
            2,
            "for key in values['b']:",
        ),
        (
            "x = 1\ncompile('y = (', '<other>', 'exec')\n",
            SyntaxError,
            2,
            "compile('y = (', '<other>', 'exec')",
        ),
        (
            "# a\x0cb\nx = 1\ny = 1 / 0\n",
            ZeroDivisionError,
            3,
            "y = 1 / 0",
        ),
        (
            "x = 1\nif x: y = 1 / 0\n",
            ZeroDivisionError,
            2,
            "if x: y = 1 / 0",
        ),
        (
            "a = 1; b = 1 / 0\n",
            ZeroDivisionError,
            1,
            "a = 1; b = 1 / 0",
        ),
        (
            "for x in [1 / 0]:\n    # comment\n    pass\n",
            ZeroDivisionError,
            1,
            "for x in [1 / 0]:",
        ),
        (
            "try:\n    1 / 0\nexcept (ValueError, undefined_name):\n    pass\n",
            NameError,
            3,
            "except (ValueError, undefined_name):",
        ),
        (
            "x = 1\ncompile('(', '<forecast>', 'exec')\n",
            SyntaxError,
            2,
            "compile('(', '<forecast>', 'exec')",
        ),
    ],
    ids=[
        "statement on one line",
        "statement on several lines",
        "error inside a library, in a loop",
        "error inside a comprehension",
        "error in the header of a compound statement",
        "syntax error of code compiled by the code",
        "form feed inside a comment",
        "compound statement on one line",
        "several statements on one line",
        "comment between header and body",
        "except clause",
        "syntax error of code compiled with the same name",
    ],
)
def test_exec_rendered_ForecastExecutionError_when_code_fails_while_running(
    code, error_type, failed_line, failed_statement
):
    """
    Test that an error raised while running the code is wrapped in a
    ForecastExecutionError that holds the line of the code where it was
    raised (the last frame of the code, also when the error comes from a
    library or from code it compiles itself) and the whole innermost
    statement holding that line, the header of a compound statement, or
    the line alone when it holds several statements or an `except` clause.
    Lines are numbered as Python numbers them.
    """
    with pytest.raises(
        ForecastExecutionError, match=re.escape(error_type.__name__)
    ) as exc_info:
        exec_rendered(code, {}, "<forecast>")

    error = exc_info.value
    assert isinstance(error.original_error, error_type)
    assert error.failed_line == failed_line
    assert error.failed_statement == failed_statement


def test_exec_rendered_output_when_code_runs(capsys):
    """
    Test that the namespace is returned holding the injected variables and
    the variables the code defined, and that printed output is discarded.
    """
    namespace = exec_rendered("b = a + 1\nprint(b)\n", {"a": 1}, "<forecast>")

    assert namespace["a"] == 1
    assert namespace["b"] == 2
    assert capsys.readouterr().out == ""


def test_exec_rendered_location_is_none_when_not_found():
    """
    Test that the location helpers give None when the error has no frame in
    the code, and that no statement is looked up without a line.
    """
    assert _find_failed_line(ValueError("not raised"), "<forecast>") is None
    assert _find_failed_statement("x = 1\n", None, None) is None
    assert _find_failed_statement("x = 1\n", 7, None) is None


def test_exec_rendered_parse_warning_emitted_once():
    """
    Test that a warning raised while parsing the code (an invalid escape
    sequence: a DeprecationWarning up to Python 3.11, a SyntaxWarning from
    3.12) is emitted once, with the name the code was compiled with, even
    when the code then fails and its statement is located.
    """
    code = "x = '\\d'\ny = 1 / 0\n"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(ForecastExecutionError, match=re.escape("ZeroDivisionError")):
            exec_rendered(code, {}, "<forecast>")

    escape_warnings = [
        w for w in caught if "invalid escape sequence" in str(w.message)
    ]
    assert len(escape_warnings) == 1
    assert escape_warnings[0].filename == "<forecast>"
