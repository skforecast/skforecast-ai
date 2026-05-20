"""Typer CLI for skforecast-ai: inspect, recommend, and generate-code."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .assistant import ForecastingAssistant
from .exceptions import ForecastExecutionError, LLMRequiredError

app = typer.Typer(
    name="skforecast-ai",
    help="Deterministic forecasting assistant powered by skforecast.",
    no_args_is_help=True,
)

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_target(target_str: str) -> str | list[str]:
    """Split comma-separated target names; return str if single value."""
    parts = [t.strip() for t in target_str.split(",")]
    return parts if len(parts) > 1 else parts[0]


def _parse_interval(interval_str: str | None) -> list[int] | None:
    """Parse 'lower,upper' interval string into [int, int] or None."""
    if interval_str is None:
        return None
    parts = [int(x.strip()) for x in interval_str.split(",")]
    if len(parts) != 2:
        raise typer.BadParameter(
            "Interval must be two comma-separated integers, e.g. '10,90'."
        )
    return parts


def _write_output(content: str, output: Path | None) -> None:
    """Write content to file or stdout."""
    if output is not None:
        output.write_text(content)
        console.print(f"[green]Output written to:[/green] {output}")
    else:
        print(content)


@contextlib.contextmanager
def _error_handler():
    """Catch known exceptions and print user-friendly errors."""
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
    except (ValueError, KeyError, TypeError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


def _render_profile_table(profile) -> None:
    """Print a Rich table summarizing the ForecastingProfile."""
    dp = profile.data_profile

    table = Table(title="Dataset Profile", show_lines=True)
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Format", dp.data_format)
    table.add_row("Series", str(dp.n_series))
    table.add_row("Observations", str(dp.n_observations))
    table.add_row("Frequency", dp.frequency or "not detected")
    table.add_row("Target", str(dp.target))
    table.add_row("Exog columns", ", ".join(dp.exog_columns) if dp.exog_columns else "none")
    table.add_row("Missing target", str(dp.missing_target) if dp.missing_target else "none")

    console.print(table)
    console.print()

    rec_table = Table(title="Recommendation", show_lines=True)
    rec_table.add_column("Property", style="bold")
    rec_table.add_column("Value")

    rec_table.add_row("Task type", profile.task_type)
    rec_table.add_row("Forecaster", profile.forecaster)
    rec_table.add_row("Forecaster candidates", ", ".join(profile.forecaster_candidates))
    rec_table.add_row("Estimator", profile.estimator or "N/A")
    rec_table.add_row("Estimator candidates", ", ".join(profile.estimator_candidates))

    console.print(rec_table)
    console.print()
    console.print(Panel(profile.explanation, title="Explanation"))


def _render_plan_panel(plan) -> None:
    """Print a Rich panel summarizing the ForecastPlan."""
    table = Table(title="Forecast Plan", show_lines=True)
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Forecaster", plan.forecaster)
    table.add_row("Estimator", plan.estimator or "N/A")
    table.add_row("Steps", str(plan.steps))
    table.add_row("Frequency", plan.frequency or "not set")

    lags = plan.forecaster_kwargs.get("lags")
    table.add_row("Lags", str(lags) if lags is not None else "N/A")

    table.add_row("Use exog", str(plan.use_exog))
    table.add_row("Interval", str(plan.interval) if plan.interval else "none")
    table.add_row("Interval method", plan.interval_method or "N/A")

    if plan.preprocessing_steps:
        steps_str = "\n".join(
            f"  - {s.action}: {s.reason}" for s in plan.preprocessing_steps
        )
        table.add_row("Preprocessing", steps_str)
    else:
        table.add_row("Preprocessing", "none")

    console.print(table)
    console.print()
    console.print(Panel(plan.explanation, title="Plan Explanation"))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def profile(
    data: Annotated[str, typer.Argument(help="Path or URL to CSV file.")],
    target: Annotated[str, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")],
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id: Annotated[str | None, typer.Option("--series-id", "-s", help="Series identifier column.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: table or json.")] = "table",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write output to file.")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Profile a dataset and recommend a forecaster + estimator."""
    with _error_handler():
        assistant = ForecastingAssistant()
        parsed_target = _parse_target(target)

        if quiet:
            result = assistant.profile(
                data=data, target=parsed_target, date_column=date_column,
                series_id_column=series_id,
            )
        else:
            with console.status("Profiling dataset..."):
                result = assistant.profile(
                    data=data, target=parsed_target, date_column=date_column,
                    series_id_column=series_id,
                )

        if format == "json":
            json_str = result.model_dump_json(indent=2)
            _write_output(json_str, output)
        else:
            _render_profile_table(result)


