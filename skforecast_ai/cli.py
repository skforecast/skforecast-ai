################################################################################
#                                    CLI                                       #
#                                                                              #
# Typer CLI for skforecast-ai                                                  #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations

import contextlib
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Annotated, Literal
import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from pydantic import ValidationError

from . import __version__
from ._display import (
    render_code,
    render_cv_config,
    render_dataframe,
    render_explanation,
    render_llm_check,
    render_metrics,
    render_plan,
    render_profile,
)
from .assistant import ForecastingAssistant
from .config import (
    CONFIG_FILE,
    VALID_KEYS,
    get_config_value,
    load_config,
    set_config_value,
)
from .exceptions import (
    AllCandidatesFailedError,
    DataNotFoundError,
    ForecastExecutionError,
    InvalidInputError,
    LLMCallError,
    LLMRequiredError,
    SkforecastAIError,
)
from ._utils import _validate_lags, load_exog
from .schemas.errors import ErrorInfo
from .schemas.plans import ForecastPlan
from .schemas.profiles import ForecastingProfile

# Literal a CLI option accepts to ask for the deterministic default instead
# of an explicit value (`--lags auto` re-runs the PACF-based selection).
AUTO_VALUE = "auto"


# Option declarations shared by several commands. Each alias carries the
# type, flags and help text once; commands whose help differs keep their
# own declaration.
TargetOption = Annotated[str | None, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")]
DateColumnOption = Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")]
SeriesIdColumnOption = Annotated[str | None, typer.Option("--series-id-column", "-s", help="Series identifier column.")]
StepsOption = Annotated[int | None, typer.Option("--steps", help="Forecast horizon (number of steps).")]
ForecasterOption = Annotated[str | None, typer.Option("--forecaster", help="Override forecaster class.")]
EstimatorOption = Annotated[str | None, typer.Option("--estimator", help="Override estimator class, or the Hugging Face model ID for ForecasterFoundation (e.g. 'google/timesfm-3.0-pytorch').")]
EstimatorKwargsOption = Annotated[str | None, typer.Option("--estimator-kwargs", help="Estimator hyperparameters as JSON string, e.g. '{\"n_estimators\": 200}'.")]
IntervalOption = Annotated[str | None, typer.Option("--interval", help="Prediction interval as two quantiles between 0 and 1, e.g. '0.1,0.9' for an 80% interval.")]
LagsOption = Annotated[str | None, typer.Option("--lags", help="Explicit lags as an int or comma-separated list, e.g. '1,2,3', or 'auto' to re-run the deterministic selection when refining a saved plan.")]
WindowFeaturesOption = Annotated[str | None, typer.Option("--window-features", help="Explicit window features as JSON array, e.g. '[{\"stats\": [\"mean\"], \"window_size\": 7}]', or 'auto' to re-run the deterministic selection when refining a saved plan.")]
MetricOption = Annotated[str | None, typer.Option("--metric", help="Metric, or comma-separated metrics whose first one is the primary metric; only those are computed. 'auto' selects them from the data again when refining a saved plan.")]
UseExogOption = Annotated[str | None, typer.Option("--use-exog", help="Use the exogenous columns: 'true', 'false' (forecast then takes no --exog) or 'auto' for the rule.")]
DifferentiationOption = Annotated[str | None, typer.Option("--differentiation", help="Order of differencing of the target before training (an integer of at least 1), or 'auto' for the rule (no differencing). Machine learning forecasters only.")]
CalendarFeaturesOption = Annotated[str | None, typer.Option("--calendar-features", help="Comma-separated calendar features (e.g. 'month,day_of_week'), 'none' for none, or 'auto' for those selected from the frequency. Machine learning forecasters only.")]
TargetTransformerOption = Annotated[str | None, typer.Option("--target-transformer", help="Scaler of the target: 'StandardScaler', 'none', or 'auto' for the rule. Machine learning forecasters only.")]
DropnaOption = Annotated[str | None, typer.Option("--dropna-from-series", help="Drop the training rows with missing values: 'true', 'false' or 'auto' for the rule. Machine learning forecasters only.")]
ExogColumnsOption = Annotated[str | None, typer.Option("--exog-columns", help="Comma-separated columns to use as exogenous variables, 'none' for none, or 'auto' for every column that is not the target, the date or the series id. The other columns are not used.")]
FromPlanOption = Annotated[str | None, typer.Option("--from-plan", help="Load plan bundle from JSON file or '-' for stdin.")]
FromProfileOption = Annotated[str | None, typer.Option("--from-profile", help="Load profile from JSON file or '-' for stdin.")]
# CV options default to None so that only the flags actually passed reach
# `create_cv()`; the assistant decides the rest from the profile and plan.
InitialTrainSizeOption = Annotated[str | None, typer.Option("--initial-train-size", help="Initial training window: number of observations or an ISO date marking the end of the initial training set.")]
FoldStrideOption = Annotated[int | None, typer.Option("--fold-stride", help="Fold stride (step size between folds).")]
RefitOption = Annotated[bool | None, typer.Option("--refit/--no-refit", help="Whether to refit the model each fold (default: decided by the assistant).")]
FixedTrainSizeOption = Annotated[bool | None, typer.Option("--fixed-train-size/--expanding-train", help="Fixed or expanding training window when the forecaster is refitted; needs --refit (default: decided by the assistant).")]
GapOption = Annotated[int | None, typer.Option("--gap", help="Gap between training and test sets.")]
AllowIncompleteFoldOption = Annotated[bool | None, typer.Option("--allow-incomplete-fold/--no-incomplete-fold", help="Allow last fold with fewer observations (default: decided by the assistant).")]
BaseUrlOption = Annotated[str | None, typer.Option("--base-url", help="Custom LLM endpoint: server URL for ollama or an OpenAI-compatible API, AWS region for bedrock.")]
ApiKeyOption = Annotated[str | None, typer.Option("--api-key", help="API key for the LLM provider.")]
OutputOption = Annotated[Path | None, typer.Option("--output", "-o", help="Write output to file.")]
OutputPredictionsOption = Annotated[Path | None, typer.Option("--output-predictions", help="Save predictions as CSV.")]
QuietOption = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")]
TableFormatOption = Annotated[Literal["table", "json"], typer.Option("--format", help="Output format: table or json.")]
CodeFormatOption = Annotated[Literal["code", "json"], typer.Option("--format", help="Output format: code or json.")]
TextFormatOption = Annotated[Literal["text", "json"], typer.Option("--format", help="Output format: text or json.")]


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


def _showwarning_to_stderr(showwarning):
    """
    Wrap a `warnings.showwarning` handler so it writes to stderr.

    skforecast installs a handler that prints its warnings as rich panels
    on stdout, which breaks the JSON of `--format json`. The wrapper sends
    stdout to stderr while the handler runs, so the panels keep their
    format; a warning shown on an explicit `file` is left untouched.

    Parameters
    ----------
    showwarning : callable
        Handler to wrap, with the signature of `warnings.showwarning`.

    Returns
    -------
    wrapper : callable
        Handler that runs `showwarning` with stdout sent to stderr.
    """

    def wrapper(message, category, filename, lineno, file=None, line=None):
        if file is not None:
            showwarning(message, category, filename, lineno, file, line)
            return
        with contextlib.redirect_stdout(sys.stderr):
            showwarning(message, category, filename, lineno, file, line)

    wrapper._skforecast_ai_stderr = True
    return wrapper


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """
    Deterministic forecasting assistant powered by skforecast.

    Parameters
    ----------
    ctx : typer.Context
        Context of the invocation, used to restore the warning handler when
        the command ends.
    version : bool, default None
        Show version and exit.

    Returns
    -------
    None
    """
    # Every warning goes to stderr, so stdout holds only the output of the
    # command (the JSON document with `--format json`). The MCP server keeps
    # its own handling: it records warnings per call in a worker thread, and
    # `redirect_stdout` is not thread safe.
    if ctx.invoked_subcommand == "mcp":
        return
    previous = warnings.showwarning
    if not getattr(previous, "_skforecast_ai_stderr", False):
        warnings.showwarning = _showwarning_to_stderr(previous)

        def restore() -> None:
            warnings.showwarning = previous

        ctx.call_on_close(restore)


console = Console()
# Status messages go to stderr so `--format json` stays parseable on stdout.
err_console = Console(stderr=True)
config_app = typer.Typer(help="Manage persistent configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """
    Display current configuration.

    Keys that skforecast-ai does not read (left by an older version or
    written by hand) are listed as ignored instead of being shown as if
    they had an effect.

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

    ignored: list[str] = []
    for section, values in sorted(config.items()):
        if not isinstance(values, dict):
            ignored.append(section)
            continue
        for key, val in sorted(values.items()):
            full_key = f"{section}.{key}"
            if full_key not in VALID_KEYS:
                ignored.append(full_key)
                continue
            display_val = _mask_secret(full_key, str(val))
            table.add_row(full_key, display_val, str(CONFIG_FILE))

    if table.row_count:
        console.print(table)
    if ignored:
        console.print(
            f"[yellow]Ignored keys (not used by skforecast-ai):[/yellow] "
            f"{', '.join(ignored)}. You can remove them from {CONFIG_FILE}."
        )


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
        err_console.print(f"[red]Error:[/red] {escape(str(e))}")
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
            raise DataNotFoundError(f"File not found: '{source}'.")
        raw = path.read_text()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise InvalidInputError(
            f"Invalid JSON input: {e}",
            code = "data_unreadable",
        ) from e


def _read_plan_bundle(source: str) -> tuple[ForecastingProfile, ForecastPlan]:
    """
    Read the profile and the plan of a `--from-plan` bundle.

    Parameters
    ----------
    source : str
        Path to the JSON file written by `plan` or `refine-plan`, or `'-'`
        to read it from stdin.

    Returns
    -------
    profile : ForecastingProfile
        Profile of the bundle.
    plan : ForecastPlan
        Plan of the bundle.
    """
    bundle = _read_json_input(source)
    missing = [
        key for key in ("profile", "plan")
        if not isinstance(bundle, dict) or key not in bundle
    ]
    if missing:
        raise InvalidInputError(
            f"The --from-plan input has no {' or '.join(map(repr, missing))}: "
            f"pass the file written by `plan` or `refine-plan` with "
            f"--format json.",
            field = "from_plan",
        )
    profile = ForecastingProfile.model_validate(bundle["profile"])
    plan = ForecastPlan.model_validate(bundle["plan"])
    return profile, plan


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
    try:
        parts = [float(x.strip()) for x in interval_str.split(",")]
    except ValueError:
        parts = []
    if len(parts) != 2:
        raise typer.BadParameter(
            "Interval must be two comma-separated quantiles, e.g. '0.1,0.9'."
        )
    return parts


def _parse_test_size(value: str | None) -> int | float | str | None:
    """
    Parse the `--test-size` string into an int, float, or date string.

    An integer literal is returned as `int` (last N observations), a
    decimal literal as `float` (fraction of observations), and anything
    else is passed through unchanged as a date string (test-set start).

    Parameters
    ----------
    value : str, None
        Raw `--test-size` value. None selects prediction mode.

    Returns
    -------
    test_size : int, float, str, None
        Parsed test size, or None when input is None.
    """
    if value is None:
        return None
    value = value.strip()
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


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


def _collect_plan_overrides(
    forecaster: str | None,
    estimator: str | None,
    estimator_kwargs: dict | None,
    interval: list[float] | None,
    lags: int | list[int] | None = None,
    window_features: list[dict] | None = None,
    steps: int | None = None,
    reset_lags: bool = False,
    reset_window_features: bool = False,
    decisions: dict | None = None,
) -> dict:
    """
    Build a dict of plan overrides for `refine_plan`.

    Collects the CLI override options that are set so a saved plan loaded
    with `--from-plan` can be re-derived through `refine_plan`. Only keys
    with a value are included; if none are set the returned dict is empty
    and the caller can skip refinement. `refine_plan` treats a key passed
    as None as a request for the deterministic default, which the CLI
    expresses with `--lags auto` / `--window-features auto`: the reset
    flags add that key with a None value.

    Parameters
    ----------
    forecaster : str, None
        Forecaster class override.
    estimator : str, None
        Estimator class override.
    estimator_kwargs : dict, None
        Estimator keyword arguments override.
    interval : list of float, None
        Prediction interval override.
    lags : int, list of int, default None
        Lags override.
    window_features : list of dict, default None
        Window features override.
    steps : int, default None
        Forecast horizon override.
    reset_lags : bool, default False
        Ask for the deterministic lag selection (`lags=None`).
    reset_window_features : bool, default False
        Ask for the deterministic window feature selection
        (`window_features=None`).
    decisions : dict, default None
        Decisions read by `_parse_decisions`, added as they are (a None
        value asks for the rule).

    Returns
    -------
    overrides : dict
        Mapping of override keys to values, restricted to those provided.
    """
    overrides: dict = {}
    if forecaster is not None:
        overrides["forecaster"] = forecaster
    if estimator is not None:
        overrides["estimator"] = estimator
    if estimator_kwargs is not None:
        overrides["estimator_kwargs"] = estimator_kwargs
    if interval is not None:
        overrides["interval"] = interval
    if steps is not None:
        overrides["steps"] = steps
    if reset_lags:
        overrides["lags"] = None
    elif lags is not None:
        overrides["lags"] = lags
    if reset_window_features:
        overrides["window_features"] = None
    elif window_features is not None:
        overrides["window_features"] = window_features
    overrides.update(decisions or {})
    return overrides


# Warnings of `create_cv()` about a strategy whose backtest raises: the
# direct forecaster with a gap and the first training window shorter than
# the forecaster needs. `backtest` and `backtest-code` raise right after
# with the same reason, and a candidate of `compare` that cannot run fails
# with its own reason.
_STRATEGY_WARNINGS = (
    r".*`backtest\(\)` and `backtest_code\(\)` of this plan",
    r".*`backtest\(\)` of this plan with this strategy raises",
)


def _create_cv_to_backtest(assistant: ForecastingAssistant, **kwargs):
    """
    Build the strategy that `backtest`, `backtest-code` or `compare` runs,
    without the warnings of `create_cv()` about a strategy whose backtest of
    its plan raises: the command says it right after (a failed candidate,
    for `compare`).
    """
    with warnings.catch_warnings():
        for pattern in _STRATEGY_WARNINGS:
            warnings.filterwarnings(
                action   = "ignore",
                message  = pattern,
                category = UserWarning,
            )
        return assistant.create_cv(**kwargs)


def _parse_exog_columns(value: str | None) -> list[str] | None:
    """
    Read `--exog-columns`: `'auto'` (or the option left out) maps to None,
    every column; `'none'` to an empty list. The names are checked by
    `profile()`.
    """
    if value is None or _is_auto(value):
        return None
    if value.strip().lower() == "none":
        return []
    return [name.strip() for name in value.split(",")]


def _parse_bool_option(value: str, option: str) -> bool:
    """
    Read 'true' or 'false' (any case) given to a three-state option.
    """
    text = value.strip().lower()
    if text not in ("true", "false"):
        raise typer.BadParameter(
            f"{option} takes 'true', 'false' or 'auto', got {value!r}."
        )
    return text == "true"


def _parse_decisions(
    metric: str | None = None,
    use_exog: str | None = None,
    differentiation: str | None = None,
    calendar_features: str | None = None,
    target_transformer: str | None = None,
    dropna_from_series: str | None = None,
) -> dict:
    """
    Read the options of the decisions added in 0.4.0 (`--metric`,
    `--use-exog`, `--differentiation`, `--calendar-features`,
    `--target-transformer`, `--dropna-from-series`).

    Each option given is a key of the result: `'auto'` maps to None, which
    asks `plan()` for the rule (and `refine_plan()` to decide again), so
    the dict can be passed to `plan()` and merged into the overrides of
    `refine_plan()` as it is. The values are checked by the core.

    Returns
    -------
    decisions : dict
        Keyword arguments of `plan()` for the options given.
    """
    decisions: dict = {}
    if metric is not None:
        metrics = [name.strip() for name in metric.split(",")]
        decisions["metric"] = (
            None if _is_auto(metric)
            else metrics[0] if len(metrics) == 1 else metrics
        )
    if use_exog is not None:
        decisions["use_exog"] = (
            None if _is_auto(use_exog)
            else _parse_bool_option(use_exog, "--use-exog")
        )
    if differentiation is not None:
        if _is_auto(differentiation):
            decisions["differentiation"] = None
        else:
            try:
                decisions["differentiation"] = int(differentiation.strip())
            except ValueError as e:
                raise typer.BadParameter(
                    f"--differentiation takes an integer or 'auto', got "
                    f"{differentiation!r}."
                ) from e
    if calendar_features is not None:
        if _is_auto(calendar_features):
            decisions["calendar_features"] = None
        elif calendar_features.strip().lower() == "none":
            decisions["calendar_features"] = []
        else:
            decisions["calendar_features"] = [
                name.strip() for name in calendar_features.split(",")
            ]
    if target_transformer is not None:
        decisions["target_transformer"] = (
            None if _is_auto(target_transformer) else target_transformer.strip()
        )
    if dropna_from_series is not None:
        decisions["dropna_from_series"] = (
            None if _is_auto(dropna_from_series)
            else _parse_bool_option(dropna_from_series, "--dropna-from-series")
        )
    return decisions


def _collect_cv_overrides(
    initial_train_size: int | str | None,
    fold_stride: int | None,
    refit: bool | None,
    fixed_train_size: bool | None,
    gap: int | None,
    allow_incomplete_fold: bool | None,
) -> dict:
    """
    Build the `create_cv` keyword arguments from the CLI options passed.

    Only options with a value are forwarded, so a flag the user did not
    pass leaves the decision to `create_cv()` instead of overriding it
    with the CLI default. This is what lets `--no-refit` or
    `--fixed-train-size` take effect: forwarded only when explicitly set,
    never dropped for matching a default.

    Parameters
    ----------
    initial_train_size : int, str, None
        Parsed --initial-train-size value.
    fold_stride : int, None
        --fold-stride value.
    refit : bool, None
        --refit / --no-refit value.
    fixed_train_size : bool, None
        --fixed-train-size / --expanding-train value.
    gap : int, None
        --gap value.
    allow_incomplete_fold : bool, None
        --allow-incomplete-fold / --no-incomplete-fold value.

    Returns
    -------
    cv_kwargs : dict
        Keyword arguments for `create_cv`, restricted to those provided.
    """
    candidates = {
        "initial_train_size": initial_train_size,
        "fold_stride": fold_stride,
        "refit": refit,
        "fixed_train_size": fixed_train_size,
        "gap": gap,
        "allow_incomplete_fold": allow_incomplete_fold,
    }
    return {key: value for key, value in candidates.items() if value is not None}


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


# Remedy for a failed script: `--output-code` is only written when the
# command succeeds, so the script comes from the matching `*-code` command.
EXECUTION_TIP = (
    "Run forecast-code or backtest-code with the same options to get the "
    "script that failed."
)
VALIDATION_TIP = "Use --format json with the source command to produce valid input."
NO_LLM_MESSAGE = (
    "No LLM configured. Set the SKFORECAST_AI_LLM environment variable or "
    "use the --llm flag."
)


def _report_error(exc: Exception, json_errors: bool) -> None:
    """
    Print an error on stderr, as text or as a JSON object.

    Parameters
    ----------
    exc : Exception
        Error to report.
    json_errors : bool
        Whether to print `{"error": {...}}`, the fields of `ErrorInfo`,
        instead of text (`--format json`).

    Returns
    -------
    None
    """
    label = "Error"
    message = str(exc)
    tip = exc.hint if isinstance(exc, SkforecastAIError) else None
    if isinstance(exc, LLMRequiredError):
        message = NO_LLM_MESSAGE
    elif isinstance(exc, LLMCallError):
        label = "LLM Error"
    elif isinstance(exc, ForecastExecutionError):
        label = "Execution Error"
        tip = tip or EXECUTION_TIP
    elif isinstance(exc, AllCandidatesFailedError):
        label = "Comparison Error"
    elif isinstance(exc, ValidationError):
        details = "; ".join(
            f"{err['loc'][0]}: {err['msg']}" if err.get("loc") else err["msg"]
            for err in exc.errors()[:3]
        )
        message = (
            f"Invalid input data: {exc.error_count()} validation error(s): "
            f"{details}"
        )
        tip = tip or VALIDATION_TIP

    if json_errors:
        info = ErrorInfo.from_exception(exc)
        update = {}
        if isinstance(exc, LLMRequiredError):
            update["message"] = message
        if info.hint is None and tip is not None:
            update["hint"] = tip
        if update:
            info = info.model_copy(update=update)
        print(json.dumps({"error": info.model_dump(mode="json")}), file=sys.stderr)
        return

    # The message is escaped: rich markup would eat text in brackets such
    # as `[lower, upper]`.
    err_console.print(f"[red]{label}:[/red] {escape(message)}")
    if tip is not None:
        err_console.print(f"[dim]Tip: {escape(tip)}[/dim]")


@contextlib.contextmanager
def _error_handler(json_errors: bool = False):
    """
    Report known exceptions on stderr and exit with code 1.

    Parameters
    ----------
    json_errors : bool, default False
        Whether to report them as a JSON object (`--format json`).
    """
    try:
        yield
    except typer.BadParameter as e:
        # A value an option parser rejects is a usage error (code 2); the
        # parser prints it as text unless the output is JSON.
        if not json_errors:
            raise
        _report_error(InvalidInputError(e.message), json_errors)
        raise typer.Exit(code=2)
    except (
        SkforecastAIError, ValidationError, FileNotFoundError, ValueError,
        KeyError, TypeError,
    ) as e:
        _report_error(e, json_errors)
        raise typer.Exit(code=1)


def _check_steps_match_plan(steps: int | None, plan: ForecastPlan) -> None:
    """
    Reject a `--steps` that differs from the steps of a `--from-plan` plan.

    The plan fixes the horizon, as in the Python API: a different `--steps`
    would otherwise be ignored.

    Parameters
    ----------
    steps : int, None
        Value of `--steps`, None when not passed.
    plan : ForecastPlan
        Plan read from `--from-plan`.

    Returns
    -------
    None
    """
    if steps is not None and steps != plan.steps:
        raise InvalidInputError(
            f"--steps ({steps}) does not match the steps of the plan in "
            f"--from-plan ({plan.steps}). Omit --steps to use the plan's "
            f"horizon, or change it with `refine-plan --steps`.",
            field = "steps",
        )


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

    The "Plan Warnings" panel is left out: each warning is already printed
    when the plan is built.

    Parameters
    ----------
    plan : ForecastPlan
        Plan object to render.

    Returns
    -------
    None
    """
    console.print(render_plan(plan, show_warnings=False))


@app.command()
def profile(
    data: Annotated[str, typer.Argument(help="Path or URL to CSV file.")],
    target: Annotated[str, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")],
    date_column: DateColumnOption = None,
    series_id_column: SeriesIdColumnOption = None,
    exog_columns: ExogColumnsOption = None,
    format: TableFormatOption = "table",
    output: OutputOption = None,
    quiet: QuietOption = False,
) -> None:
    """Profile a dataset and recommend a forecaster and an estimator."""
    with _error_handler(json_errors=format == "json"):
        assistant = ForecastingAssistant()
        parsed_target = _parse_target(target)
        parsed_exog_columns = _parse_exog_columns(exog_columns)

        with _spinner("Profiling dataset...", quiet):
            result = assistant.profile(
                data=data, target=parsed_target, date_column=date_column,
                series_id_column=series_id_column,
                exog_columns=parsed_exog_columns,
            )

        if format == "json":
            json_str = result.model_dump_json(indent=2)
            _write_output(json_str, output)
        else:
            _render_profile_table(result)


def _is_auto(value: str | None) -> bool:
    """
    Tell whether a CLI option asks for the deterministic default.

    Parameters
    ----------
    value : str, None
        Raw option value.

    Returns
    -------
    is_auto : bool
        True when the value is the literal `'auto'` (case-insensitive).
    """
    return value is not None and value.strip().lower() == AUTO_VALUE


def _parse_lags(lags_str: str | None) -> int | list[int] | None:
    """
    Parse lags string into an int or list of ints.

    The parsed value goes through the same `_validate_lags` check the
    Python API applies, so the CLI cannot accept a lag specification that
    `plan()` would reject. The literal `'auto'` maps to None, which asks
    for the deterministic lag selection.

    Parameters
    ----------
    lags_str : str, None
        Comma-separated lag indices (e.g. '1,2,3'), a single int, or
        'auto'.

    Returns
    -------
    lags : int, list of int, None
        Parsed lags or None.
    """
    if lags_str is None or _is_auto(lags_str):
        return None
    try:
        if "," in lags_str:
            lags: int | list[int] = [int(x.strip()) for x in lags_str.split(",")]
        else:
            lags = int(lags_str)
    except ValueError as e:
        raise typer.BadParameter(f"Invalid format for --lags: {e}") from e

    try:
        _validate_lags(lags)
    except ValueError as e:
        raise typer.BadParameter(f"--lags: {e}") from e
    return lags


def _parse_window_features(wf_str: str | None) -> list[dict] | None:
    """
    Parse window features JSON string.

    Parameters
    ----------
    wf_str : str, None
        JSON string representing a list of dicts, or 'auto' to ask for the
        deterministic window feature selection (maps to None).

    Returns
    -------
    window_features : list of dict, None
        Parsed list of dicts or None.
    """
    if wf_str is None or _is_auto(wf_str):
        return None
    try:
        parsed = json.loads(wf_str)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"Invalid JSON in --window-features: {e}") from e
    if not isinstance(parsed, list) or not all(isinstance(x, dict) for x in parsed):
        raise typer.BadParameter(
            "--window-features must be a JSON array of objects, "
            "e.g. '[{\"stats\": [\"mean\"], \"window_size\": 7}]'."
        )
    return parsed


def _parse_initial_train_size(value: str | None) -> int | str | None:
    """
    Parse the --initial-train-size option.

    An integer literal is the number of observations; any other text is
    passed through as a date string, which `create_cv()` validates
    against the dataset index (it must be an ISO date inside the series
    range, and the dataset must have a datetime index).

    Parameters
    ----------
    value : str, None
        Raw option value.

    Returns
    -------
    initial_train_size : int, str, None
        Parsed value or None.
    """
    if value is None:
        return None
    text = value.strip()
    try:
        return int(text)
    except ValueError:
        return text


@app.command()
def plan(
    data: Annotated[str | None, typer.Argument(help="Path or URL to CSV file.")] = None,
    target: TargetOption = None,
    steps: StepsOption = None,
    date_column: DateColumnOption = None,
    series_id_column: SeriesIdColumnOption = None,
    forecaster: ForecasterOption = None,
    estimator: EstimatorOption = None,
    estimator_kwargs: EstimatorKwargsOption = None,
    interval: IntervalOption = None,
    lags: LagsOption = None,
    window_features: WindowFeaturesOption = None,
    metric: MetricOption = None,
    use_exog: UseExogOption = None,
    differentiation: DifferentiationOption = None,
    calendar_features: CalendarFeaturesOption = None,
    target_transformer: TargetTransformerOption = None,
    dropna_from_series: DropnaOption = None,
    exog_columns: ExogColumnsOption = None,
    from_profile: FromProfileOption = None,
    format: TableFormatOption = "table",
    output: OutputOption = None,
    quiet: QuietOption = False,
) -> None:
    """Generate a detailed forecasting plan from a dataset."""
    with _error_handler(json_errors=format == "json"):
        if steps is None:
            raise InvalidInputError(
                "--steps is required.",
                field = "steps",
            )

        assistant = ForecastingAssistant()
        parsed_interval = _parse_interval(interval)
        parsed_estimator_kwargs = _parse_estimator_kwargs(estimator_kwargs)
        parsed_lags = _parse_lags(lags)
        parsed_window_features = _parse_window_features(window_features)
        decisions = _parse_decisions(
            metric             = metric,
            use_exog           = use_exog,
            differentiation    = differentiation,
            calendar_features  = calendar_features,
            target_transformer = target_transformer,
            dropna_from_series = dropna_from_series,
        )

        parsed_exog_columns = _parse_exog_columns(exog_columns)

        if from_profile is not None:
            if parsed_exog_columns is not None:
                # The columns are chosen when the data is profiled: the
                # profile loaded already decided them.
                raise InvalidInputError(
                    "--exog-columns applies when the data is profiled, not "
                    "with --from-profile: run `skforecast-ai profile` with "
                    "--exog-columns instead.",
                    field = "exog_columns",
                )
            profile_data = _read_json_input(from_profile)
            prof = ForecastingProfile.model_validate(profile_data)
        else:
            if data is None or target is None:
                raise InvalidInputError(
                    "DATA and --target are required "
                    "unless --from-profile is provided.",
                )
            parsed_target = _parse_target(target)
            with _spinner("Profiling...", quiet):
                prof = assistant.profile(
                    data=data, target=parsed_target, date_column=date_column,
                    series_id_column=series_id_column,
                    exog_columns=parsed_exog_columns,
                )

        with _spinner("Planning...", quiet):
            result = assistant.plan(
                profile=prof, steps=steps, forecaster=forecaster,
                estimator=estimator, estimator_kwargs=parsed_estimator_kwargs,
                interval=parsed_interval, lags=parsed_lags,
                window_features=parsed_window_features, **decisions,
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
    forecaster: ForecasterOption = None,
    estimator: EstimatorOption = None,
    estimator_kwargs: EstimatorKwargsOption = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Override forecast horizon.")] = None,
    interval: Annotated[str | None, typer.Option("--interval", help="Override prediction interval as two quantiles between 0 and 1, e.g. '0.1,0.9'.")] = None,
    lags: LagsOption = None,
    window_features: WindowFeaturesOption = None,
    metric: MetricOption = None,
    use_exog: UseExogOption = None,
    differentiation: DifferentiationOption = None,
    calendar_features: CalendarFeaturesOption = None,
    target_transformer: TargetTransformerOption = None,
    dropna_from_series: DropnaOption = None,
    prompt: Annotated[str | None, typer.Option("--prompt", help="Domain knowledge in natural language; the LLM proposes lags and window features from it.")] = None,
    llm: Annotated[str | None, typer.Option("--llm", help="LLM provider and model, e.g. 'openai:gpt-5.5'.")] = None,
    base_url: BaseUrlOption = None,
    api_key: ApiKeyOption = None,
    format: TableFormatOption = "table",
    output: OutputOption = None,
    quiet: QuietOption = False,
) -> None:
    """Refine an existing forecasting plan by overriding specific fields or using LLM guidance."""
    with _error_handler(json_errors=format == "json"):
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

        overrides = _collect_plan_overrides(
            forecaster=forecaster,
            estimator=estimator,
            estimator_kwargs=parsed_estimator_kwargs,
            interval=parsed_interval,
            lags=parsed_lags,
            window_features=parsed_window_features,
            steps=steps,
            reset_lags=_is_auto(lags),
            reset_window_features=_is_auto(window_features),
            decisions=_parse_decisions(
                metric             = metric,
                use_exog           = use_exog,
                differentiation    = differentiation,
                calendar_features  = calendar_features,
                target_transformer = target_transformer,
                dropna_from_series = dropna_from_series,
            ),
        )

        with _spinner("Refining plan...", quiet):
            result = assistant.refine_plan(
                profile=prof, plan=plan_obj, prompt=prompt, **overrides
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
    target: TargetOption = None,
    steps: StepsOption = None,
    date_column: DateColumnOption = None,
    series_id_column: SeriesIdColumnOption = None,
    forecaster: ForecasterOption = None,
    estimator: EstimatorOption = None,
    estimator_kwargs: EstimatorKwargsOption = None,
    interval: IntervalOption = None,
    lags: LagsOption = None,
    window_features: WindowFeaturesOption = None,
    metric: MetricOption = None,
    use_exog: UseExogOption = None,
    differentiation: DifferentiationOption = None,
    calendar_features: CalendarFeaturesOption = None,
    target_transformer: TargetTransformerOption = None,
    dropna_from_series: DropnaOption = None,
    from_plan: FromPlanOption = None,
    format: CodeFormatOption = "code",
    output: OutputOption = None,
    quiet: QuietOption = False,
) -> None:
    """Generate a complete Python forecasting script."""
    with _error_handler(json_errors=format == "json"):
        assistant = ForecastingAssistant()
        parsed_interval = _parse_interval(interval)
        parsed_estimator_kwargs = _parse_estimator_kwargs(estimator_kwargs)
        parsed_lags = _parse_lags(lags)
        parsed_window_features = _parse_window_features(window_features)
        decisions = _parse_decisions(
            metric             = metric,
            use_exog           = use_exog,
            differentiation    = differentiation,
            calendar_features  = calendar_features,
            target_transformer = target_transformer,
            dropna_from_series = dropna_from_series,
        )

        if from_plan is not None:
            prof, plan_obj = _read_plan_bundle(from_plan)
            _check_steps_match_plan(steps, plan_obj)

            # Overrides supplied alongside --from-plan are applied on top of
            # the saved plan through refine_plan, as `forecast` does, instead
            # of being dropped silently.
            plan_overrides = _collect_plan_overrides(
                forecaster=forecaster,
                estimator=estimator,
                estimator_kwargs=parsed_estimator_kwargs,
                interval=parsed_interval,
                lags=parsed_lags,
                window_features=parsed_window_features,
                reset_lags=_is_auto(lags),
                reset_window_features=_is_auto(window_features),
                decisions=decisions,
            )
            if plan_overrides:
                plan_obj = assistant.refine_plan(
                    profile=prof, plan=plan_obj, **plan_overrides
                )
            # DATA, when given, is the file the script loads (as in
            # `backtest-code`); the profile of the bundle describes it.
            result = assistant.forecast_code(
                data=data, target=None, steps=plan_obj.steps,
                profile=prof, plan=plan_obj,
            )
        else:
            if data is None or target is None or steps is None:
                raise InvalidInputError(
                    "DATA, --target, and --steps are required "
                    "unless --from-plan is provided.",
                )
            parsed_target = _parse_target(target)

            with _spinner("Generating code...", quiet):
                result = assistant.forecast_code(
                    data=data, target=parsed_target, steps=steps,
                    date_column=date_column, series_id_column=series_id_column,
                    forecaster=forecaster, estimator=estimator,
                    estimator_kwargs=parsed_estimator_kwargs,
                    interval=parsed_interval, lags=parsed_lags,
                    window_features=parsed_window_features, **decisions,
                )

        if format == "json":
            json_str = result.model_dump_json(indent=2)
            _write_output(json_str, output)
        else:
            if output is not None:
                output.write_text(result.code)
                err_console.print(f"[green]Code written to:[/green] {output}")
            else:
                console.print(render_code(result.code, title=None))


@app.command(name="backtest-code")
def backtest_code(
    data: Annotated[str | None, typer.Argument(help="Path or URL to CSV file.")] = None,
    target: TargetOption = None,
    steps: StepsOption = None,
    date_column: DateColumnOption = None,
    series_id_column: SeriesIdColumnOption = None,
    forecaster: ForecasterOption = None,
    estimator: EstimatorOption = None,
    estimator_kwargs: EstimatorKwargsOption = None,
    interval: IntervalOption = None,
    lags: LagsOption = None,
    window_features: WindowFeaturesOption = None,
    metric: MetricOption = None,
    use_exog: UseExogOption = None,
    differentiation: DifferentiationOption = None,
    calendar_features: CalendarFeaturesOption = None,
    target_transformer: TargetTransformerOption = None,
    dropna_from_series: DropnaOption = None,
    initial_train_size: InitialTrainSizeOption = None,
    fold_stride: FoldStrideOption = None,
    refit: RefitOption = None,
    fixed_train_size: FixedTrainSizeOption = None,
    gap: GapOption = None,
    allow_incomplete_fold: AllowIncompleteFoldOption = None,
    from_plan: FromPlanOption = None,
    format: CodeFormatOption = "code",
    output: OutputOption = None,
    quiet: QuietOption = False,
) -> None:
    """Generate a complete Python backtesting script without executing it."""
    with _error_handler(json_errors=format == "json"):
        assistant = ForecastingAssistant()

        if from_plan is not None:
            prof, plan_obj = _read_plan_bundle(from_plan)
            _check_steps_match_plan(steps, plan_obj)
            resolved_steps = plan_obj.steps
            resolved_target = _parse_target(target) if target else None
            resolved_date_column = date_column
            resolved_series_id = series_id_column
        else:
            if data is None or target is None or steps is None:
                raise InvalidInputError(
                    "DATA, --target, and --steps are required "
                    "unless --from-plan is provided.",
                )
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
        decisions = _parse_decisions(
            metric             = metric,
            use_exog           = use_exog,
            differentiation    = differentiation,
            calendar_features  = calendar_features,
            target_transformer = target_transformer,
            dropna_from_series = dropna_from_series,
        )

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
                    **decisions,
                )
            else:
                # Overrides supplied alongside --from-plan are applied on top
                # of the saved plan, as `backtest` does.
                plan_overrides = _collect_plan_overrides(
                    forecaster=forecaster,
                    estimator=estimator,
                    estimator_kwargs=parsed_estimator_kwargs,
                    interval=parsed_interval,
                    lags=parsed_lags,
                    window_features=parsed_window_features,
                    reset_lags=_is_auto(lags),
                    reset_window_features=_is_auto(window_features),
                    decisions=decisions,
                )
                if plan_overrides:
                    plan_obj = assistant.refine_plan(
                        profile=prof, plan=plan_obj, **plan_overrides
                    )

            # Generate CV
            cv_kwargs = _collect_cv_overrides(
                initial_train_size=_parse_initial_train_size(initial_train_size),
                fold_stride=fold_stride,
                refit=refit,
                fixed_train_size=fixed_train_size,
                gap=gap,
                allow_incomplete_fold=allow_incomplete_fold,
            )

            cv = _create_cv_to_backtest(
                assistant,
                profile=prof,
                plan=plan_obj,
                **cv_kwargs,
            ).cv

            # Generate code
            # Without DATA the script is rendered from the saved profile,
            # which records the path the data was profiled from.
            result = assistant.backtest_code(
                data=data,
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
                err_console.print(f"[green]Code written to:[/green] {output}")
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
    if result.metrics is not None:
        console.print(render_metrics(result.metrics, title="Forecast Metrics"))
        console.print()
    console.print(render_dataframe(result.predictions, title="Predictions"))


def _result_to_json(result) -> str:
    """
    Serialize any workflow result to JSON.

    Relies on the results' own JSON serialization: DataFrame fields become
    lists of row records with the index as a leading column.

    Parameters
    ----------
    result : ForecastResult, BacktestResult, ComparisonResult, AskResult
        Result to serialize.

    Returns
    -------
    json_str : str
        JSON string representation of the result.
    """
    return json.dumps(result.model_dump(mode="json"), indent=2, default=str)


@app.command()
def forecast(
    data: Annotated[str, typer.Argument(help="Path or URL to CSV file.")],
    target: TargetOption = None,
    steps: StepsOption = None,
    date_column: DateColumnOption = None,
    series_id_column: SeriesIdColumnOption = None,
    forecaster: ForecasterOption = None,
    estimator: EstimatorOption = None,
    estimator_kwargs: EstimatorKwargsOption = None,
    interval: IntervalOption = None,
    lags: LagsOption = None,
    window_features: WindowFeaturesOption = None,
    metric: MetricOption = None,
    use_exog: UseExogOption = None,
    differentiation: DifferentiationOption = None,
    calendar_features: CalendarFeaturesOption = None,
    target_transformer: TargetTransformerOption = None,
    dropna_from_series: DropnaOption = None,
    test_size: Annotated[str | None, typer.Option("--test-size", help="Evaluation test set size: int (last N obs), float in (0,1) (fraction), or a date (test set start). The test set must hold exactly --steps observations. When omitted, forecasts the future.")] = None,
    exog: Annotated[Path | None, typer.Option("--exog", help="CSV with future exogenous values covering the forecast horizon (prediction mode only).")] = None,
    from_plan: FromPlanOption = None,
    output_predictions: OutputPredictionsOption = None,
    output_code: Annotated[Path | None, typer.Option("--output-code", help="Save generated script to file.")] = None,
    format: TableFormatOption = "table",
    quiet: QuietOption = False,
) -> None:
    """Run end-to-end forecasting and report predictions, plus metrics with --test-size."""
    with _error_handler(json_errors=format == "json"):
        assistant = ForecastingAssistant()
        parsed_interval = _parse_interval(interval)
        parsed_estimator_kwargs = _parse_estimator_kwargs(estimator_kwargs)
        parsed_test_size = _parse_test_size(test_size)
        parsed_lags = _parse_lags(lags)
        parsed_window_features = _parse_window_features(window_features)
        decisions = _parse_decisions(
            metric             = metric,
            use_exog           = use_exog,
            differentiation    = differentiation,
            calendar_features  = calendar_features,
            target_transformer = target_transformer,
            dropna_from_series = dropna_from_series,
        )

        if from_plan is not None:
            prof, plan_obj = _read_plan_bundle(from_plan)
            _check_steps_match_plan(steps, plan_obj)

            # Any override supplied alongside --from-plan is applied on top
            # of the saved plan by re-deriving it through refine_plan. This
            # keeps coupled fields (e.g. interval and interval_method)
            # consistent and avoids silently dropping CLI overrides.
            plan_overrides = _collect_plan_overrides(
                forecaster=forecaster,
                estimator=estimator,
                estimator_kwargs=parsed_estimator_kwargs,
                interval=parsed_interval,
                lags=parsed_lags,
                window_features=parsed_window_features,
                reset_lags=_is_auto(lags),
                reset_window_features=_is_auto(window_features),
                decisions=decisions,
            )
            if plan_overrides:
                plan_obj = assistant.refine_plan(
                    profile=prof, plan=plan_obj, **plan_overrides
                )

            exog_df = load_exog(
                exog,
                date_column      = prof.data_profile.date_column,
                series_id_column = prof.data_profile.series_id_column,
            )

            with _spinner("Running forecast from plan...", quiet):
                result = assistant.forecast(
                    data=data,
                    target=_parse_target(target) if target else None,
                    steps=plan_obj.steps,
                    date_column=date_column,
                    series_id_column=series_id_column,
                    test_size=parsed_test_size,
                    exog=exog_df,
                    profile=prof, plan=plan_obj,
                )
        else:
            if target is None or steps is None:
                raise InvalidInputError(
                    "--target and --steps are required "
                    "unless --from-plan is provided.",
                )
            parsed_target = _parse_target(target)

            exog_df = load_exog(
                exog,
                date_column      = date_column,
                series_id_column = series_id_column,
            )

            with _spinner("Running forecast...", quiet):
                result = assistant.forecast(
                    data=data, target=parsed_target, steps=steps,
                    date_column=date_column, series_id_column=series_id_column,
                    forecaster=forecaster, estimator=estimator,
                    estimator_kwargs=parsed_estimator_kwargs,
                    interval=parsed_interval,
                    lags=parsed_lags, window_features=parsed_window_features,
                    test_size=parsed_test_size, exog=exog_df, **decisions,
                )

        if output_predictions is not None:
            result.predictions.to_csv(output_predictions)
            err_console.print(f"[green]Predictions written to:[/green] {output_predictions}")

        if output_code is not None:
            output_code.write_text(result.code)
            err_console.print(f"[green]Code written to:[/green] {output_code}")

        if format == "json":
            json_str = _result_to_json(result)
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


@app.command()
def backtest(
    data: Annotated[str, typer.Argument(help="Path or URL to CSV file.")],
    target: TargetOption = None,
    steps: StepsOption = None,
    date_column: DateColumnOption = None,
    series_id_column: SeriesIdColumnOption = None,
    forecaster: ForecasterOption = None,
    estimator: EstimatorOption = None,
    estimator_kwargs: EstimatorKwargsOption = None,
    interval: IntervalOption = None,
    lags: LagsOption = None,
    window_features: WindowFeaturesOption = None,
    metric: MetricOption = None,
    use_exog: UseExogOption = None,
    differentiation: DifferentiationOption = None,
    calendar_features: CalendarFeaturesOption = None,
    target_transformer: TargetTransformerOption = None,
    dropna_from_series: DropnaOption = None,
    initial_train_size: InitialTrainSizeOption = None,
    fold_stride: FoldStrideOption = None,
    refit: RefitOption = None,
    fixed_train_size: FixedTrainSizeOption = None,
    gap: GapOption = None,
    allow_incomplete_fold: AllowIncompleteFoldOption = None,
    prompt: Annotated[str | None, typer.Option("--prompt", help="Deployment scenario in natural language; the LLM translates it into the cross-validation strategy.")] = None,
    llm: Annotated[str | None, typer.Option("--llm", help="LLM provider and model, e.g. 'openai:gpt-5.5'.")] = None,
    base_url: BaseUrlOption = None,
    api_key: ApiKeyOption = None,
    from_plan: FromPlanOption = None,
    output_predictions: OutputPredictionsOption = None,
    output_code: Annotated[Path | None, typer.Option("--output-code", help="Save generated script to file.")] = None,
    format: TableFormatOption = "table",
    quiet: QuietOption = False,
) -> None:
    """Run backtesting evaluation and report metrics and predictions."""
    with _error_handler(json_errors=format == "json"):
        llm_value = _resolve(llm, "SKFORECAST_AI_LLM", "llm.provider")
        base_url_value = _resolve(base_url, "SKFORECAST_AI_BASE_URL", "llm.base_url")
        api_key_value = _resolve(api_key, "SKFORECAST_AI_API_KEY", "llm.api_key")
        parsed_estimator_kwargs = _parse_estimator_kwargs(estimator_kwargs)
        parsed_interval = _parse_interval(interval)
        parsed_lags = _parse_lags(lags)
        parsed_window_features = _parse_window_features(window_features)
        decisions = _parse_decisions(
            metric             = metric,
            use_exog           = use_exog,
            differentiation    = differentiation,
            calendar_features  = calendar_features,
            target_transformer = target_transformer,
            dropna_from_series = dropna_from_series,
        )

        assistant = ForecastingAssistant(
            llm=llm_value,
            base_url=base_url_value,
            api_key=api_key_value,
        )

        if from_plan is not None:
            prof, plan_obj = _read_plan_bundle(from_plan)
            _check_steps_match_plan(steps, plan_obj)
            parsed_target = _parse_target(target) if target else None
            resolved_steps = plan_obj.steps
            resolved_date_column = date_column
            resolved_series_id = series_id_column
        else:
            if target is None or steps is None:
                raise InvalidInputError(
                    "--target and --steps are required "
                    "unless --from-plan is provided.",
                )
            parsed_target = _parse_target(target)
            resolved_steps = steps
            resolved_date_column = date_column
            resolved_series_id = series_id_column
            prof = None
            plan_obj = None

        with _spinner("Running backtest...", quiet):
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
                    interval=parsed_interval,
                    lags=parsed_lags,
                    window_features=parsed_window_features,
                    **decisions,
                )
            else:
                # Apply any override supplied alongside --from-plan on top of
                # the saved plan, re-deriving via refine_plan so coupled
                # fields stay consistent and no override is silently dropped.
                plan_overrides = _collect_plan_overrides(
                    forecaster=forecaster,
                    estimator=estimator,
                    estimator_kwargs=parsed_estimator_kwargs,
                    interval=parsed_interval,
                    lags=parsed_lags,
                    window_features=parsed_window_features,
                    reset_lags=_is_auto(lags),
                    reset_window_features=_is_auto(window_features),
                    decisions=decisions,
                )
                if plan_overrides:
                    plan_obj = assistant.refine_plan(
                        profile=prof, plan=plan_obj, **plan_overrides
                    )

            # Generate CV
            cv_kwargs = _collect_cv_overrides(
                initial_train_size=_parse_initial_train_size(initial_train_size),
                fold_stride=fold_stride,
                refit=refit,
                fixed_train_size=fixed_train_size,
                gap=gap,
                allow_incomplete_fold=allow_incomplete_fold,
            )

            cv = _create_cv_to_backtest(
                assistant,
                profile=prof,
                plan=plan_obj,
                prompt=prompt,
                **cv_kwargs,
            )

            # Run backtest, with the whole strategy result: it records the
            # options passed, which the result states.
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
            err_console.print(f"[green]Predictions written to:[/green] {output_predictions}")

        if output_code is not None:
            output_code.write_text(result.code)
            err_console.print(f"[green]Code written to:[/green] {output_code}")

        if format == "json":
            json_str = _result_to_json(result)
            print(json_str)
        else:
            _render_backtest_results(result)


def _parse_candidates(value: str | None) -> list[tuple[str, dict]] | None:
    """
    Parse the `--candidates` JSON string into a list of (name, config).

    Accepts a JSON array of two-element `[name, config]` pairs, or a JSON
    object mapping each name to its config dict.

    Parameters
    ----------
    value : str, None
        Raw `--candidates` JSON value. None selects the auto-built set.

    Returns
    -------
    candidates : list of tuple of (str, dict), None
        Parsed configurations, or None when input is None.
    """
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"Invalid --candidates JSON: {e}") from e

    if isinstance(parsed, dict):
        return [(str(name), config) for name, config in parsed.items()]
    if isinstance(parsed, list):
        candidates: list[tuple[str, dict]] = []
        for entry in parsed:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise typer.BadParameter(
                    "Each --candidates entry must be a [name, config] pair."
                )
            name, config = entry
            candidates.append((str(name), config))
        return candidates
    raise typer.BadParameter(
        "--candidates must be a JSON array of [name, config] pairs or an "
        "object mapping names to configs."
    )


def _render_comparison_results(result) -> None:
    """
    Print Rich tables summarizing the comparison leaderboard.

    Parameters
    ----------
    result : ComparisonResult
        Comparison result containing the ranked results and CV config.

    Returns
    -------
    None
    """
    console.print(render_explanation(result.explanation, title="Comparison Explanation"))
    console.print()
    console.print(render_dataframe(result.results, title="Comparison Results"))
    console.print()
    console.print(render_cv_config(result.cv_config))


@app.command()
def compare(
    data: Annotated[str, typer.Argument(help="Path or URL to CSV file.")],
    target: TargetOption = None,
    steps: StepsOption = None,
    date_column: DateColumnOption = None,
    series_id_column: SeriesIdColumnOption = None,
    candidates: Annotated[str | None, typer.Option("--candidates", help="Candidate configs as JSON array of [name, config] pairs; config keys: forecaster, estimator, estimator_kwargs, lags, window_features, use_exog, differentiation, calendar_features, target_transformer, dropna_from_series. When omitted, candidates are built from the profile.")] = None,
    metric: Annotated[str | None, typer.Option("--metric", help="Metric(s) to compute, comma-separated. The first ranks the table.")] = None,
    interval: IntervalOption = None,
    baseline: Annotated[bool, typer.Option("--baseline/--no-baseline", help="Add a seasonal naive baseline (ForecasterEquivalentDate) to the leaderboard. Single series only.")] = True,
    initial_train_size: InitialTrainSizeOption = None,
    fold_stride: FoldStrideOption = None,
    refit: RefitOption = None,
    fixed_train_size: FixedTrainSizeOption = None,
    gap: GapOption = None,
    allow_incomplete_fold: AllowIncompleteFoldOption = None,
    from_profile: FromProfileOption = None,
    output_code: Annotated[Path | None, typer.Option("--output-code", help="Save the winning configuration's script to file.")] = None,
    format: TableFormatOption = "table",
    quiet: QuietOption = False,
) -> None:
    """Compare several forecasters and report a ranked leaderboard."""
    with _error_handler(json_errors=format == "json"):
        assistant = ForecastingAssistant()
        parsed_interval = _parse_interval(interval)
        parsed_candidates = _parse_candidates(candidates)
        parsed_metric: str | list[str] | None = None
        if metric is not None:
            metric_list = [m.strip() for m in metric.split(",") if m.strip()]
            parsed_metric = metric_list[0] if len(metric_list) == 1 else metric_list

        if from_profile is not None:
            profile_data = _read_json_input(from_profile)
            prof = ForecastingProfile.model_validate(profile_data)
            parsed_target = _parse_target(target) if target else None
            resolved_date_column = date_column
            resolved_series_id = series_id_column
        else:
            if target is None:
                raise InvalidInputError(
                    "--target is required unless "
                    "--from-profile is provided.",
                    field = "target",
                )
            parsed_target = _parse_target(target)
            resolved_date_column = date_column
            resolved_series_id = series_id_column
            prof = None

        if steps is None:
            raise InvalidInputError(
                "--steps is required.",
                field = "steps",
            )

        with _spinner("Comparing forecasters...", quiet):
            if prof is None:
                prof = assistant.profile(
                    data=data,
                    target=parsed_target,
                    date_column=resolved_date_column,
                    series_id_column=resolved_series_id,
                )

            # The default plan of the profile gives a shared
            # cross-validation strategy; compare() re-plans each candidate
            # with the same cv.steps.
            default_plan = assistant.plan(profile=prof, steps=steps)

            cv_kwargs = _collect_cv_overrides(
                initial_train_size=_parse_initial_train_size(initial_train_size),
                fold_stride=fold_stride,
                refit=refit,
                fixed_train_size=fixed_train_size,
                gap=gap,
                allow_incomplete_fold=allow_incomplete_fold,
            )

            # The default plan only sizes the strategy: each candidate that
            # cannot run with it fails with its own reason.
            cv = _create_cv_to_backtest(
                assistant,
                profile=prof,
                plan=default_plan,
                **cv_kwargs,
            )

            result = assistant.compare(
                data=data,
                cv=cv,
                target=parsed_target,
                date_column=resolved_date_column,
                series_id_column=resolved_series_id,
                candidates=parsed_candidates,
                metric=parsed_metric,
                interval=parsed_interval,
                profile=prof,
                show_progress=(not quiet and format != "json"),
                baseline=baseline,
            )

        if output_code is not None:
            output_code.write_text(result.best_candidate.code)
            err_console.print(f"[green]Code written to:[/green] {output_code}")

        if format == "json":
            print(_result_to_json(result))
        else:
            _render_comparison_results(result)


@app.command()
def ask(
    prompt: Annotated[str, typer.Argument(help="Natural-language question about forecasting.")],
    data: Annotated[Path | None, typer.Option("--data", help="Path to a CSV file to profile; the LLM receives its profile, never the observations.")] = None,
    target: TargetOption = None,
    date_column: DateColumnOption = None,
    series_id_column: SeriesIdColumnOption = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Forecast horizon. With --data, also builds a plan so the question is answered about the plan.")] = None,
    from_profile: FromProfileOption = None,
    from_plan: FromPlanOption = None,
    llm: Annotated[str | None, typer.Option("--llm", help="LLM provider and model, e.g. 'openai:gpt-5.5'.")] = None,
    base_url: BaseUrlOption = None,
    api_key: ApiKeyOption = None,
    send_data_to_llm: Annotated[bool | None, typer.Option("--send-data-to-llm/--no-send-data-to-llm", help="Accepted for parity with the Python API; the CLI never sends observations to the LLM, whatever its value.")] = None,
    skills: Annotated[str | None, typer.Option("--skills", help="Comma-separated skill names to include, e.g. 'prediction-intervals'. The Skills page of the documentation lists them.")] = None,
    format: TextFormatOption = "text",
    quiet: QuietOption = False,
) -> None:
    """Ask a forecasting question using an LLM."""
    with _error_handler(json_errors=format == "json"):
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

        parsed_skills = [s.strip() for s in skills.split(",")] if skills else None

        # Resolve what the question is about: a saved bundle, a saved
        # profile, or a dataset profiled (and optionally planned) here.
        # Nothing is computed inside ask() itself.
        context = None
        if from_plan is not None:
            prof, plan_obj = _read_plan_bundle(from_plan)
            _check_steps_match_plan(steps, plan_obj)
            context = assistant.forecast_code(profile=prof, plan=plan_obj)
        elif from_profile is not None:
            context = ForecastingProfile.model_validate(_read_json_input(from_profile))
        elif data is not None:
            if target is None:
                raise InvalidInputError(
                    "--target is required with --data.",
                    field = "target",
                )
            with _spinner("Profiling...", quiet):
                prof = assistant.profile(
                    data=str(data), target=_parse_target(target),
                    date_column=date_column, series_id_column=series_id_column,
                )
            context = prof
            if steps is not None:
                plan_obj = assistant.plan(profile=prof, steps=steps)
                context = assistant.forecast_code(profile=prof, plan=plan_obj)

        with _spinner("Thinking...", quiet):
            result = assistant.ask(
                prompt=prompt,
                context=context,
                skills=parsed_skills,
            )

        if format == "json":
            print(_result_to_json(result))
        else:
            console.print(render_explanation(result.explanation, title="Assistant Response"))


@app.command(name="check-llm")
def check_llm(
    llm: Annotated[str | None, typer.Option("--llm", help="LLM provider and model, e.g. 'openai:gpt-5.5'.")] = None,
    base_url: BaseUrlOption = None,
    api_key: ApiKeyOption = None,
    test_call: Annotated[bool, typer.Option("--test-call", help="Send a one-line prompt to the model once the static checks pass.")] = False,
    format: TableFormatOption = "table",
    quiet: QuietOption = False,
) -> None:
    """Check how the LLM configuration resolves and whether it can be used."""
    with _error_handler(json_errors=format == "json"):
        llm_value = _resolve(llm, "SKFORECAST_AI_LLM", "llm.provider")
        base_url_value = _resolve(base_url, "SKFORECAST_AI_BASE_URL", "llm.base_url")
        api_key_value = _resolve(api_key, "SKFORECAST_AI_API_KEY", "llm.api_key")

        if llm_value is None:
            raise LLMRequiredError(method_name="check_llm")

        assistant = ForecastingAssistant(
            llm=llm_value,
            base_url=base_url_value,
            api_key=api_key_value,
        )

        with _spinner("Checking the LLM configuration...", quiet):
            result = assistant.check_llm(test_call=test_call)

        if format == "json":
            print(_result_to_json(result))
        else:
            console.print(render_llm_check(result))

        if not result.ok:
            raise typer.Exit(code=1)


@app.command(name="mcp")
def mcp_server(
    allow_dir: Annotated[Path | None, typer.Option("--allow-dir", help="Directory the server may read data from (required unless --allow-project-dir is given). Only absolute paths of CSV files inside it are accepted, also after resolving symbolic links.")] = None,
    allow_project_dir: Annotated[bool, typer.Option("--allow-project-dir", help="Use as the directory of --allow-dir the project of the session, read from the environment variable CLAUDE_PROJECT_DIR that Claude Code sets. The home directory and the root of a file system are rejected.")] = False,
    output_dir: Annotated[Path | None, typer.Option("--output-dir", help="Directory of the files the server writes; also its working directory. Default: a new temporary directory.")] = None,
    max_objects: Annotated[int, typer.Option("--max-objects", min=1, help="Most objects the server keeps; the least recently used ones are removed beyond it.")] = 256,
    max_memory_mb: Annotated[int, typer.Option("--max-memory-mb", min=1, help="Memory, in MB, the objects may take; the least recently used ones are removed beyond it.")] = 1024,
    max_file_mb: Annotated[int, typer.Option("--max-file-mb", min=0, help="Largest CSV file the server reads, in MB, checked before reading it; 0 for no limit.")] = 256,
    allow_model: Annotated[list[str] | None, typer.Option("--allow-model", help="Model ID prefix of a foundation model that the server may run although its license restricts commercial use, its weights are gated, its provider requires an account or skforecast gives no license information, e.g. google/timesfm-3.0 (repeatable). Other models run without it.")] = None,
) -> None:
    """Serve the deterministic workflow to MCP clients (coding agents) over stdio."""
    if (allow_dir is None) == (not allow_project_dir):
        raise typer.BadParameter(
            "Give one of '--allow-dir' or '--allow-project-dir'.",
            param_hint = "'--allow-dir'",
        )

    try:
        from .mcp._inputs import project_dir_from_environment
        from .mcp.server import run_server
    except ModuleNotFoundError as exc:
        # The packages of the `mcp` extra that the server imports: without
        # it `anyio`, which `mcp` installs, is the first one missing.
        if exc.name is None or exc.name.split(".")[0] not in ("mcp", "anyio"):
            raise
        err_console.print(
            "[red]Error:[/red] the MCP server needs the `mcp` extra: "
            "pip install \"skforecast-ai\\[mcp]\""
        )
        raise typer.Exit(code=1)

    # stdout carries the protocol: errors go to stderr.
    try:
        if allow_project_dir:
            allow_dir = Path(project_dir_from_environment())
        run_server(
            allow_dir     = allow_dir,
            output_dir    = output_dir,
            max_objects   = max_objects,
            max_memory_mb = max_memory_mb,
            max_file_mb   = max_file_mb,
            allow_models  = allow_model or (),
        )
    except InvalidInputError as exc:
        err_console.print(f"[red]Error:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app(prog_name="skforecast-ai")
