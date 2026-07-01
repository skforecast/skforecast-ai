"""Typer CLI for skforecast-ai"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from pydantic import ValidationError

from . import __version__
from ._display import (
    render_code,
    render_cv_config,
    render_dataframe,
    render_explanation,
    render_metrics,
    render_plan,
    render_profile,
)
from .assistant import ForecastingAssistant
from .config import (
    CONFIG_FILE,
    get_config_value,
    load_config,
    set_config_value,
)
from .exceptions import ForecastExecutionError, LLMRequiredError
from .schemas.plans import ForecastPlan
from .schemas.profiles import ForecastingProfile


def _version_callback(value: bool) -> None:
    """
    Print version and exit.

    Parameters
    ----------
    value : bool
        Whether the --version flag was passed.

    Returns
    -------
    None
    """
    if value:
        print(f"skforecast-ai {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="skforecast-ai",
    help="Deterministic forecasting assistant powered by skforecast.",
    no_args_is_help=True,
)


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """
    Deterministic forecasting assistant powered by skforecast.

    Parameters
    ----------
    version : bool, default None
        Show version and exit.

    Returns
    -------
    None
    """


console = Console()


# ---------------------------------------------------------------------------
# Config subcommand
# ---------------------------------------------------------------------------

config_app = typer.Typer(help="Manage persistent configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """
    Display current configuration.

    Returns
    -------
    None
    """
    config = load_config()
    if not config:
        console.print("[dim]No config file found. Using defaults and environment variables.[/dim]")
        console.print(f"[dim]Config path: {CONFIG_FILE}[/dim]")
        return

    table = Table(title="Configuration", show_lines=True)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    for section, values in sorted(config.items()):
        if not isinstance(values, dict):
            continue
        for key, val in sorted(values.items()):
            full_key = f"{section}.{key}"
            display_val = _mask_secret(full_key, str(val))
            table.add_row(full_key, display_val, str(CONFIG_FILE))

    console.print(table)


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key (e.g. 'llm.provider').")],
    value: Annotated[str, typer.Argument(help="Value to set.")],
) -> None:
    """
    Set a configuration value.

    Parameters
    ----------
    key : str
        Config key in dotted notation (e.g. `'llm.provider'`).
    value : str
        Value to set.

    Returns
    -------
    None
    """
    try:
        set_config_value(key, value)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
    display_val = _mask_secret(key, value)
    console.print(f"[green]Set[/green] {key} = {display_val}")


@config_app.command("path")
def config_path() -> None:
    """
    Print the config file location.

    Returns
    -------
    None
    """
    print(str(CONFIG_FILE))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET_KEYS = {"llm.api_key"}


def _mask_secret(key: str, value: str) -> str:
    """Mask sensitive config values for display, showing only last 4 chars."""
    if key in _SECRET_KEYS and len(value) > 4:
        return "***" + value[-4:]
    return value


def _resolve(flag: str | None, env_var: str, config_key: str) -> str | None:
    """
    Resolve a setting with precedence: CLI flag > env var > config file > None.

    Parameters
    ----------
    flag : str, None
        Value from the CLI flag.
    env_var : str
        Name of the environment variable to check.
    config_key : str
        Dotted key to look up in the config file.

    Returns
    -------
    value : str, None
        Resolved value or None if not found.
    """
    if flag is not None:
        return flag
    env_val = os.environ.get(env_var)
    if env_val is not None:
        return env_val
    return get_config_value(config_key)


def _resolve_bool(
    flag: bool | None, env_var: str, config_key: str, default: bool = False
) -> bool:
    """
    Resolve a boolean setting: CLI flag > env var > config file > default.

    Parameters
    ----------
    flag : bool, None
        Value from the CLI flag.
    env_var : str
        Name of the environment variable to check.
    config_key : str
        Dotted key to look up in the config file.
    default : bool, default False
        Fallback value if not found anywhere.

    Returns
    -------
    value : bool
        Resolved boolean value.
    """
    if flag is not None:
        return flag
    env_val = os.environ.get(env_var)
    if env_val is not None:
        return env_val.lower() in ("true", "1", "yes")
    config_val = get_config_value(config_key)
    if config_val is not None:
        return config_val.lower() in ("true", "1", "yes")
    return default


def _read_json_input(source: str) -> dict:
    """
    Read JSON from a file path or stdin (when source is `'-'`).

    Parameters
    ----------
    source : str
        Path to a JSON file, or `'-'` to read from stdin.

    Returns
    -------
    data : dict
        Parsed JSON content.
    """
    if source == "-":
        raw = sys.stdin.read()
    else:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: '{source}'.")
        raw = path.read_text()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON input: {e}") from e


def _parse_target(target_str: str) -> str | list[str]:
    """
    Split comma-separated target names; return str if single value.

    Parameters
    ----------
    target_str : str
        Comma-separated target column names.

    Returns
    -------
    target : str, list
        Single target name or list of target names.
    """
    parts = [t.strip() for t in target_str.split(",") if t.strip()]
    if not parts:
        raise typer.BadParameter("Target must not be empty.")
    return parts if len(parts) > 1 else parts[0]


def _parse_interval(interval_str: str | None) -> list[float] | None:
    """
    Parse `'lower,upper'` interval string into a two-element list or None.

    Parameters
    ----------
    interval_str : str, None
        Comma-separated lower and upper quantiles (e.g. `'0.1,0.9'`).

    Returns
    -------
    interval : list, None
        Two-element list `[lower, upper]` or None if input is None.
    """
    if interval_str is None:
        return None
    parts = [float(x.strip()) for x in interval_str.split(",")]
    if len(parts) != 2:
        raise typer.BadParameter(
            "Interval must be two comma-separated quantiles, e.g. '0.1,0.9'."
        )
    return parts


def _parse_estimator_kwargs(value: str | None) -> dict | None:
    """
    Parse JSON string into dict for estimator hyperparameters.

    Parameters
    ----------
    value : str, None
        JSON string representing estimator keyword arguments.

    Returns
    -------
    kwargs : dict, None
        Parsed dictionary or None if input is None.
    """
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(
            f"Invalid JSON in --estimator-kwargs: {e}"
        ) from e
    if not isinstance(parsed, dict):
        raise typer.BadParameter(
            "--estimator-kwargs must be a JSON object, "
            "e.g. '{\"n_estimators\": 200}'."
        )
    return parsed


def _load_exog_future(
    path: Path | None,
    date_column: str | None,
    frequency: str | None = None,
) -> pd.DataFrame | None:
    """
    Load a future exogenous CSV and set its datetime index.

    Mirrors the index setup applied to the main dataset: when a date
    column is provided it is parsed to datetime and set as the index;
    otherwise the first column is parsed as the index. The frequency is
    applied with `asfreq` when known and the index is sorted, so the
    returned DataFrame carries a DatetimeIndex covering the forecast
    horizon as required by skforecast.

    Parameters
    ----------
    path : Path, None
        Path to the future exogenous CSV file. If None, returns None.
    date_column : str, None
        Name of the column containing timestamps. If None, the first
        column is parsed as the datetime index.
    frequency : str, default None
        Pandas frequency string to apply with `asfreq`. If None, no
        frequency is enforced.

    Returns
    -------
    exog_future : pandas DataFrame, None
        Future exogenous variables indexed by a DatetimeIndex, or None
        when `path` is None.
    """
    if path is None:
        return None
    if not path.is_file():
        raise FileNotFoundError(f"Exog future CSV not found: '{path}'.")

    if date_column is not None:
        exog = pd.read_csv(path)
        exog[date_column] = pd.to_datetime(exog[date_column])
        exog = exog.set_index(date_column)
    else:
        exog = pd.read_csv(path, index_col=0, parse_dates=True)

    if frequency:
        exog = exog.asfreq(frequency)

    return exog.sort_index()


def _write_output(content: str, output: Path | None) -> None:
    """
    Write content to file or stdout.

    Parameters
    ----------
    content : str
        Text content to write.
    output : Path, None
        File path to write to. If None, prints to stdout.

    Returns
    -------
    None
    """
    if output is not None:
        output.write_text(content)
        console.print(f"[green]Output written to:[/green] {output}")
    else:
        print(content)


@contextlib.contextmanager
def _spinner(message: str, quiet: bool):
    """Wrap a block with a Rich spinner unless quiet mode is active."""
    if quiet:
        yield
    else:
        with console.status(message):
            yield


@contextlib.contextmanager
def _error_handler():
    """
    Catch known exceptions and print user-friendly errors.
    """
    try:
        yield
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
    except LLMRequiredError:
        console.print(
            "[red]Error:[/red] No LLM configured. "
            "Set the SKFORECAST_AI_LLM environment variable or use the --llm flag."
        )
        raise typer.Exit(code=1)
    except ForecastExecutionError as e:
        console.print(f"[red]Execution Error:[/red] {e}")
        console.print(
            "[dim]Tip: use --output-code to save the generated script for debugging.[/dim]"
        )
        raise typer.Exit(code=1)
    except ValidationError as e:
        n = e.error_count()
        details = "; ".join(
            f"{err['loc'][0]}: {err['msg']}" if err.get("loc") else err["msg"]
            for err in e.errors()[:3]
        )
        console.print(
            f"[red]Error:[/red] Invalid input data — {n} validation error(s): {details}"
        )
        console.print(
            "[dim]Tip: use --format json with the source command to produce valid input.[/dim]"
        )
        raise typer.Exit(code=1)
    except (ValueError, KeyError, TypeError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


def _render_profile_table(profile) -> None:
    """
    Print a Rich table summarizing the ForecastingProfile.

    Parameters
    ----------
    profile : ForecastingProfile
        Profile object to render.

    Returns
    -------
    None
    """
    console.print(render_profile(profile))


def _render_plan_panel(plan) -> None:
    """
    Print a Rich panel summarizing the ForecastPlan.

    Parameters
    ----------
    plan : ForecastPlan
        Plan object to render.

    Returns
    -------
    None
    """
    console.print(render_plan(plan))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def profile(
    data: Annotated[str, typer.Argument(help="Path or URL to CSV file.")],
    target: Annotated[str, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")],
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id_column: Annotated[str | None, typer.Option("--series-id-column", "-s", help="Series identifier column.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: table or json.")] = "table",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write output to file.")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Profile a dataset and recommend a forecaster + estimator."""
    with _error_handler():
        assistant = ForecastingAssistant()
        parsed_target = _parse_target(target)

        with _spinner("Profiling dataset...", quiet):
            result = assistant.profile(
                data=data, target=parsed_target, date_column=date_column,
                series_id_column=series_id_column,
            )

        if format == "json":
            json_str = result.model_dump_json(indent=2)
            _write_output(json_str, output)
        else:
            _render_profile_table(result)


