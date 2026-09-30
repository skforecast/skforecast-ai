"""
Generate the "How it works" diagram of the README and the user guides.

Writes two files from a single layout so they can never drift apart:

- `docs/img/how-it-works.svg`: light theme.
- `docs/img/how-it-works-dark.svg`: dark theme.

The two paths are drawn row by row so the difference is visible at a glance:
where the step-by-step path calls `profile()` and `plan()`, the fast path runs
them inside the call; where the step-by-step path builds the cross-validation
strategy with `create_cv()`, the fast path takes a `TimeSeriesFold`. Below
them, `compare()` for model selection and `ask()` for the LLM explanations.

The README picks a variant with `<picture>` and `prefers-color-scheme`; the
documentation with the `#only-light` and `#only-dark` suffixes of Material for
MkDocs.

Usage (from the repository root):

    python tools/docs/how_it_works/make_how_it_works.py
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = ROOT / "docs" / "img"

WIDTH = 1040
HEIGHT = 806
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

PALETTES = {
    "light": {
        "panel":       "#f6f8fa",
        "border":      "#d0d7de",
        "surface":     "#ffffff",
        "ink":         "#24292f",
        "muted":       "#57606a",
        "on_header":   "#ffffff",
        "fast":        "#0969da",
        "fast_fill":   "#dbeafe",
        "step":        "#1a7f37",
        "step_fill":   "#dcfce7",
        "cmp":         "#bc4c00",
        "cmp_bg":      "#fff4ed",
        "cmp_fill":    "#ffe0cc",
        "llm":         "#8250df",
        "llm_bg":      "#faf5ff",
    },
    "dark": {
        "panel":       "#161b22",
        "border":      "#30363d",
        "surface":     "#0d1117",
        "ink":         "#e6edf3",
        "muted":       "#9198a1",
        "on_header":   "#ffffff",
        "fast":        "#1f6feb",
        "fast_fill":   "#0c2d6b",
        "step":        "#238636",
        "step_fill":   "#0f3d1f",
        "cmp":         "#bd561d",
        "cmp_bg":      "#221610",
        "cmp_fill":    "#4a2512",
        "llm":         "#8957e5",
        "llm_bg":      "#1c1530",
    },
}


def text(
    x: float,
    y: float,
    content: str,
    fill: str,
    size: float = 12,
    weight: int = 400,
    anchor: str = "middle",
    spacing: float | None = None,
) -> str:
    """
    Return an SVG `<text>` element.
    """
    letter = f' letter-spacing="{spacing}"' if spacing else ""
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{fill}" '
        f'font-size="{size}" font-weight="{weight}"{letter}>{escape(content)}</text>'
    )


def rect(
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str,
    stroke: str,
    rx: float = 8,
    dashed: bool = False,
) -> str:
    """
    Return a rounded SVG `<rect>` element.
    """
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}"{dash}/>'
    )


def down(x: float, y0: float, y1: float) -> str:
    """
    Return a vertical arrow from `y0` to `y1`.
    """
    return (
        f'<path d="M{x},{y0 + 3} V{y1 - 3}" stroke="currentColor" '
        f'stroke-width="1.5" fill="none" marker-end="url(#arrow)"/>'
    )


def right(x0: float, x1: float, y: float) -> str:
    """
    Return a horizontal arrow from `x0` to `x1`.
    """
    return (
        f'<path d="M{x0 + 4},{y} H{x1 - 4}" stroke="currentColor" '
        f'stroke-width="1.5" fill="none" marker-end="url(#arrow)"/>'
    )


def card(
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    color: str,
    bg: str,
    c: dict[str, str],
    header_h: float = 40,
) -> list[str]:
    """
    Return a card with a colored header band and a title.
    """
    r = 12
    band = (
        f'<path d="M{x + r},{y} h{w - 2 * r} a{r},{r} 0 0 1 {r},{r} '
        f'v{header_h - r} h{-w} v{-(header_h - r)} a{r},{r} 0 0 1 {r},{-r} z" '
        f'fill="{color}"/>'
    )
    return [
        rect(x, y, w, h, bg, color if bg != c["panel"] else c["border"], rx=r),
        band,
        text(x + 16, y + header_h / 2 + 5, title, c["on_header"], 15, 700, "start"),
    ]


def step(
    cx: float,
    y: float,
    w: float,
    h: float,
    title: str,
    subs: list[str],
    fill: str,
    stroke: str,
    c: dict[str, str],
    dashed: bool = False,
) -> list[str]:
    """
    Return a step box: bold title and gray subtitles, centered on `cx`.
    """
    out = [rect(cx - w / 2, y, w, h, fill, stroke, dashed=dashed)]
    n = 1 + len(subs)
    first = y + h / 2 - (n - 1) * 8 + 5
    out.append(text(cx, first, title, c["ink"], 13.5, 700))
    for i, sub in enumerate(subs, start=1):
        out.append(text(cx, first + 16 * i, sub, c["muted"], 11.5))
    return out


def path_card(x: float, fast: bool, c: dict[str, str]) -> list[str]:
    """
    Return one of the two path cards, fast (`fast=True`) or step-by-step.

    Both share the same rows so they can be compared side by side.
    """
    color, fill = (c["fast"], c["fast_fill"]) if fast else (c["step"], c["step_fill"])
    w = 490
    inner_x, inner_w = x + 16, w - 32
    cx = inner_x + inner_w / 2
    el = card(
        x, 20, w, 466,
        "Fast path: one call" if fast else "Step-by-step path: full control",
        color, c["panel"], c,
    )
    intro = (
        "Data in, result and code out."
        if fast
        else "Inspect or change each object before running."
    )
    el.append(text(inner_x, 80, intro, c["ink"], 12.5, anchor="start"))

    # Everything below the intro is laid out as if the intro had two lines
    # and shifted up by one, so the rows keep their spacing.
    head = el
    el = []
    el.append(rect(inner_x, 108, inner_w, 30, c["surface"], c["border"]))
    el.append(text(cx, 128, "data", c["ink"], 13.5, 600))
    el.append(down(cx, 138, 156))

    # The fast path box spans exactly the profile() and plan() rows, so the
    # rows below line up across both cards.
    if fast:
        el += step(
            cx, 156, inner_w, 92, "profile() and plan()",
            ["run inside each call below"],
            c["panel"], c["muted"], c, dashed=True,
        )
    else:
        el += step(cx, 156, inner_w, 30, "profile()", [], fill, color, c)
        el.append(down(cx, 186, 204))
        el += step(
            cx, 204, inner_w, 44, "plan()",
            ["then refine_plan(), optional, with or without a prompt"],
            fill, color, c,
        )
    el.append(down(cx, 248, 266))

    col_w = (inner_w - 16) / 2
    box_w = col_w - 24
    cols = [inner_x, inner_x + col_w + 16]
    for col_x, label in zip(cols, ["FORECAST", "BACKTESTING (VALIDATION)"]):
        el.append(rect(col_x, 266, col_w, 220, c["surface"], c["border"]))
        el.append(text(col_x + col_w / 2, 288, label, c["muted"], 11, spacing=0.5))

    # The calls that run (forecast, backtest) share a row, and so do their
    # outputs; the row above is the validation setup, which only backtesting
    # needs.
    y_out = 474
    fx = cols[0] + col_w / 2
    el += step(fx, 386, box_w, 50, "forecast()", ["or forecast_code()"], fill, color, c)
    el.append(down(fx, 436, y_out - 16))
    el.append(text(fx, y_out, "predictions + code", c["ink"], 12))

    bx = cols[1] + col_w / 2
    if fast:
        el += step(
            bx, 300, box_w, 64, "TimeSeriesFold",
            ["your own, from skforecast", "passed as backtest(data, cv)"],
            fill, color, c,
        )
    else:
        el += step(
            bx, 300, box_w, 64, "create_cv()",
            ["with or without a prompt", "or your own TimeSeriesFold"],
            fill, color, c,
        )
    el.append(down(bx, 364, 386))
    el += step(bx, 386, box_w, 50, "backtest()", ["or backtest_code()"], fill, color, c)
    el.append(down(bx, 436, y_out - 16))
    el.append(text(bx, y_out, "metrics + predictions + code", c["ink"], 12))
    return head + ['<g transform="translate(0,-16)">', *el, "</g>"]


def compare_card(c: dict[str, str]) -> list[str]:
    """
    Return the model selection card: candidates, compare(), ranked answer.
    """
    y = 506
    el = card(20, y, 1000, 160, "Model selection: which forecaster should you use?",
              c["cmp"], c["cmp_bg"], c)
    by, bh = y + 56, 64
    boxes = [
        (36, 280, "Candidates", c["surface"], c["border"], [
            "forecasters, estimators, lags or window",
            "features; yours or proposed from the profile",
        ]),
        (352, 336, "compare()", c["cmp_fill"], c["cmp"], [
            "one backtest per candidate, same cv,",
            "scored with the metrics you choose",
        ]),
        (724, 280, "A ranked answer", c["surface"], c["border"], [
            "leaderboard with the code of every row;",
            "the winner is ready to reuse",
        ]),
    ]
    for bx, bw, title, fill, stroke, lines in boxes:
        el.append(rect(bx, by, bw, bh, fill, stroke))
        cx = bx + bw / 2
        top = by + bh / 2 - (len(lines) * 15) / 2 + 2
        el.append(text(cx, top, title, c["ink"], 13.5, 700))
        el += [text(cx, top + 18 + 15 * i, line, c["muted"], 11.5)
               for i, line in enumerate(lines)]
    el.append(right(316, 352, by + bh / 2))
    el.append(right(688, 724, by + bh / 2))
    el.append(
        text(520, y + 144,
             "The ranking is a plain sort of the metric column: deterministic and "
             "auditable. The LLM plays no part in choosing the winner.",
             c["muted"], 11.5)
    )
    return el


def ask_card(c: dict[str, str]) -> list[str]:
    """
    Return the LLM reasoning card for `ask()`.
    """
    y = 686
    el = card(20, y, 1000, 100, "LLM reasoning: available at any moment, in any workflow",
              c["llm"], c["llm_bg"], c)
    lines = [
        "Call ask() before, during or after either path: it explains a profile "
        "(optionally with its plan), a script, a cross-validation strategy",
        "or any result, or answers a question with no context.",
    ]
    el += [text(36, y + 64 + 17 * i, line, c["ink"], 12.5, anchor="start")
           for i, line in enumerate(lines)]
    return el


def build(c: dict[str, str]) -> str:
    """
    Build the diagram with the palette `c`.
    """
    el: list[str] = []
    el += path_card(20, fast=True, c=c)
    el += path_card(530, fast=False, c=c)
    el += compare_card(c)
    el += ask_card(c)

    title = (
        "How skforecast-ai works: the fast path runs profiling and planning inside "
        "forecast() or backtest(); the step-by-step path calls profile(), plan() and "
        "create_cv() so you can inspect each object. compare() ranks several "
        "configurations under the same cross-validation, and ask() explains any "
        "object at any moment."
    )
    body = "\n  ".join(el)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" role="img" font-family="{FONT}" '
        f'color="{c["muted"]}">\n'
        f"  <title>{escape(title)}</title>\n"
        '  <defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{c["muted"]}"/></marker></defs>\n'
        f"  {body}\n</svg>\n"
    )


def main() -> None:
    """
    Write the light and dark variants of the diagram.
    """
    for theme, suffix in [("light", ""), ("dark", "-dark")]:
        target = OUTPUT_DIR / f"how-it-works{suffix}.svg"
        target.write_text(build(PALETTES[theme]), encoding="utf-8")
        print(f"Wrote {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
