################################################################################
#                                Display                                       #
#                                                                              #
# Rich rendering helpers shared by the CLI and the result objects              #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import base64
import html
import io
from numbers import Number
from typing import TYPE_CHECKING, Any
import pandas as pd
from rich import get_console
from rich.console import Console, Group
from rich.jupyter import JupyterMixin
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pandas import DataFrame
    from rich.console import ConsoleOptions, RenderableType, RenderResult

    from .schemas.plans import ForecastPlan
    from .schemas.profiles import ForecastingProfile

_CODE_THEME = "monokai"
_PANEL_BORDER = "color(214)"
_PREVIEW_ROWS = 5
_TABLE_KWARGS = {"show_lines": True}
_SPACER = ""
MAX_WIDTH = 90


def _default_console() -> Console:
    """A fresh `Console`, capped at `MAX_WIDTH` only when running in Jupyter.

    A real terminal keeps Rich's own auto-detected width; Jupyter kernels
    otherwise default to a fixed 115 columns (`rich.console.
    JUPYTER_DEFAULT_COLUMNS`), well past `MAX_WIDTH`.
    """
    console = Console()
    if console.is_jupyter:
        console.width = min(console.width, MAX_WIDTH)
    return console


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
    if pd.api.types.is_float(value):
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


# JavaScript for the notebook copy button. Defined once on `window` (guarded so
# repeated cell executions do not redefine it) and shared by every rendered
# block. The raw code is passed as a base64 `data-code` attribute so that
# arbitrary source (quotes, newlines, unicode) survives HTML attribute
# normalization and is decoded back to exact bytes before copying.
_COPY_BUTTON_SCRIPT = """
if (!window.skfCopyCode) {
  window.skfCopyCode = function (btn) {
    function fallback(text, done) {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try { document.execCommand('copy'); } catch (e) { /* ignore */ }
      document.body.removeChild(ta);
      done();
    }
    var bin = atob(btn.getAttribute('data-code'));
    var bytes = Uint8Array.from(bin, function (c) { return c.charCodeAt(0); });
    var text = new TextDecoder('utf-8').decode(bytes);
    var done = function () {
      var original = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(function () { btn.textContent = original; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        fallback(text, done);
      });
    } else {
      fallback(text, done);
    }
  };
}
"""


def _highlighted_code_html(code: str) -> str:
    """
    Return syntax-highlighted HTML spans for `code` (no wrapping element).

    The code is rendered with the same Rich `Syntax` highlighter used by the
    terminal panel and exported to a self-contained HTML fragment with inline
    styles, so it renders identically regardless of the notebook front-end.
    Lines longer than `MAX_WIDTH` are wrapped so the block never overflows.
    """
    console = Console(
        record=True,
        width=MAX_WIDTH,
        file=io.StringIO(),
        force_jupyter=False,
        force_terminal=True,
    )
    console.print(
        Syntax(
            code.rstrip("\n"),
            "python",
            theme=_CODE_THEME,
            word_wrap=True,
        )
    )
    inner = console.export_html(inline_styles=True, code_format="{code}")
    return inner.rstrip("\n")