def _parse_lags(lags_str: str | None) -> int | list[int] | None:
    """
    Parse lags string into an int or list of ints.

    Parameters
    ----------
    lags_str : str, None
        Comma-separated lag indices (e.g. '1,2,3') or a single int.

    Returns
    -------
    lags : int, list of int, None
        Parsed lags or None.
    """
    if lags_str is None:
        return None
    try:
        if "," in lags_str:
            lags: int | list[int] = [int(x.strip()) for x in lags_str.split(",")]
        else:
            lags = int(lags_str)
    except ValueError as e:
        raise typer.BadParameter(f"Invalid format for --lags: {e}") from e

    values = lags if isinstance(lags, list) else [lags]
    if any(v < 1 for v in values):
        raise typer.BadParameter("--lags must be positive integers (>= 1).")
    return lags


def _parse_window_features(wf_str: str | None) -> list[dict] | None:
    """
    Parse window features JSON string.

    Parameters
    ----------
    wf_str : str, None
        JSON string representing a list of dicts.

    Returns
    -------
    window_features : list of dict, None
        Parsed list of dicts or None.
    """
    if wf_str is None:
        return None
    try:
        parsed = json.loads(wf_str)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"Invalid JSON in --window-features: {e}") from e
    if not isinstance(parsed, list) or not all(isinstance(x, dict) for x in parsed):
        raise typer.BadParameter(
            "--window-features must be a JSON array of objects, "
            "e.g. '[{\"stats\": [\"mean\"], \"window_sizes\": 7}]'."
        )
    return parsed


