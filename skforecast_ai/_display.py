"""
Rich rendering helpers shared by the CLI and the result objects.

The functions in this module are *pure*: they build and return Rich
renderables (``Panel``, ``Syntax``, ``Table``, ``Group``) without printing
anything. This lets a single set of renderers drive both the Typer CLI
(`skforecast_ai/cli.py`) and the automatic notebook/terminal display of the
result schemas (`skforecast_ai/schemas/results.py`), so styling never
diverges between them.

`DisplayMixin` wires those renderables into the Pydantic result classes,
providing ``_repr_mimebundle_`` (automatic rendering in Jupyter), the
``__rich_console__`` protocol (``rich.print`` / terminal), and an explicit
``show()`` method.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

from rich.console import Console, Group
from rich.jupyter import JupyterMixin
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

if TYPE_CHECKING:
    from rich.console import ConsoleOptions, RenderableType, RenderResult

_CODE_THEME = "monokai"
_EXPLANATION_BORDER = "color(214)"
_PREVIEW_ROWS = 5
_PREVIEW_THRESHOLD = 10


def render_code(code: str, title: str | None = "Generated code") -> RenderableType:
    """
    Render Python source as syntax-highlighted code.

    Parameters
    ----------
    code : str
        Python source code to highlight.
    title : str, default 'Generated code'
        Panel title. If `None`, the bare `Syntax` is returned without a panel.

    Returns
    -------
    renderable : rich.console.RenderableType
        Syntax renderable, optionally wrapped in a titled panel.
    """
    syntax = Syntax(code, "python", theme=_CODE_THEME, word_wrap=True)
    if title is None:
        return syntax
    return Panel(syntax, title=title, title_align="center", border_style=_EXPLANATION_BORDER)


def render_explanation(text: str, title: str = "Explanation") -> Panel:
    """
    Render an explanation string as Markdown inside a titled panel.

    Parameters
    ----------
    text : str
        Explanation text (may contain Markdown).
    title : str, default 'Explanation'
        Panel title.

    Returns
    -------
    panel : rich.panel.Panel
        Panel wrapping the rendered Markdown.
    """
    return Panel(
        Markdown(text),
        title=title,
        title_align="center",
        border_style=_EXPLANATION_BORDER,
    )


def render_dataframe(df: Any, title: str = "Data") -> Panel:
    """
    Render a pandas DataFrame as a text preview inside a panel.

    Long frames are truncated to the head and tail rows, mirroring the CLI
    behaviour, so very large prediction frames stay readable.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame to render.
    title : str, default 'Data'
        Panel title.

    Returns
    -------
    panel : rich.panel.Panel
        Panel wrapping the (possibly truncated) string representation.
    """
    n_rows = len(df)
    if n_rows <= _PREVIEW_THRESHOLD:
        return Panel(df.to_string(), title=title, title_align="center")
    head = df.head(_PREVIEW_ROWS).to_string()
    tail = df.tail(_PREVIEW_ROWS).to_string(header=False)
    return Panel(
        f"{head}\n  ...\n{tail}",
        title=f"{title} ({n_rows} rows)",
        title_align="center",
    )


def render_metrics(metrics: Any, title: str = "Metrics") -> Table:
    """
    Render a metrics DataFrame as a Rich table.

    Handles both the `forecast()` layout (a `'series'` column plus metric
    columns) and the skforecast backtesting layout (metric columns only,
    optionally with a `'levels'` column).

    Parameters
    ----------
    metrics : pandas.DataFrame
        Metrics to render.
    title : str, default 'Metrics'
        Table title.

    Returns
    -------
    table : rich.table.Table
        Populated metrics table.
    """
    table = Table(title=title, show_lines=True)

    series_col = next((c for c in ("series", "levels") if c in metrics.columns), None)
    if series_col is not None:
        table.add_column("Series", style="bold")
        metric_cols = [c for c in metrics.columns if c != series_col]
        for col in metric_cols:
            table.add_column(col, justify="right")
        for _, row in metrics.iterrows():
            values = [str(row[series_col])]
            for col in metric_cols:
                val = row[col]
                values.append(f"{val:.4f}" if val is not None else "N/A")
            table.add_row(*values)
    else:
        for col in metrics.columns:
            table.add_column(col, justify="right")
        for _, row in metrics.iterrows():
            values = [
                f"{row[col]:.4f}" if row[col] is not None else "N/A"
                for col in metrics.columns
            ]
            table.add_row(*values)

    return table


def render_cv_config(cv_config: dict) -> Table:
    """
    Render a cross-validation configuration dict as a Rich table.

    Parameters
    ----------
    cv_config : dict
        Resolved `TimeSeriesFold` parameters.

    Returns
    -------
    table : rich.table.Table
        Two-column key/value table.
    """
    table = Table(title="Cross-Validation Configuration", show_lines=True)
    table.add_column("Parameter", style="bold")
    table.add_column("Value", justify="right")
    for key, value in cv_config.items():
        table.add_row(str(key), str(value))
    return table


def render_profile(profile: Any) -> RenderableType:
    """
    Render a `ForecastingProfile` as a group of tables and an explanation panel.       

    Parameters
    ----------
    profile : ForecastingProfile
        Profile object to render.

    Returns
    -------
    renderable : rich.console.RenderableType
        Group containing the dataset profile table, recommendation table, and
        the explanation panel.
    """
    from ._utils import _display_n_observations

    dp = profile.data_profile

    table = Table(title="Dataset Profile", show_lines=True)
    table.add_column("Property", style="bold")
    table.add_column("Value")
    table.add_row("Format", dp.data_format)
    table.add_row("Series", str(dp.n_series))
    table.add_row("Observations", str(_display_n_observations(dp)))
    table.add_row("Frequency", dp.frequency or "not detected")
    table.add_row("Target", str(dp.target))
    table.add_row("Exog columns", ", ".join(dp.exog_columns) if dp.exog_columns else "none")
    table.add_row("Missing target", str(dp.missing_target) if dp.missing_target else "none")

    rec_table = Table(title="Recommendation", show_lines=True)
    rec_table.add_column("Property", style="bold")
    rec_table.add_column("Value")
    rec_table.add_row("Task type", profile.task_type)
    rec_table.add_row("Forecaster", profile.forecaster)
    rec_table.add_row("Forecaster candidates", ", ".join(profile.forecaster_candidates))
    rec_table.add_row("Estimator", profile.estimator or "N/A")
    rec_table.add_row("Estimator candidates", ", ".join(profile.estimator_candidates))

    return Group(
        table,
        "",
        rec_table,
        "",
        render_explanation(profile.explanation, title="Explanation"),
    )


def render_plan(plan: Any) -> RenderableType:
    """
    Render a `ForecastPlan` as a table plus an explanation panel.

    Parameters
    ----------
    plan : ForecastPlan
        Plan object to render.

    Returns
    -------
    renderable : rich.console.RenderableType
        Group containing the plan table and the explanation panel.
    """
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
    table.add_row("Primary metric", plan.metric)

    if plan.preprocessing_steps:
        steps_str = "\n".join(
            f"  - {s.action}: {s.reason}" for s in plan.preprocessing_steps
        )
        table.add_row("Preprocessing", steps_str)
    else:
        table.add_row("Preprocessing", "none")

    return Group(
        table,
        "",
        render_explanation(plan.explanation, title="Plan Explanation"),
    )


class DisplayMixin(JupyterMixin):
    """
    Mixin that gives a result object rich display in notebooks and terminals.

    Subclasses must implement `__rich_console__`, yielding the Rich
    renderables that make up their display. This mixin then provides:

    - `_repr_mimebundle_` (inherited from `JupyterMixin`): automatic HTML
      rendering in Jupyter without CSS bleeding.
    - `show`: explicit printing to a `rich.console.Console`.

    The `__rich_console__` protocol additionally makes the object work with
    `rich.print(result)` and `console.print(result)` in a terminal.
    """

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError(
            f"{type(self).__name__} must implement __rich_console__"
        )

    def show(self, console: Console | None = None) -> None:
        """
        Print the rich representation to a console.

        Parameters
        ----------
        console : rich.console.Console, default None
            Console to print to. A new default console is created if omitted.

        Returns
        -------
        None
        """
        (console or Console()).print(self)
