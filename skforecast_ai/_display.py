"""
Rich rendering helpers shared by the CLI and the result objects.

The functions in this module are *pure*: they build and return Rich
renderables (`Panel`, `Syntax`, `Table`, `Group`) without printing
anything. This lets a single set of renderers drive both the Typer CLI
(`skforecast_ai/cli.py`) and the automatic notebook/terminal display of the
result schemas (`skforecast_ai/schemas/results.py`), so styling never
diverges between them.

`DisplayMixin` wires those renderables into the Pydantic result classes,
providing `_repr_mimebundle_` (automatic rendering in Jupyter), the
`__rich_console__` protocol (`rich.print` / terminal), and an explicit
`show()` method.
"""

from __future__ import annotations
from numbers import Number
from typing import TYPE_CHECKING, Any

import pandas as pd
from rich.console import Console, Group
from rich.jupyter import JupyterMixin
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

if TYPE_CHECKING:
    from pandas import DataFrame
    from rich.console import ConsoleOptions, RenderableType, RenderResult

    from .schemas.plans import ForecastPlan
    from .schemas.profiles import ForecastingProfile

_CODE_THEME = "monokai"
_PANEL_BORDER = "color(214)"
_PREVIEW_ROWS = 5
_TABLE_KWARGS = {"show_lines": True}
_SPACER = ""


def _format_value(value: Any) -> str:
    """Format a value for display in a table.

    The stringified value is markup-escaped so that literal brackets in the
    data are not interpreted as Rich markup; the intentional style tags are
    added around the escaped text.
    """
    if isinstance(value, bool):
        return f"[{'green' if value else 'red'}]{value}[/]"
    if value is None:
        return "[dim]None[/]"
    return escape(str(value))


def _format_metric(value: Any) -> str:
    """Format a single metric cell for display.

    Returns `"N/A"` for missing values, a 4-decimal float for real numbers,
    and the markup-escaped string otherwise (so non-numeric cells do not raise
    on the `.4f` format).
    """
    if pd.isna(value):
        return "N/A"
    if isinstance(value, Number) and not isinstance(value, bool):
        return f"{value:.4f}"
    return escape(str(value))


def _format_cell(value: Any) -> str:
    """Format a single DataFrame cell for display.

    Returns `"N/A"` for missing values and a 4-decimal float for real floats
    (keeping integers untruncated), otherwise the markup-escaped string. This
    keeps prediction previews readable without altering integer or label
    columns.
    """
    if pd.isna(value):
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return escape(str(value))


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
    return Panel(syntax, title=title, title_align="center", border_style=_PANEL_BORDER)


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
        border_style=_PANEL_BORDER,
        padding=(1, 2),
        expand=True
    )


def render_dataframe(df: DataFrame, title: str = "Data") -> Table:
    """
    Render a pandas DataFrame as a Rich table.

    Long frames are truncated to the head and tail rows, mirroring the CLI
    behaviour, so very large prediction frames stay readable.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame to render.
    title : str, default 'Data'
        Table title.

    Returns
    -------
    table : rich.table.Table
        Populated data table.
    """
    n_rows = len(df)
    table_title = f"{title} ({n_rows} rows)" if n_rows > 2 * _PREVIEW_ROWS else title
    table = Table(title=table_title, **_TABLE_KWARGS)
    table.add_column("Index", style="dim")
    for col in df.columns:
        table.add_column(escape(str(col)), justify="right")

    def _add_row(idx: Any, row: Any) -> None:
        table.add_row(escape(str(idx)), *[_format_cell(x) for x in row])

    # Only truncate when the head+tail preview is actually shorter than the
    # full frame; otherwise render every row.
    if n_rows <= 2 * _PREVIEW_ROWS:
        for idx, row in df.iterrows():
            _add_row(idx, row)
    else:
        for idx, row in df.head(_PREVIEW_ROWS).iterrows():
            _add_row(idx, row)
        table.add_row("...", *["..."] * len(df.columns))
        for idx, row in df.tail(_PREVIEW_ROWS).iterrows():
            _add_row(idx, row)

    return table