@app.command()
def plan(
    data: Annotated[str | None, typer.Argument(help="Path or URL to CSV file.")] = None,
    target: Annotated[str | None, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")] = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Forecast horizon (number of steps).")] = None,
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id_column: Annotated[str | None, typer.Option("--series-id-column", "-s", help="Series identifier column.")] = None,
    forecaster: Annotated[str | None, typer.Option("--forecaster", help="Override forecaster class.")] = None,
    estimator: Annotated[str | None, typer.Option("--estimator", help="Override estimator class.")] = None,
    estimator_kwargs: Annotated[str | None, typer.Option("--estimator-kwargs", help="Estimator hyperparameters as JSON string, e.g. '{\"n_estimators\": 200}'.")] = None,
    interval: Annotated[str | None, typer.Option("--interval", help="Prediction interval, e.g. '0.1,0.9'.")] = None,
    lags: Annotated[str | None, typer.Option("--lags", help="Explicit lags as an int or comma-separated list, e.g. '1,2,3'.")] = None,
    window_features: Annotated[str | None, typer.Option("--window-features", help="Explicit window features as JSON array, e.g. '[{\"stats\": [\"mean\"], \"window_sizes\": 7}]'.")] = None,
    from_profile: Annotated[str | None, typer.Option("--from-profile", help="Load profile from JSON file or '-' for stdin.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: table or json.")] = "table",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write output to file.")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Generate a detailed forecasting plan from a dataset."""
    with _error_handler():
        if steps is None:
            console.print("[red]Error:[/red] --steps is required.")
            raise typer.Exit(code=1)

        assistant = ForecastingAssistant()
        parsed_interval = _parse_interval(interval)
        parsed_estimator_kwargs = _parse_estimator_kwargs(estimator_kwargs)
        parsed_lags = _parse_lags(lags)
        parsed_window_features = _parse_window_features(window_features)

        if from_profile is not None:
            profile_data = _read_json_input(from_profile)
            prof = ForecastingProfile.model_validate(profile_data)
        else:
            if data is None or target is None:
                console.print(
                    "[red]Error:[/red] DATA and --target are required "
                    "unless --from-profile is provided."
                )
                raise typer.Exit(code=1)
            parsed_target = _parse_target(target)
            with _spinner("Profiling...", quiet):
                prof = assistant.profile(
                    data=data, target=parsed_target, date_column=date_column,
                    series_id_column=series_id_column,
                )

        with _spinner("Planning...", quiet):
            result = assistant.plan(
                profile=prof, steps=steps, forecaster=forecaster,
                estimator=estimator, estimator_kwargs=parsed_estimator_kwargs,
                interval=parsed_interval, lags=parsed_lags,
                window_features=parsed_window_features,
            )

        if format == "json":
            bundle = {
                "profile": prof.model_dump(mode="json"),
                "plan": result.model_dump(mode="json"),
            }
            json_str = json.dumps(bundle, indent=2)
            _write_output(json_str, output)
        else:
            _render_plan_panel(result)