def render_code_html(code: str, title: str = "Generated code") -> str:
    """
    Render Python source as an HTML block with a one-click copy button.

    Intended for notebook front-ends. The rendered block shows
    syntax-highlighted code without any surrounding border characters, so a
    manual selection copies clean source. The copy button copies the exact
    original code (real line breaks preserved) via the browser clipboard API.

    Parameters
    ----------
    code : str
        Python source code to display.
    title : str, default 'Generated code'
        Header label shown above the code block.

    Returns
    -------
    html : str
        Self-contained HTML fragment (styles inlined) for display in a
        notebook via `IPython.display.HTML`.
    """
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    inner = _highlighted_code_html(code)
    title_html = html.escape(title)
    return (
        '<div style="border:1px solid #444;border-radius:6px;overflow:hidden;'
        'margin:4px 0;font-family:Menlo,\'DejaVu Sans Mono\',consolas,'
        "'Courier New',monospace\">"
        '<div style="display:flex;justify-content:space-between;'
        "align-items:center;background:#1e1e1e;padding:6px 10px;"
        'border-bottom:1px solid #444;">'
        f'<span style="color:#ffaf00;font-weight:600;font-size:1em;">'
        f"{title_html}</span>"
        '<button type="button" onclick="skfCopyCode(this)" '
        f'data-code="{encoded}" '
        'style="cursor:pointer;border:1px solid #666;border-radius:4px;'
        "background:#2d2d2d;color:#eee;font-size:0.95em;padding:3px 12px;"
        'font-family:inherit;">Copy</button>'
        "</div>"
        '<pre style="margin:0;padding:10px;background:#272822;color:#f8f8f2;'
        'overflow-x:auto;white-space:pre;line-height:1.4;">'
        f"{inner}</pre>"
        "</div>"
        f"<script>{_COPY_BUTTON_SCRIPT}</script>"
    )


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
    rec_table.add_row(
        "Forecaster candidates",
        _format_value(", ".join(profile.forecaster_candidates) if profile.forecaster_candidates else "none"),
    )
    rec_table.add_row("Estimator", _format_value(profile.estimator or "N/A"))
    rec_table.add_row(
        "Estimator candidates",
        _format_value(", ".join(profile.estimator_candidates) if profile.estimator_candidates else "none"),
    )

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

    refined = set(plan.llm_refined_fields)
    llm_tag = "  [magenta](LLM-suggested)[/]"

    lags = plan.forecaster_kwargs.get("lags")
    lags_value = _format_value(lags if lags is not None else "N/A")
    if "lags" in refined:
        lags_value += llm_tag
    table.add_row("Lags", lags_value)

    window_features = plan.forecaster_kwargs.get("window_features")
    window_value = _format_value(
        window_features if window_features is not None else "N/A"
    )
    if "window_features" in refined:
        window_value += llm_tag
    table.add_row("Window features", window_value)

    calendar_features = plan.forecaster_kwargs.get("calendar_features")
    if isinstance(calendar_features, dict) and calendar_features.get("features"):
        features = calendar_features["features"]
        encoding = calendar_features.get("encoding") or "raw ordinal"
        calendar_value = _format_value(f"{features} ({encoding} encoding)")
    else:
        calendar_value = _format_value("none")
    table.add_row("Calendar features", calendar_value)

    table.add_row("Use exog", _format_value(plan.use_exog))
    table.add_row("Interval", _format_value(plan.interval if plan.interval else "none"))
    table.add_row("Interval method", _format_value(plan.interval_method or "N/A"))
    table.add_row("Primary metric", _format_value(plan.metric))

    if plan.preprocessing_steps:
        steps_str = "\n".join(
            f"  - {escape(str(s.action))}: {escape(str(s.reason))}"
            + ("" if s.blocking else " [dim](optional)[/]")
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


class _BodyOnly(JupyterMixin):
    """Wraps a `DisplayMixin` instance to render only its non-code body."""

    def __init__(self, owner: DisplayMixin) -> None:
        self._owner = owner

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield from self._owner._rich_body(console, options)


class DisplayMixin(JupyterMixin):
    """
    Mixin that gives a result object rich display in notebooks and terminals.

    Subclasses must implement `_rich_body`, yielding the Rich renderables
    that make up their display, excluding the generated-code block. This
    mixin then provides:

    - `__rich_console__`: yields the subclass's body followed by the code
      block (via `render_code`), if the object has a non-`None` `code`
      attribute. This makes the object work with `rich.print(result)` and
      `console.print(result)` in a terminal.
    - `_repr_mimebundle_`: automatic HTML rendering in Jupyter without CSS
      bleeding, capped at `MAX_WIDTH` (overrides `JupyterMixin`, which
      otherwise renders at the ambient console's full width, which some
      notebook front-ends report as much wider than a typical terminal).
      The code block, if present, is rendered with the same copy-button HTML
      `show_code` uses, instead of a plain Rich panel.
    - `show`: explicit printing to a `rich.console.Console`.
    """

    def _rich_body(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError(
            f"{type(self).__name__} must implement _rich_body"
        )

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield from self._rich_body(console, options)
        code = getattr(self, "code", None)
        if code is not None:
            yield render_code(code)

    def _repr_mimebundle_(
        self, include: Sequence[str] | None, exclude: Sequence[str] | None, **kwargs: Any
    ) -> dict[str, str]:
        console = get_console()
        original_width = console._width
        console.width = min(console.width, MAX_WIDTH)
        try:
            bundle = super()._repr_mimebundle_(include, exclude, **kwargs)
            code = getattr(self, "code", None)
            if code is not None and "text/html" in bundle:
                body_bundle = _BodyOnly(self)._repr_mimebundle_(["text/html"], [])
                bundle = {
                    **bundle,
                    "text/html": body_bundle.get("text/html", "") + render_code_html(code),
                }
            return bundle
        finally:
            console.width = original_width

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
        (console or _default_console()).print(self)

    def show_code(self, console: Console | None = None) -> None:
        """
        Print the generated code with syntax highlighting to a console.

        In a notebook front-end the code is displayed as an HTML block with a
        one-click copy button that copies clean source (no border characters,
        real line breaks preserved). In a terminal the code is printed inside
        the usual syntax-highlighted panel.

        Parameters
        ----------
        console : rich.console.Console, default None
            Console to print to. A new default console is created if omitted.

        Returns
        -------
        None
        """
        target = console or _default_console()
        if not (hasattr(self, "code") and self.code is not None):
            target.print("No code available to display.")
            return
        if target.is_jupyter:
            try:
                from IPython.display import HTML, display

                display(HTML(render_code_html(self.code)))
                return
            except ImportError:
                pass
        target.print(render_code(self.code))

    def show_explanation(self, console: Console | None = None) -> None:
        """
        Print the explanation with Markdown formatting to a console.

        Parameters
        ----------
        console : rich.console.Console, default None
            Console to print to. A new default console is created if omitted.

        Returns
        -------
        None
        """
        if hasattr(self, "explanation") and self.explanation is not None:
            (console or _default_console()).print(render_explanation(self.explanation))
        else:
            (console or _default_console()).print("No explanation available to display.")