def render_metrics(metrics: DataFrame, title: str = "Metrics") -> Table:
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
    table = Table(title=title, **_TABLE_KWARGS)

    series_col = next((c for c in ("series", "levels") if c in metrics.columns), None)
    metric_cols = [c for c in metrics.columns if c != series_col]

    if series_col is not None:
        table.add_column("Series", style="bold")
    for col in metric_cols:
        table.add_column(escape(str(col)), justify="right")

    for _, row in metrics.iterrows():
        values = [escape(str(row[series_col]))] if series_col is not None else []
        values.extend(_format_metric(row[col]) for col in metric_cols)
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
    table = Table(title="Cross-Validation Configuration", **_TABLE_KWARGS)
    table.add_column("Parameter")
    table.add_column("Value", justify="right")
    for key, value in cv_config.items():
        table.add_row(escape(str(key)), _format_value(value))
    return table


def render_profile(profile: ForecastingProfile) -> RenderableType:
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
    # Must stay local: _utils imports schemas, which imports .._display at
    # module level (DisplayMixin). Hoisting this would reintroduce that cycle.
    from ._utils import _display_n_observations

    dp = profile.data_profile

    table = Table(title="Dataset Profile", **_TABLE_KWARGS)
    table.add_column("Property")
    table.add_column("Value")
    table.add_row("Format", _format_value(dp.data_format))
    table.add_row("Series", _format_value(dp.n_series))
    table.add_row("Observations", _format_value(_display_n_observations(dp)))
    table.add_row("Frequency", _format_value(dp.frequency or "not detected"))
    table.add_row("Target", _format_value(dp.target))
    table.add_row("Exog columns", _format_value(", ".join(dp.exog_columns) if dp.exog_columns else "none"))

    missing_val = _format_value(dp.missing_target if dp.missing_target else "none")
    if dp.missing_target:
        missing_val = f"[bold yellow]{missing_val}[/bold yellow]"
    table.add_row("Missing target", missing_val)

    rec_table = Table(title="Recommendation", **_TABLE_KWARGS)
    rec_table.add_column("Property")
    rec_table.add_column("Value")
    rec_table.add_row("Task type", _format_value(profile.task_type))
    rec_table.add_row("Forecaster", _format_value(profile.forecaster))
    rec_table.add_row("Forecaster candidates", _format_value(", ".join(profile.forecaster_candidates)))
    rec_table.add_row("Estimator", _format_value(profile.estimator or "N/A"))
    rec_table.add_row("Estimator candidates", _format_value(", ".join(profile.estimator_candidates)))

    return Group(
        table,
        _SPACER,
        rec_table,
        _SPACER,
        render_explanation(profile.explanation, title="Explanation"),
    )


def render_plan(plan: ForecastPlan) -> RenderableType:
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
    table = Table(title="Forecast Plan", **_TABLE_KWARGS)
    table.add_column("Property")
    table.add_column("Value")
    table.add_row("Forecaster", _format_value(plan.forecaster))
    table.add_row("Estimator", _format_value(plan.estimator or "N/A"))
    table.add_row("Steps", _format_value(plan.steps))
    table.add_row("Frequency", _format_value(plan.frequency or "not set"))

    lags = plan.forecaster_kwargs.get("lags")
    table.add_row("Lags", _format_value(lags if lags is not None else "N/A"))

    table.add_row("Use exog", _format_value(plan.use_exog))
    table.add_row("Interval", _format_value(plan.interval if plan.interval else "none"))
    table.add_row("Interval method", _format_value(plan.interval_method or "N/A"))
    table.add_row("Primary metric", _format_value(plan.metric))

    if plan.preprocessing_steps:
        steps_str = "\n".join(
            f"  - {escape(str(s.action))}: {escape(str(s.reason))}"
            for s in plan.preprocessing_steps
        )
        table.add_row("Preprocessing", steps_str)
    else:
        table.add_row("Preprocessing", _format_value("none"))

    return Group(
        table,
        _SPACER,
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

    def show_code(self, console: Console | None = None) -> None:
        """
        Print the generated code with syntax highlighting to a console.

        Parameters
        ----------
        console : rich.console.Console, default None
            Console to print to. A new default console is created if omitted.

        Returns
        -------
        None
        """
        if hasattr(self, "code") and self.code is not None:
            (console or Console()).print(render_code(self.code))
        else:
            (console or Console()).print("No code available to display.")