@app.command()
def plan(
    data: Annotated[str, typer.Argument(help="Path or URL to CSV file.")],
    target: Annotated[str, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")],
    steps: Annotated[int, typer.Option("--steps", help="Forecast horizon (number of steps).")],
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id: Annotated[str | None, typer.Option("--series-id", "-s", help="Series identifier column.")] = None,
    forecaster: Annotated[str | None, typer.Option("--forecaster", help="Override forecaster class.")] = None,
    estimator: Annotated[str | None, typer.Option("--estimator", help="Override estimator class.")] = None,
    interval: Annotated[str | None, typer.Option("--interval", help="Prediction interval, e.g. '10,90'.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: table or json.")] = "table",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write output to file.")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Generate a detailed forecasting plan from a dataset."""
    with _error_handler():
        assistant = ForecastingAssistant()
        parsed_target = _parse_target(target)
        parsed_interval = _parse_interval(interval)

        if quiet:
            prof = assistant.profile(
                data=data, target=parsed_target, date_column=date_column,
                series_id_column=series_id,
            )
            result = assistant.generate_plan(
                profile=prof, steps=steps, forecaster=forecaster,
                estimator=estimator, interval=parsed_interval,
            )
        else:
            with console.status("Profiling and planning..."):
                prof = assistant.profile(
                    data=data, target=parsed_target, date_column=date_column,
                    series_id_column=series_id,
                )
                result = assistant.generate_plan(
                    profile=prof, steps=steps, forecaster=forecaster,
                    estimator=estimator, interval=parsed_interval,
                )

        if format == "json":
            json_str = result.model_dump_json(indent=2)
            _write_output(json_str, output)
        else:
            _render_plan_panel(result)


@app.command(name="generate-code")
def generate_code(
    data: Annotated[str, typer.Argument(help="Path or URL to CSV file.")],
    target: Annotated[str, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")],
    steps: Annotated[int, typer.Option("--steps", help="Forecast horizon (number of steps).")],
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id: Annotated[str | None, typer.Option("--series-id", "-s", help="Series identifier column.")] = None,
    forecaster: Annotated[str | None, typer.Option("--forecaster", help="Override forecaster class.")] = None,
    estimator: Annotated[str | None, typer.Option("--estimator", help="Override estimator class.")] = None,
    interval: Annotated[str | None, typer.Option("--interval", help="Prediction interval, e.g. '10,90'.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: code or json.")] = "code",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write output to file.")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Generate a complete Python forecasting script."""
    with _error_handler():
        assistant = ForecastingAssistant()
        parsed_target = _parse_target(target)
        parsed_interval = _parse_interval(interval)

        if quiet:
            result = assistant.generate_code(
                data=data, target=parsed_target, steps=steps,
                date_column=date_column, series_id_column=series_id,
                forecaster=forecaster, estimator=estimator,
                interval=parsed_interval,
            )
        else:
            with console.status("Generating code..."):
                result = assistant.generate_code(
                    data=data, target=parsed_target, steps=steps,
                    date_column=date_column, series_id_column=series_id,
                    forecaster=forecaster, estimator=estimator,
                    interval=parsed_interval,
                )

        if format == "json":
            json_str = result.model_dump_json(indent=2)
            _write_output(json_str, output)
        else:
            if output is not None:
                output.write_text(result.code)
                console.print(f"[green]Code written to:[/green] {output}")
            else:
                syntax = Syntax(result.code, "python", theme="monokai")
                console.print(syntax)


def _render_forecast_results(result) -> None:
    """Print a Rich table summarizing forecast metrics and predictions."""
    metrics = result.metrics

    table = Table(title="Forecast Metrics", show_lines=True)
    table.add_column("Series", style="bold")
    table.add_column("MAE", justify="right")
    table.add_column("MSE", justify="right")
    table.add_column("MASE", justify="right")

    for _, row in metrics.iterrows():
        table.add_row(
            str(row["series"]),
            f"{row['MAE']:.4f}",
            f"{row['MSE']:.4f}",
            f"{row['MASE']:.4f}",
        )

    console.print(table)
    console.print()

    predictions = result.predictions
    n_rows = len(predictions)
    if n_rows <= 10:
        console.print(Panel(predictions.to_string(), title="Predictions"))
    else:
        head = predictions.head(5).to_string()
        tail = predictions.tail(5).to_string(header=False)
        console.print(Panel(
            f"{head}\n  ...\n{tail}",
            title=f"Predictions ({n_rows} rows)",
        ))


def _forecast_result_to_json(result) -> str:
    """Serialize ForecastResult to JSON with DataFrame fields as records."""
    data = {
        "profile": result.profile.model_dump(mode="json"),
        "plan": result.plan.model_dump(mode="json"),
        "code": result.code,
        "metrics": result.metrics.to_dict(orient="records"),
        "predictions": result.predictions.reset_index().to_dict(orient="records"),
    }
    if result.intervals is not None:
        data["intervals"] = result.intervals.reset_index().to_dict(orient="records")
    else:
        data["intervals"] = None
    return json.dumps(data, indent=2, default=str)


@app.command()
def forecast(
    data: Annotated[str, typer.Argument(help="Path to CSV file.")],
    target: Annotated[str, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")],
    steps: Annotated[int, typer.Option("--steps", help="Forecast horizon (number of steps).")],
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id: Annotated[str | None, typer.Option("--series-id", "-s", help="Series identifier column.")] = None,
    forecaster: Annotated[str | None, typer.Option("--forecaster", help="Override forecaster class.")] = None,
    estimator: Annotated[str | None, typer.Option("--estimator", help="Override estimator class.")] = None,
    interval: Annotated[str | None, typer.Option("--interval", help="Prediction interval, e.g. '10,90'.")] = None,
    exog_future: Annotated[Path | None, typer.Option("--exog-future", help="CSV with future exogenous variables.")] = None,
    output_predictions: Annotated[Path | None, typer.Option("--output-predictions", help="Save predictions as CSV.")] = None,
    output_code: Annotated[Path | None, typer.Option("--output-code", help="Save generated script to file.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: table or json.")] = "table",
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Run end-to-end forecasting and report metrics + predictions."""
    with _error_handler():
        assistant = ForecastingAssistant()
        parsed_target = _parse_target(target)
        parsed_interval = _parse_interval(interval)

        exog_future_df = None
        if exog_future is not None:
            if not exog_future.is_file():
                raise FileNotFoundError(
                    f"Exog future CSV not found: '{exog_future}'."
                )
            exog_future_df = pd.read_csv(exog_future)

        if quiet:
            result = assistant.forecast(
                data=data, target=parsed_target, steps=steps,
                date_column=date_column, series_id_column=series_id,
                forecaster=forecaster, estimator=estimator,
                interval=parsed_interval, exog_future=exog_future_df,
            )
        else:
            with console.status("Running forecast..."):
                result = assistant.forecast(
                    data=data, target=parsed_target, steps=steps,
                    date_column=date_column, series_id_column=series_id,
                    forecaster=forecaster, estimator=estimator,
                    interval=parsed_interval, exog_future=exog_future_df,
                )

        if output_predictions is not None:
            preds = result.predictions
            if result.intervals is not None:
                preds = result.intervals
            preds.to_csv(output_predictions)
            console.print(f"[green]Predictions written to:[/green] {output_predictions}")

        if output_code is not None:
            output_code.write_text(result.code)
            console.print(f"[green]Code written to:[/green] {output_code}")

        if format == "json":
            json_str = _forecast_result_to_json(result)
            print(json_str)
        else:
            _render_forecast_results(result)


@app.command()
def ask(
    prompt: Annotated[str, typer.Argument(help="Natural-language question about forecasting.")],
    data: Annotated[Path | None, typer.Option("--data", help="Path to CSV file for context.")] = None,
    target: Annotated[str | None, typer.Option("--target", "-t", help="Target column name(s), comma-separated.")] = None,
    date_column: Annotated[str | None, typer.Option("--date-column", "-d", help="Date/timestamp column.")] = None,
    series_id: Annotated[str | None, typer.Option("--series-id", "-s", help="Series identifier column.")] = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Forecast horizon (required when --data is provided).")] = None,
    llm: Annotated[str | None, typer.Option("--llm", help="LLM provider, e.g. 'openai:gpt-4o-mini'.")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Custom LLM endpoint URL.")] = None,
    send_data_to_llm: Annotated[bool, typer.Option("--send-data-to-llm", help="Allow sending raw data to the LLM.")] = False,
    skills: Annotated[str | None, typer.Option("--skills", help="Comma-separated skill names to include.")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: text or json.")] = "text",
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress spinners.")] = False,
) -> None:
    """Ask a forecasting question using an LLM."""
    with _error_handler():
        llm_value = llm or os.environ.get("SKFORECAST_AI_LLM")
        base_url_value = base_url or os.environ.get("SKFORECAST_AI_BASE_URL")

        assistant = ForecastingAssistant(
            llm=llm_value,
            base_url=base_url_value,
            send_data_to_llm=send_data_to_llm,
        )

        parsed_target = _parse_target(target) if target else None
        parsed_skills = [s.strip() for s in skills.split(",")] if skills else None

        data_path = str(data) if data is not None else None

        if quiet:
            result = assistant.ask(
                prompt=prompt,
                data=data_path,
                target=parsed_target,
                date_column=date_column,
                series_id_column=series_id,
                steps=steps,
                skills=parsed_skills,
            )
        else:
            with console.status("Thinking..."):
                result = assistant.ask(
                    prompt=prompt,
                    data=data_path,
                    target=parsed_target,
                    date_column=date_column,
                    series_id_column=series_id,
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
            console.print(Markdown(result.explanation))
