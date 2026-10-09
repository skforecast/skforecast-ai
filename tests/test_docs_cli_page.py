# Unit test docs/user-guides/cli-usage.md examples

import re
import shlex
from pathlib import Path

import typer

from skforecast_ai.cli import app

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_GUIDE = REPO_ROOT / "docs" / "user-guides" / "cli-usage.md"

_BASH_BLOCK = re.compile(r"^```bash\n(.*?)^```", flags=re.M | re.S)
_BACKTICKED = re.compile(r"`([^`]+)`")


def _cli_calls(text: str) -> list[list[str]]:
    """
    Return the `skforecast-ai` calls of the bash blocks of a Markdown document.

    Continuation lines are joined, comments dropped and pipelines split, so
    each call is the argument list that follows `skforecast-ai`.

    Parameters
    ----------
    text : str
        Full Markdown document.

    Returns
    -------
    calls : list of list of str
        Arguments of each call, in document order.
    """
    calls: list[list[str]] = []
    for block in _BASH_BLOCK.findall(text):
        for line in block.replace("\\\n", " ").splitlines():
            segment: list[str] = []
            for token in shlex.split(line, comments=True) + ["|"]:
                if token != "|":
                    segment.append(token)
                    continue
                if segment and segment[0] == "skforecast-ai":
                    calls.append(segment[1:])
                segment = []

    return calls


def _resolve_command(
    group: object,
    args: list[str],
) -> tuple[list[str], object, list[str]]:
    """
    Walk the command tree along the leading positional arguments of a call.

    Typer ships its own copy of Click, so commands are told apart by their
    attributes rather than by `isinstance` checks against `click`.

    Parameters
    ----------
    group : Group
        Root command of the CLI, as built by `typer.main.get_command`.
    args : list of str
        Arguments that follow `skforecast-ai`.

    Returns
    -------
    path : list of str
        Names of the commands walked, empty for the root.
    command : Command
        Command the call runs.
    remaining : list of str
        Arguments left after the command names.
    """
    path: list[str] = []
    command = group
    remaining = list(args)
    while (
        hasattr(command, "commands")
        and remaining
        and not remaining[0].startswith("-")
    ):
        name = remaining.pop(0)
        if name not in command.commands:
            raise KeyError(" ".join([*path, name]))
        path.append(name)
        command = command.commands[name]

    return path, command, remaining


def _option_names(command: object) -> set[str]:
    """
    Return every spelling of the options a command accepts.

    Parameters
    ----------
    command : Command
        Command to inspect.

    Returns
    -------
    names : set of str
        Long and short names, including the negative form of boolean flags
        and `--help`.
    """
    names = {"--help"}
    for param in command.params:
        if param.param_type_name == "option":
            names.update(param.opts)
            names.update(param.secondary_opts)

    return names


def test_cli_guide_examples_use_existing_commands_and_options():
    """
    Test that every `skforecast-ai` call in the bash blocks of the CLI user
    guide runs an existing command and passes only options that command
    accepts. The guide no longer carries a table of options (the generated
    CLI reference does), so this is what catches an example left behind
    when an option is renamed or removed.
    """
    root = typer.main.get_command(app)
    calls = _cli_calls(CLI_GUIDE.read_text(encoding="utf-8"))

    errors = []
    for args in calls:
        try:
            path, command, remaining = _resolve_command(root, args)
        except KeyError as exc:
            errors.append(f"unknown command '{exc.args[0]}' in {args}")
            continue
        accepted = _option_names(command)
        for token in remaining:
            name = token.split("=", 1)[0]
            if name.startswith("-") and name != "-" and name not in accepted:
                errors.append(
                    f"'{' '.join(path) or 'skforecast-ai'}' has no option "
                    f"'{name}'"
                )

    assert calls
    assert not errors, "\n".join(errors)


def test_cli_guide_has_an_example_for_every_command():
    """
    Test that every top-level command of the CLI appears in at least one
    example of the CLI user guide.
    """
    root = typer.main.get_command(app)
    calls = _cli_calls(CLI_GUIDE.read_text(encoding="utf-8"))
    used = {args[0] for args in calls if args and not args[0].startswith("-")}

    assert sorted(set(root.commands) - used) == []


def test_cli_guide_commands_table_lists_every_command():
    """
    Test that the "Commands" table of the CLI user guide lists exactly the
    top-level commands of the CLI.
    """
    root = typer.main.get_command(app)
    text = CLI_GUIDE.read_text(encoding="utf-8")
    start = text.index("## Commands\n")
    end = text.index("\n## ", start + 1)
    documented = {
        _BACKTICKED.match(line[1:].strip()).group(1)
        for line in text[start:end].splitlines()
        if line.startswith("| `")
    }

    assert documented == set(root.commands)