@app.command(name="refine-plan")
def refine_plan(
    from_plan: Annotated[str, typer.Option("--from-plan", help="Load plan bundle from JSON file or '-' for stdin.")],
    forecaster: Annotated[str | None, typer.Option("--forecaster", help="Override forecaster class.")] = None,
    estimator: Annotated[str | None, typer.Option("--estimator", help="Override estimator class.")] = None,
    estimator_kwargs: Annotated[str | None, typer.Option("--estimator-kwargs", help="Estimator hyperparameters as JSON string, e.g. '{\"n_estimators\": 200}'.")] = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Override forecast horizon.")] = None,
    interval: Annotated[str | None, typer.Option("--interval", help="Override prediction interval, e.g. '0.1,0.9'.")] = None,
    lags: Annotated[str | None, typer.Option("--lags", help="Explicit lags as an int or comma-separated list, e.g. '1,2,3'.")] = None,
    window_features: Annotated[str | None, typer.Option("--window-features", help="Explicit window features as JSON array, e.g. '[{\"stats\": [\"mean\"], \"window_sizes\": 7}]'.")] = None,
    prompt: Annotated[str | None, typer.Option("--prompt", help="Natural language domain knowledge to guide LLM plan refinement.")] = None,
    llm: Annotated[str | None, typer.Option("--llm", help="LLM provider for plan refinement.")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Custom LLM endpoint URL.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key for the LLM provider.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: table or json.")] = "table",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write output to file.")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Refine an existing forecasting plan by overriding specific fields or using LLM guidance."""
    with _error_handler():
        bundle_data = _read_json_input(from_plan)
        prof = ForecastingProfile.model_validate(bundle_data.get("profile", {}))
        plan_obj = ForecastPlan.model_validate(bundle_data.get("plan", {}))

        parsed_interval = _parse_interval(interval)
        parsed_estimator_kwargs = _parse_estimator_kwargs(estimator_kwargs)
        parsed_lags = _parse_lags(lags)
        parsed_window_features = _parse_window_features(window_features)

        llm_value = _resolve(llm, "SKFORECAST_AI_LLM", "llm.provider")
        base_url_value = _resolve(base_url, "SKFORECAST_AI_BASE_URL", "llm.base_url")
        api_key_value = _resolve(api_key, "SKFORECAST_AI_API_KEY", "llm.api_key")

        assistant = ForecastingAssistant(
            llm=llm_value,
            base_url=base_url_value,
            api_key=api_key_value,
        )

        overrides: dict = {}
        if forecaster is not None:
            overrides["forecaster"] = forecaster
        if estimator is not None:
            overrides["estimator"] = estimator
        if parsed_estimator_kwargs is not None:
            overrides["estimator_kwargs"] = parsed_estimator_kwargs
        if steps is not None:
            overrides["steps"] = steps
        if parsed_interval is not None:
            overrides["interval"] = parsed_interval
        if parsed_lags is not None:
            overrides["lags"] = parsed_lags
        if parsed_window_features is not None:
            overrides["window_features"] = parsed_window_features

        with _spinner("Refining plan...", quiet):
            result = assistant.refine_plan(profile=prof, plan=plan_obj, **overrides)

        if prompt is not None:
            with _spinner("Refining plan with AI...", quiet):
                result, _ = assistant.refine_plan_with_llm(
                    profile=prof, plan=result, prompt=prompt
                )

        if format == "json":
            bundle = {
                "profile": prof.model_dump(mode="json"),
                "plan": result.model_dump(mode="json"),
            }
            json_str = json.dumps(bundle, indent=2)
            _write_output(json_str, output)
        else:
            _render_plan_panel(result)


@app.command(name="forecast-code")
def forecast_code(
    data: Annotated[str | None, typer.Argument(help="Path or URL to CSV file.")] = None,
    target: Annotated[str | None, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")] = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Forecast horizon (number of steps).")] = None,
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id_column: Annotated[str | None, typer.Option("--series-id-column", "-s", help="Series identifier column.")] = None,
    forecaster: Annotated[str | None, typer.Option("--forecaster", help="Override forecaster class.")] = None,
    estimator: Annotated[str | None, typer.Option("--estimator", help="Override estimator class.")] = None,
    estimator_kwargs: Annotated[str | None, typer.Option("--estimator-kwargs", help="Estimator hyperparameters as JSON string, e.g. '{\"n_estimators\": 200}'.")] = None,
    interval: Annotated[str | None, typer.Option("--interval", help="Prediction interval, e.g. '0.1,0.9'.")] = None,
    lags: Annotated[str | None, typer.Option("--lags", help="Explicit lags as an int or comma-separated list, e.g. '1,2,3'.")] = None,
    window_features: Annotated[str | None, typer.Option("--window-features", help="Explicit window features as JSON array, e.g. '[{\"stats\": [\"mean\"], \"window_sizes\": 7}]'.")] = None,
    from_plan: Annotated[str | None, typer.Option("--from-plan", help="Load plan bundle from JSON file or '-' for stdin.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: code or json.")] = "code",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write output to file.")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Generate a complete Python forecasting script."""
    with _error_handler():
        assistant = ForecastingAssistant()

        if from_plan is not None:
            bundle = _read_json_input(from_plan)
            prof = ForecastingProfile.model_validate(bundle["profile"])
            plan_obj = ForecastPlan.model_validate(bundle["plan"])
            result = assistant.forecast_code(
                data=None, target=None, steps=plan_obj.steps,
                profile=prof, plan=plan_obj,
            )
        else:
            if data is None or target is None or steps is None:
                console.print(
                    "[red]Error:[/red] DATA, --target, and --steps are required "
                    "unless --from-plan is provided."
                )
                raise typer.Exit(code=1)
            parsed_target = _parse_target(target)
            parsed_interval = _parse_interval(interval)
            parsed_estimator_kwargs = _parse_estimator_kwargs(estimator_kwargs)
            parsed_lags = _parse_lags(lags)
            parsed_window_features = _parse_window_features(window_features)

            with _spinner("Generating code...", quiet):
                result = assistant.forecast_code(
                    data=data, target=parsed_target, steps=steps,
                    date_column=date_column, series_id_column=series_id_column,
                    forecaster=forecaster, estimator=estimator,
                    estimator_kwargs=parsed_estimator_kwargs,
                    interval=parsed_interval, lags=parsed_lags,
                    window_features=parsed_window_features,
                )

        if format == "json":
            json_str = result.model_dump_json(indent=2)
            _write_output(json_str, output)
        else:
            if output is not None:
                output.write_text(result.code)
                console.print(f"[green]Code written to:[/green] {output}")
            else:
                console.print(render_code(result.code, title=None))


@app.command(name="backtest-code")
def backtest_code(
    data: Annotated[str | None, typer.Argument(help="Path or URL to CSV file.")] = None,
    target: Annotated[str | None, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")] = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Forecast horizon (number of steps).")] = None,
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id_column: Annotated[str | None, typer.Option("--series-id-column", "-s", help="Series identifier column.")] = None,
    forecaster: Annotated[str | None, typer.Option("--forecaster", help="Override forecaster class.")] = None,
    estimator: Annotated[str | None, typer.Option("--estimator", help="Override estimator class.")] = None,
    estimator_kwargs: Annotated[str | None, typer.Option("--estimator-kwargs", help="Estimator hyperparameters as JSON string, e.g. '{\"n_estimators\": 200}'.")] = None,
    interval: Annotated[str | None, typer.Option("--interval", help="Prediction interval, e.g. '0.1,0.9'.")] = None,
    lags: Annotated[str | None, typer.Option("--lags", help="Explicit lags as an int or comma-separated list, e.g. '1,2,3'.")] = None,
    window_features: Annotated[str | None, typer.Option("--window-features", help="Explicit window features as JSON array, e.g. '[{\"stats\": [\"mean\"], \"window_sizes\": 7}]'.")] = None,
    initial_train_size: Annotated[int | None, typer.Option("--initial-train-size", help="Initial training window size.")] = None,
    fold_stride: Annotated[int | None, typer.Option("--fold-stride", help="Fold stride (step size between folds).")] = None,
    refit: Annotated[bool, typer.Option("--refit/--no-refit", help="Whether to refit the model each fold.")] = False,
    fixed_train_size: Annotated[bool, typer.Option("--fixed-train-size/--expanding-train", help="Fixed or expanding training window.")] = True,
    gap: Annotated[int, typer.Option("--gap", help="Gap between training and test sets.")] = 0,
    allow_incomplete_fold: Annotated[bool, typer.Option("--allow-incomplete-fold/--no-incomplete-fold", help="Allow last fold with fewer observations.")] = True,
    from_plan: Annotated[str | None, typer.Option("--from-plan", help="Load plan bundle from JSON file or '-' for stdin.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: code or json.")] = "code",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write output to file.")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Generate a complete Python backtesting script without executing it."""
    with _error_handler():
        assistant = ForecastingAssistant()

        if from_plan is not None:
            bundle = _read_json_input(from_plan)
            prof = ForecastingProfile.model_validate(bundle["profile"])
            plan_obj = ForecastPlan.model_validate(bundle["plan"])
            resolved_steps = plan_obj.steps
            resolved_target = prof.data_profile.target
            resolved_date_column = prof.data_profile.date_column
            resolved_series_id = prof.data_profile.series_id_column
        else:
            if data is None or target is None or steps is None:
                console.print(
                    "[red]Error:[/red] DATA, --target, and --steps are required "
                    "unless --from-plan is provided."
                )
                raise typer.Exit(code=1)
            resolved_target = _parse_target(target)
            resolved_steps = steps
            resolved_date_column = date_column
            resolved_series_id = series_id_column
            prof = None
            plan_obj = None

        parsed_interval = _parse_interval(interval)
        parsed_estimator_kwargs = _parse_estimator_kwargs(estimator_kwargs)
        parsed_lags = _parse_lags(lags)
        parsed_window_features = _parse_window_features(window_features)

        with _spinner("Generating backtesting code...", quiet):
            # Profile (if needed)
            if prof is None:
                prof = assistant.profile(
                    data=data,
                    target=resolved_target,
                    date_column=resolved_date_column,
                    series_id_column=resolved_series_id,
                )

            # Plan (if needed)
            if plan_obj is None:
                plan_obj = assistant.plan(
                    profile=prof,
                    steps=resolved_steps,
                    forecaster=forecaster,
                    estimator=estimator,
                    estimator_kwargs=parsed_estimator_kwargs,
                    interval=parsed_interval,
                    lags=parsed_lags,
                    window_features=parsed_window_features,
                )

            # Generate CV
            cv_kwargs = {}
            if initial_train_size is not None:
                cv_kwargs["initial_train_size"] = initial_train_size
            if fold_stride is not None:
                cv_kwargs["fold_stride"] = fold_stride
            if refit:
                cv_kwargs["refit"] = refit
            if not fixed_train_size:
                cv_kwargs["fixed_train_size"] = fixed_train_size
            if gap != 0:
                cv_kwargs["gap"] = gap
            if not allow_incomplete_fold:
                cv_kwargs["allow_incomplete_fold"] = allow_incomplete_fold

            cv, _ = assistant.create_cv(
                profile=prof,
                plan=plan_obj,
                **cv_kwargs,
            )

            # Generate code
            result = assistant.backtest_code(
                data=data or "data.csv",
                target=resolved_target,
                cv=cv,
                date_column=resolved_date_column,
                series_id_column=resolved_series_id,
                profile=prof,
                plan=plan_obj,
            )

        if format == "json":
            json_str = result.model_dump_json(indent=2)
            _write_output(json_str, output)
        else:
            if output is not None:
                output.write_text(result.code)
                console.print(f"[green]Code written to:[/green] {output}")
            else:
                console.print(render_code(result.code, title=None))


def _render_forecast_results(result) -> None:
    """
    Print a Rich table summarizing forecast metrics and predictions.

    Parameters
    ----------
    result : ForecastResult
        Forecast result containing metrics and predictions.

    Returns
    -------
    None
    """
    console.print(render_metrics(result.metrics, title="Forecast Metrics"))
    console.print()
    console.print(render_dataframe(result.predictions, title="Predictions"))


def _forecast_result_to_json(result) -> str:
    """
    Serialize ForecastResult to JSON with DataFrame fields as records.

    Parameters
    ----------
    result : ForecastResult
        Forecast result to serialize.

    Returns
    -------
    json_str : str
        JSON string representation of the result.
    """
    data = {
        "profile": result.profile.model_dump(mode="json"),
        "plan": result.plan.model_dump(mode="json"),
        "code": result.code,
        "metrics": result.metrics.to_dict(orient="records"),
        "predictions": result.predictions.reset_index().to_dict(orient="records"),
    }
    return json.dumps(data, indent=2, default=str)


@app.command()
def forecast(
    data: Annotated[str, typer.Argument(help="Path to CSV file.")],
    target: Annotated[str | None, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")] = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Forecast horizon (number of steps).")] = None,
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id_column: Annotated[str | None, typer.Option("--series-id-column", "-s", help="Series identifier column.")] = None,
    forecaster: Annotated[str | None, typer.Option("--forecaster", help="Override forecaster class.")] = None,
    estimator: Annotated[str | None, typer.Option("--estimator", help="Override estimator class.")] = None,
    estimator_kwargs: Annotated[str | None, typer.Option("--estimator-kwargs", help="Estimator hyperparameters as JSON string, e.g. '{\"n_estimators\": 200}'.")] = None,
    interval: Annotated[str | None, typer.Option("--interval", help="Prediction interval, e.g. '0.1,0.9'.")] = None,
    exog_future: Annotated[Path | None, typer.Option("--exog-future", help="CSV with future exogenous variables.")] = None,
    from_plan: Annotated[str | None, typer.Option("--from-plan", help="Load plan bundle from JSON file or '-' for stdin.")] = None,
    output_predictions: Annotated[Path | None, typer.Option("--output-predictions", help="Save predictions as CSV.")] = None,
    output_code: Annotated[Path | None, typer.Option("--output-code", help="Save generated script to file.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: table or json.")] = "table",
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Run end-to-end forecasting and report metrics + predictions."""
    with _error_handler():
        assistant = ForecastingAssistant()
        parsed_interval = _parse_interval(interval)
        parsed_estimator_kwargs = _parse_estimator_kwargs(estimator_kwargs)

        if from_plan is not None:
            bundle = _read_json_input(from_plan)
            prof = ForecastingProfile.model_validate(bundle["profile"])
            plan_obj = ForecastPlan.model_validate(bundle["plan"])

            exog_future_df = _load_exog_future(
                exog_future,
                date_column=prof.data_profile.date_column,
                frequency=prof.data_profile.frequency,
            )

            with _spinner("Running forecast from plan...", quiet):
                result = assistant.forecast(
                    data=data, target=prof.data_profile.target,
                    steps=plan_obj.steps,
                    date_column=prof.data_profile.date_column,
                    series_id_column=prof.data_profile.series_id_column,
                    interval=parsed_interval or plan_obj.interval,
                    exog_future=exog_future_df,
                    profile=prof, plan=plan_obj,
                )
        else:
            if target is None or steps is None:
                console.print(
                    "[red]Error:[/red] --target and --steps are required "
                    "unless --from-plan is provided."
                )
                raise typer.Exit(code=1)
            parsed_target = _parse_target(target)

            exog_future_df = _load_exog_future(
                exog_future, date_column=date_column
            )

            with _spinner("Running forecast...", quiet):
                result = assistant.forecast(
                    data=data, target=parsed_target, steps=steps,
                    date_column=date_column, series_id_column=series_id_column,
                    forecaster=forecaster, estimator=estimator,
                    estimator_kwargs=parsed_estimator_kwargs,
                    interval=parsed_interval, exog_future=exog_future_df,
                )

        if output_predictions is not None:
            result.predictions.to_csv(output_predictions)
            console.print(f"[green]Predictions written to:[/green] {output_predictions}")

        if output_code is not None:
            output_code.write_text(result.code)
            console.print(f"[green]Code written to:[/green] {output_code}")

        if format == "json":
            json_str = _forecast_result_to_json(result)
            print(json_str)
        else:
            _render_forecast_results(result)


def _render_backtest_results(result) -> None:
    """
    Print Rich tables summarizing backtest metrics and predictions.

    Parameters
    ----------
    result : BacktestResult
        Backtest result containing metrics, predictions, and CV config.

    Returns
    -------
    None
    """
    console.print(render_cv_config(result.cv_config))
    console.print()
    console.print(render_metrics(result.metrics, title="Backtest Metrics"))
    console.print()
    console.print(render_dataframe(result.predictions, title="Backtest Predictions"))


def _backtest_result_to_json(result) -> str:
    """
    Serialize BacktestResult to JSON with DataFrame fields as records.

    Parameters
    ----------
    result : BacktestResult
        Backtest result to serialize.

    Returns
    -------
    json_str : str
        JSON string representation of the result.
    """
    data = {
        "profile": result.profile.model_dump(mode="json"),
        "plan": result.plan.model_dump(mode="json"),
        "cv_config": result.cv_config,
        "code": result.code,
        "metrics": result.metrics.to_dict(orient="records"),
        "predictions": result.predictions.reset_index().to_dict(orient="records"),
        "explanation": result.explanation,
    }
    return json.dumps(data, indent=2, default=str)


@app.command()
def backtest(
    data: Annotated[str, typer.Argument(help="Path to CSV file.")],
    target: Annotated[str | None, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")] = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Forecast horizon (number of steps).")] = None,
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id_column: Annotated[str | None, typer.Option("--series-id-column", "-s", help="Series identifier column.")] = None,
    forecaster: Annotated[str | None, typer.Option("--forecaster", help="Override forecaster class.")] = None,
    estimator: Annotated[str | None, typer.Option("--estimator", help="Override estimator class.")] = None,
    estimator_kwargs: Annotated[str | None, typer.Option("--estimator-kwargs", help="Estimator hyperparameters as JSON string.")] = None,
    initial_train_size: Annotated[int | None, typer.Option("--initial-train-size", help="Initial training window size.")] = None,
    fold_stride: Annotated[int | None, typer.Option("--fold-stride", help="Fold stride (step size between folds).")] = None,
    refit: Annotated[bool, typer.Option("--refit/--no-refit", help="Whether to refit the model each fold.")] = False,
    fixed_train_size: Annotated[bool, typer.Option("--fixed-train-size/--expanding-train", help="Fixed or expanding training window.")] = True,
    gap: Annotated[int, typer.Option("--gap", help="Gap between training and test sets.")] = 0,
    allow_incomplete_fold: Annotated[bool, typer.Option("--allow-incomplete-fold/--no-incomplete-fold", help="Allow last fold with fewer observations.")] = True,
    prompt: Annotated[str | None, typer.Option("--prompt", help="Optional prompt for LLM-assisted CV configuration.")] = None,
    llm: Annotated[str | None, typer.Option("--llm", help="LLM provider for CV configuration.")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Custom LLM endpoint URL.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key for the LLM provider.")] = None,
    from_plan: Annotated[str | None, typer.Option("--from-plan", help="Load plan bundle from JSON file or '-' for stdin.")] = None,
    output_predictions: Annotated[Path | None, typer.Option("--output-predictions", help="Save predictions as CSV.")] = None,
    output_code: Annotated[Path | None, typer.Option("--output-code", help="Save generated script to file.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: table or json.")] = "table",
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Run backtesting evaluation and report metrics + predictions."""
    with _error_handler():
        llm_value = _resolve(llm, "SKFORECAST_AI_LLM", "llm.provider")
        base_url_value = _resolve(base_url, "SKFORECAST_AI_BASE_URL", "llm.base_url")
        api_key_value = _resolve(api_key, "SKFORECAST_AI_API_KEY", "llm.api_key")
        parsed_estimator_kwargs = _parse_estimator_kwargs(estimator_kwargs)

        assistant = ForecastingAssistant(
            llm=llm_value,
            base_url=base_url_value,
            api_key=api_key_value,
        )

        if from_plan is not None:
            bundle = _read_json_input(from_plan)
            prof = ForecastingProfile.model_validate(bundle["profile"])
            plan_obj = ForecastPlan.model_validate(bundle["plan"])
            parsed_target = prof.data_profile.target
            resolved_steps = plan_obj.steps
            resolved_date_column = prof.data_profile.date_column
            resolved_series_id = prof.data_profile.series_id_column
        else:
            if target is None or steps is None:
                console.print(
                    "[red]Error:[/red] --target and --steps are required "
                    "unless --from-plan is provided."
                )
                raise typer.Exit(code=1)
            parsed_target = _parse_target(target)
            resolved_steps = steps
            resolved_date_column = date_column
            resolved_series_id = series_id_column
            prof = None
            plan_obj = None

        # Suppress warnings when outputting JSON to avoid polluting stdout
        warn_ctx = (
            warnings.catch_warnings()
            if format == "json"
            else contextlib.nullcontext()
        )

        with warn_ctx, _spinner("Running backtest...", quiet):
            if format == "json":
                warnings.simplefilter("ignore")

            # Profile (if needed)
            if prof is None:
                prof = assistant.profile(
                    data=data,
                    target=parsed_target,
                    date_column=resolved_date_column,
                    series_id_column=resolved_series_id,
                )

            # Plan (if needed)
            if plan_obj is None:
                plan_obj = assistant.plan(
                    profile=prof,
                    steps=resolved_steps,
                    forecaster=forecaster,
                    estimator=estimator,
                    estimator_kwargs=parsed_estimator_kwargs,
                )

            # Generate CV
            cv_kwargs = {}
            if initial_train_size is not None:
                cv_kwargs["initial_train_size"] = initial_train_size
            if fold_stride is not None and fold_stride != steps:
                cv_kwargs["fold_stride"] = fold_stride
            if refit:
                cv_kwargs["refit"] = refit
            if not fixed_train_size:
                cv_kwargs["fixed_train_size"] = fixed_train_size
            if gap != 0:
                cv_kwargs["gap"] = gap
            if not allow_incomplete_fold:
                cv_kwargs["allow_incomplete_fold"] = allow_incomplete_fold

            cv, _ = assistant.create_cv(
                profile=prof,
                plan=plan_obj,
                prompt=prompt,
                **cv_kwargs,
            )

            # Run backtest
            result = assistant.backtest(
                data=data,
                target=parsed_target,
                cv=cv,
                date_column=resolved_date_column,
                series_id_column=resolved_series_id,
                profile=prof,
                plan=plan_obj,
                show_progress=(not quiet and format != "json"),
            )

        if output_predictions is not None:
            result.predictions.to_csv(output_predictions)
            console.print(f"[green]Predictions written to:[/green] {output_predictions}")

        if output_code is not None:
            output_code.write_text(result.code)
            console.print(f"[green]Code written to:[/green] {output_code}")

        if format == "json":
            json_str = _backtest_result_to_json(result)
            print(json_str)
        else:
            _render_backtest_results(result)


@app.command()
def ask(
    prompt: Annotated[str, typer.Argument(help="Natural-language question about forecasting.")],
    data: Annotated[Path | None, typer.Option("--data", help="Path to CSV file for context.")] = None,
    target: Annotated[str | None, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")] = None,
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id_column: Annotated[str | None, typer.Option("--series-id-column", "-s", help="Series identifier column.")] = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Forecast horizon (required when --data is provided).")] = None,
    llm: Annotated[str | None, typer.Option("--llm", help="LLM provider, e.g. 'openai:gpt-4o-mini'.")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Custom LLM endpoint URL.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key for the LLM provider.")] = None,
    send_data_to_llm: Annotated[bool | None, typer.Option("--send-data-to-llm/--no-send-data-to-llm", help="Allow sending raw data to the LLM.")] = None,
    skills: Annotated[str | None, typer.Option("--skills", help="Comma-separated skill names to include.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: text or json.")] = "text",
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Ask a forecasting question using an LLM."""
    with _error_handler():
        llm_value = _resolve(llm, "SKFORECAST_AI_LLM", "llm.provider")
        base_url_value = _resolve(base_url, "SKFORECAST_AI_BASE_URL", "llm.base_url")
        api_key_value = _resolve(api_key, "SKFORECAST_AI_API_KEY", "llm.api_key")
        send_data_value = _resolve_bool(
            send_data_to_llm, "SKFORECAST_AI_SEND_DATA_TO_LLM",
            "llm.send_data_to_llm",
        )

        if llm_value is None:
            raise LLMRequiredError(method_name="ask")

        assistant = ForecastingAssistant(
            llm=llm_value,
            base_url=base_url_value,
            api_key=api_key_value,
            send_data_to_llm=send_data_value,
        )

        parsed_target = _parse_target(target) if target else None
        parsed_skills = [s.strip() for s in skills.split(",")] if skills else None

        data_path = str(data) if data is not None else None

        with _spinner("Thinking...", quiet):
            result = assistant.ask(
                prompt=prompt,
                data=data_path,
                target=parsed_target,
                date_column=date_column,
                series_id_column=series_id_column,
                steps=steps,
                skills=parsed_skills,
            )

        if format == "json":
            output_data = {"explanation": result.explanation}
            if result.profile is not None:
                output_data["profile"] = result.profile.model_dump(mode="json")
            if result.plan is not None:
                output_data["plan"] = result.plan.model_dump(mode="json")
            if result.code is not None:
                output_data["code"] = result.code
            print(json.dumps(output_data, indent=2, default=str))
        else:
            console.print(render_explanation(result.explanation, title="Explanation"))
