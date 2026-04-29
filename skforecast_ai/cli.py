"""Typer CLI for skforecast-ai: inspect, recommend, and generate-code."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .generation.code_templates import generate_code
from .profiling.data_profile import create_data_profile
from .recommendation.forecaster_selection import recommend_plan

app = typer.Typer(
    name="skforecast-ai",
    help="Deterministic forecasting assistant powered by skforecast.",
    no_args_is_help=True,
)

console = Console()


def _print_profile(profile) -> None:
    """Print a DataProfile as a Rich table."""
    table = Table(title="Data Profile")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Target", profile.target)
    table.add_row("Observations", str(profile.n_observations))
    table.add_row("Series", str(profile.n_series))
    table.add_row("Index type", profile.index_type)
    table.add_row("Frequency", profile.frequency or "Unknown")
    table.add_row("Date column", profile.date_column or "—")
    table.add_row("Series ID column", profile.series_id_column or "—")
    table.add_row("Exog columns", ", ".join(profile.exog_columns) or "None")
    table.add_row("Categorical exog", ", ".join(profile.categorical_exog) or "None")
    table.add_row("Seasonalities", str(profile.inferred_seasonalities) or "None")

    if profile.missing_values:
        missing_str = ", ".join(
            f"{col}: {count}" for col, count in profile.missing_values.items()
        )
        table.add_row("Missing values", missing_str)
    else:
        table.add_row("Missing values", "None")

    if profile.warnings:
        table.add_row("Warnings", "\n".join(profile.warnings))

    console.print(table)


def _print_plan(plan) -> None:
    """Print a ForecastPlan as a Rich table."""
    table = Table(title="Forecast Plan")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Task type", plan.task_type)
    table.add_row("Forecaster", plan.forecaster)
    table.add_row("Estimator", plan.estimator or "—")
    table.add_row("Horizon", str(plan.horizon))
    table.add_row("Frequency", plan.frequency or "Unknown")
    table.add_row("Lags", str(plan.lags))
    table.add_row("Metric", plan.metric)
    table.add_row("Backtesting", plan.backtesting_strategy)
    table.add_row("Interval method", plan.interval_method or "—")
    table.add_row("Use exog", str(plan.use_exog))

    if plan.data_requirements:
        table.add_row("Data requirements", "\n".join(plan.data_requirements))

    if plan.warnings:
        table.add_row("Warnings", "\n".join(plan.warnings))

    table.add_row("Rationale", plan.rationale)

    console.print(table)


@app.command()
def inspect(
    data_path: Annotated[Path, typer.Argument(help="Path to the CSV file.")],
    target: Annotated[str, typer.Option("--target", help="Target column name.")],
    date: Annotated[
        str | None, typer.Option("--date", help="Date column name.")
    ] = None,
    series_id: Annotated[
        str | None, typer.Option("--series-id", help="Series ID column name.")
    ] = None,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output as JSON.")
    ] = False,
) -> None:
    """Profile a time series dataset."""
    try:
        profile = create_data_profile(
            data=data_path,
            target=target,
            date_column=date,
            series_id_column=series_id,
        )
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] File not found: {data_path}")
        raise typer.Exit(code=1)
    except (ValueError, KeyError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]Unexpected error:[/red] {exc}")
        raise typer.Exit(code=2)

    if output_json:
        typer.echo(profile.model_dump_json(indent=2))
    else:
        _print_profile(profile)


@app.command()
def recommend(
    data_path: Annotated[Path, typer.Argument(help="Path to the CSV file.")],
    target: Annotated[str, typer.Option("--target", help="Target column name.")],
    date: Annotated[
        str | None, typer.Option("--date", help="Date column name.")
    ] = None,
    series_id: Annotated[
        str | None, typer.Option("--series-id", help="Series ID column name.")
    ] = None,
    horizon: Annotated[
        int, typer.Option("--horizon", help="Forecast horizon (steps ahead).")
    ] = 10,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output as JSON.")
    ] = False,
) -> None:
    """Profile a dataset and generate a forecasting plan."""
    try:
        profile = create_data_profile(
            data=data_path,
            target=target,
            date_column=date,
            series_id_column=series_id,
        )
        plan = recommend_plan(profile=profile, horizon=horizon)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] File not found: {data_path}")
        raise typer.Exit(code=1)
    except (ValueError, KeyError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]Unexpected error:[/red] {exc}")
        raise typer.Exit(code=2)

    if output_json:
        typer.echo(plan.model_dump_json(indent=2))
    else:
        _print_plan(plan)


@app.command("generate-code")
def generate_code_cmd(
    data_path: Annotated[Path, typer.Argument(help="Path to the CSV file.")],
    target: Annotated[str, typer.Option("--target", help="Target column name.")],
    date: Annotated[
        str | None, typer.Option("--date", help="Date column name.")
    ] = None,
    series_id: Annotated[
        str | None, typer.Option("--series-id", help="Series ID column name.")
    ] = None,
    horizon: Annotated[
        int, typer.Option("--horizon", help="Forecast horizon (steps ahead).")
    ] = 10,
    output: Annotated[
        Path | None, typer.Option("--output", help="Write code to this file.")
    ] = None,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output plan and code as JSON.")
    ] = False,
) -> None:
    """Profile, recommend, and generate forecasting code."""
    try:
        profile = create_data_profile(
            data=data_path,
            target=target,
            date_column=date,
            series_id_column=series_id,
        )
        plan = recommend_plan(profile=profile, horizon=horizon)
        code = generate_code(plan=plan, profile=profile, data_path=str(data_path))
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] File not found: {data_path}")
        raise typer.Exit(code=1)
    except (ValueError, KeyError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]Unexpected error:[/red] {exc}")
        raise typer.Exit(code=2)

    if output_json:
        result = {"plan": plan.model_dump(), "code": code}
        typer.echo(json.dumps(result, indent=2))
    elif output:
        output.write_text(code)
        console.print(f"[green]Code written to:[/green] {output}")
    else:
        typer.echo(code)
