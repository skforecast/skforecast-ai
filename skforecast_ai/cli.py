"""Typer CLI for skforecast-ai: inspect, recommend, and generate-code."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .assistant import ForecastingAssistant

app = typer.Typer(
    name="skforecast-ai",
    help="Deterministic forecasting assistant powered by skforecast.",
    no_args_is_help=True,
)

console = Console()


# TODO: Create when the assistant is ready
