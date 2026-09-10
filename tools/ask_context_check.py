"""
Check what `ForecastingAssistant.ask()` sends to the LLM and what comes back.

The goal is to judge whether the context the `llm` module builds for each
kind of object (profile, plan, script, cross-validation strategy, forecast,
backtest, comparison) is enough for the model to answer well, and to spot
information the library has but does not send.

For every scenario the script prints and writes to a Markdown report:

- the questions asked, split into "grounded" (answerable from the context)
  and "probe" (deliberately NOT answerable, to see whether the model admits
  it or makes something up),
- the skills routed to the model and the size of the context,
- the exact `<forecast_context>` block the model received,
- the answer,
- a review checklist for the reader,
- the fields the source objects hold that do not appear in the context.

Usage (from the repository root, inside the conda environment):

    python tools/ask_context_check.py --dry-run          # contexts only, no LLM
    python tools/ask_context_check.py                    # full run
    python tools/ask_context_check.py --scenarios profile,plan,compare
    python tools/ask_context_check.py --extra-context notes.txt

`--extra-context` prepends the text of a file to every question, which is
a quick way to test whether giving the model extra facts (for example the
seasonal period or the PACF values) improves an answer before deciding to
add them to the library context.

Model: defaults to the value of `ASK_CHECK_LLM`, else `google:gemini-3.5-flash`.
To see which Gemini models the key can use, list them with:

    curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY" \\
        | python -c "import json,sys; [print(m['name']) for m in json.load(sys.stdin)['models']]"

and pass the newest flash model with `--model google:<name>`.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from skforecast_ai import ForecastingAssistant, LLMCallError  # noqa: E402
from skforecast_ai.llm.skills import estimate_context_tokens  # noqa: E402

DEFAULT_MODEL = os.getenv("ASK_CHECK_LLM", "google:gemini-3.5-flash")
REPORTS_DIR = REPO_ROOT / "tools" / "ask_context_reports"


# =============================================================================
# Data
# =============================================================================
DATASETS = {
    # name: (target, date_column, default steps)
    "bike_sharing": ("users", "date_time", 36),
    "items_sales": (["item_1", "item_2", "item_3"], "date", 14),
}


def load_data(name: str, tail: int) -> pd.DataFrame:
    """
    Load one of the datasets used for the check.

    `bike_sharing` is the hourly single series used by the documentation
    (with exogenous variables). `items_sales` is a daily wide-format
    multi-series dataset (three items), which exercises the per-series
    branches of the context renderers. The bike sharing download falls
    back to a synthetic hourly series so the script still runs offline.

    Parameters
    ----------
    name : str
        One of the keys of `DATASETS`.
    tail : int
        Number of trailing rows to keep, to bound the run time.

    Returns
    -------
    data : pandas DataFrame
        The dataset, date column included.
    """

    from skforecast.datasets import fetch_dataset

    if name == "items_sales":
        data = fetch_dataset("items_sales", raw=True, verbose=False)
        data["date"] = pd.to_datetime(data["date"])
        data = data.tail(tail).reset_index(drop=True)
        print(f"[data] skforecast items_sales: {len(data)} rows, {data['date'].min()} to {data['date'].max()}")
        return data

    try:
        data = fetch_dataset("bike_sharing", raw=True, verbose=False)
        data = data[["date_time", "users", "holiday", "weather", "temp"]].copy()
        data["date_time"] = pd.to_datetime(data["date_time"])
        source = "skforecast bike_sharing"
    except Exception as exc:  # network, missing dataset
        print(f"[data] fetch failed ({exc}); using a synthetic series")
        rng = np.random.default_rng(123)
        index = pd.date_range("2012-01-01", periods=max(tail, 24 * 60), freq="h")
        hour = index.hour.to_numpy()
        day = index.dayofweek.to_numpy()
        users = (
            120
            + 80 * np.sin(2 * np.pi * hour / 24)
            + 30 * (day < 5)
            + rng.normal(0, 15, len(index))
        )
        data = pd.DataFrame({
            "date_time": index,
            "users": users.clip(0).round(),
            "holiday": (rng.random(len(index)) < 0.03).astype(float),
            "weather": rng.choice(["clear", "mist", "rain"], len(index)),
            "temp": 15 + 10 * np.sin(2 * np.pi * hour / 24) + rng.normal(0, 2, len(index)),
        })
        source = "synthetic"

    data = data.tail(tail).reset_index(drop=True)
    print(f"[data] {source}: {len(data)} rows, {data['date_time'].min()} to {data['date_time'].max()}")
    return data


# =============================================================================
# Scenarios
# =============================================================================
@dataclass
class Scenario:
    """
    One kind of context to evaluate.

    Attributes
    ----------
    name : str
        Short identifier used on the command line.
    build : callable
        Returns `(context, plan)` for `ask()`, from the workflow objects.
    grounded : list of str
        Questions answerable from the context.
    probes : list of str
        Questions the context cannot answer; the model should say so.
    checklist : list of str
        What the reader should verify in the answers.
    multi_series : list of str
        Extra grounded questions asked only on multi-series data.
    """

    name: str
    build: Callable[[dict[str, Any]], tuple[Any, Any]]
    grounded: list[str]
    probes: list[str] = field(default_factory=list)
    checklist: list[str] = field(default_factory=list)
    multi_series: list[str] = field(default_factory=list)


SCENARIOS: list[Scenario] = [
    Scenario(
        name="qa",
        build=lambda w: (None, None),
        grounded=[
            "For hourly demand with strong daily and weekly seasonality, when "
            "should I prefer a direct forecasting strategy over a recursive one?",
        ],
        probes=[
            "What is the best number of lags for my dataset?",
        ],
        checklist=[
            "Answers from the skills, with a concrete skforecast API when suggesting next steps.",
            "The probe is declined: there is no dataset in this mode.",
        ],
    ),
    Scenario(
        name="profile",
        build=lambda w: (w["profile"], None),
        grounded=[
            "Why were this forecaster and estimator recommended for my data, "
            "and what do the exogenous variables add?",
        ],
        probes=[
            "Which seasonal periods did you detect and how strong is the weekly one?",
            "How many missing values does the target have?",
        ],
        checklist=[
            "Only values present in <dataset> and <profile_decision> are quoted.",
            "The estimator justification matches the size rule (Ridge below 250 observations).",
            "Probes: seasonality strength is not in the context; missing values are only in the context if they are non zero.",
        ],
    ),
    Scenario(
        name="plan",
        build=lambda w: (w["profile"], w["plan"]),
        grounded=[
            "Walk me through this plan: why these lags and window features, "
            "and how will the prediction interval be produced?",
        ],
        probes=[
            "Which lag will matter most for accuracy?",
        ],
        checklist=[
            "Lags and window features are quoted exactly as in <forecast_plan>.",
            "No code block in the answer (result.code exists).",
            "Probe: feature importance is refused, not invented.",
        ],
    ),
    Scenario(
        name="code",
        build=lambda w: (w["code_result"], None),
        grounded=[
            "Explain what this script does step by step and what I need to run it.",
        ],
        probes=[
            "How long will the script take to run?",
        ],
        checklist=[
            "The steps described match the plan (preprocessing, split, fit, predict, metrics).",
            "No code is reproduced; it points to result.code.",
        ],
    ),
    Scenario(
        name="cv",
        build=lambda w: (w["cv_result"], None),
        grounded=[
            "Why this initial training size and refit setting, and how many "
            "folds will the backtest run?",
        ],
        probes=[
            "How long will the backtest take on my machine?",
        ],
        checklist=[
            "n_folds and the parameters are quoted from <cross_validation>.",
            "The deterministic summary is used, not re-derived.",
        ],
    ),
    Scenario(
        name="forecast",
        build=lambda w: (w["forecast_result"], None),
        grounded=[
            "Explain the evaluation metrics. Is the MASE good, and what do the "
            "predictions look like?",
        ],
        probes=[
            "Which exogenous variable drives the forecast the most?",
            "What is the RMSE?",
        ],
        checklist=[
            "MASE is interpreted against the naive baseline (below 1 beats it) and nothing else.",
            "No percentage improvements or derived numbers.",
            "Probes: attribution refused; RMSE reported as not available.",
        ],
        multi_series=[
            "Which series is forecast worst, and is the average row representative of all of them?",
        ],
    ),
    Scenario(
        name="backtest",
        build=lambda w: (w["backtest_result"], None),
        grounded=[
            "Explain the backtesting strategy and the metrics. Is the model good "
            "enough to deploy?",
        ],
        probes=[
            "How did the error evolve from the first fold to the last one?",
        ],
        checklist=[
            "Fold count comes from <cross_validation> or the summary, not from counting rows.",
            "Probe: with rows omitted in <predictions>, no trend across folds is described.",
        ],
        multi_series=[
            "Compare the series: which one has the best and the worst backtest error?",
        ],
    ),
    Scenario(
        name="compare",
        build=lambda w: (w["comparison_result"], None),
        grounded=[
            "Explain the comparison. Is the margin between the top candidates "
            "meaningful, or are they practically equivalent?",
        ],
        probes=[
            "Why did the winner beat the runner-up?",
        ],
        checklist=[
            "Ranking and values are restated, not re-ranked.",
            "Probe: causes are not explained beyond the metric values.",
        ],
    ),
]


# =============================================================================
# Workflow objects
# =============================================================================
def build_workflow(
    assistant: ForecastingAssistant, data: pd.DataFrame, steps: int, spec: tuple
) -> dict[str, Any]:
    """
    Run the deterministic workflow once and keep every object it produces.

    Parameters
    ----------
    assistant : ForecastingAssistant
        Assistant used for the deterministic methods (no LLM needed).
    data : pandas DataFrame
        Dataset to profile and forecast.
    steps : int
        Forecast horizon.
    spec : tuple
        `(target, date_column, default_steps)` entry of `DATASETS`.

    Returns
    -------
    workflow : dict
        Profile, plan, code result, cv result, forecast, backtest and
        comparison results.
    """

    started = time.perf_counter()
    target, date_column, _ = spec
    common = dict(target=target, date_column=date_column)
    multi = isinstance(target, list)

    profile = assistant.profile(data=data, **common)
    plan = assistant.plan(profile, steps=steps, interval=[0.1, 0.9])
    code_result = assistant.forecast_code(profile=profile, plan=plan)
    cv_result = assistant.create_cv(profile, plan, refit=False)
    forecast_result = assistant.forecast(
        data=data, test_size=steps, profile=profile, plan=plan
    )
    backtest_result = assistant.backtest(
        data=data, cv=cv_result, profile=profile, plan=plan, show_progress=False
    )
    candidates = None if multi else [
        ("recursive_default", {"forecaster": "ForecasterRecursive"}),
        ("recursive_ridge", {"forecaster": "ForecasterRecursive", "estimator": "Ridge"}),
        ("direct", {"forecaster": "ForecasterDirect"}),
    ]
    comparison_result = assistant.compare(
        data=data, cv=cv_result, profile=profile, candidates=candidates,
        show_progress=False,
    )
    print(f"[workflow] built in {time.perf_counter() - started:.1f}s")

    return {
        "multi_series": multi,
        "profile": profile,
        "plan": plan,
        "code_result": code_result,
        "cv_result": cv_result,
        "forecast_result": forecast_result,
        "backtest_result": backtest_result,
        "comparison_result": comparison_result,
    }


# =============================================================================
# What the objects hold but the context does not say
# =============================================================================
def unsent_information(workflow: dict[str, Any], context_text: str) -> list[str]:
    """
    List fields of the profile and plan that do not appear in a context.

    A field counts as sent when its name appears in the context text. This
    is a heuristic to prompt the reader, not a proof of absence.

    Parameters
    ----------
    workflow : dict
        Workflow objects (uses `profile` and `plan`).
    context_text : str
        The `<forecast_context>` block sent to the model.

    Returns
    -------
    lines : list of str
        One line per unsent field with a compact rendering of its value.
    """

    dp = workflow["profile"].data_profile
    profile = workflow["profile"]
    plan = workflow["plan"]
    candidates: dict[str, Any] = {
        "series_lengths (start/end per series)": {k: (v.start, v.end, v.length) for k, v in dp.series_lengths.items()},
        "target_stats": dp.target_stats,
        "missing_target": dp.missing_target,
        "missing_exog": dp.missing_exog,
        "categorical_exog": dp.categorical_exog,
        "has_gaps": dp.has_gaps,
        "has_duplicate_timestamps": dp.has_duplicate_timestamps,
        "index_is_monotonic": dp.index_is_monotonic,
        "frequency_is_set": dp.frequency_is_set,
        "data warnings": dp.warnings,
        "series_pacf (significant lags)": {s.series_id: s.lags for s in profile.series_pacf} or None,
        "profile.window_features": profile.window_features,
        "profile.calendar_features": profile.calendar_features,
        "plan.preprocessing_steps": [s.action for s in plan.preprocessing_steps],
        "plan.warnings": plan.warnings,
        "plan.estimator_kwargs": plan.estimator_kwargs,
        "plan.metrics_to_compute": plan.metrics_to_compute,
        "plan.forecaster_kwargs keys": sorted(plan.forecaster_kwargs),
    }

    # How each field shows up in the rendered context, when it does.
    labels = {
        "series_lengths (start/end per series)": ["Date range:"],
        "target_stats": ["Target statistics"],
        "missing_target": ["Missing in target", "Missing values: none"],
        "missing_exog": ["Missing in exog", "Missing values: none"],
        "categorical_exog": ["Categorical exogenous columns"],
        "has_gaps": ["Index irregularities"],
        "has_duplicate_timestamps": ["Index irregularities"],
        "index_is_monotonic": ["Index irregularities"],
        "data warnings": ["Data warning:"],
        "series_pacf (significant lags)": ["Significant lags"],
        "profile.window_features": ["Suggested window features"],
        "profile.calendar_features": ["Suggested calendar features"],
        "plan.preprocessing_steps": ["[informational]", "[in generated code]"],
    }

    lines = []
    lowered = context_text.lower()
    for name, value in candidates.items():
        if value in (None, [], {}, ""):
            continue
        aliases = labels.get(name, [name.split(" ")[0].split(".")[-1]])
        if any(alias.lower() in lowered for alias in aliases):
            continue
        rendered = textwrap.shorten(repr(value), width=140, placeholder=" ...")
        lines.append(f"- {name}: {rendered}")
    return lines


# =============================================================================
# Runner
# =============================================================================
def run_scenario(
    scenario: Scenario,
    assistant: ForecastingAssistant,
    workflow: dict[str, Any],
    *,
    dry_run: bool,
    extra_context: str | None,
    show_context: bool,
) -> list[str]:
    """
    Run one scenario and return the Markdown lines of its report section.

    Parameters
    ----------
    scenario : Scenario
        Scenario to run.
    assistant : ForecastingAssistant
        Assistant configured with the LLM under evaluation.
    workflow : dict
        Objects produced by `build_workflow`.
    dry_run : bool
        When True, no LLM call is made; only the context is reported.
    extra_context : str, None
        Text prepended to every question, for experiments.
    show_context : bool
        Whether to include the full context block in the report.

    Returns
    -------
    lines : list of str
        Markdown lines.
    """

    context, plan = scenario.build(workflow)
    lines = [f"## Scenario: {scenario.name}", ""]

    # The exact block the model receives, taken through the same path ask() uses.
    if context is None:
        context_text = ""
    elif plan is not None:
        from skforecast_ai.schemas import CodeGenerationResult
        from skforecast_ai.execution.forecast_runner import render_forecast_script

        pair = CodeGenerationResult(
            profile=context, plan=plan,
            code=render_forecast_script(profile=context.data_profile, plan=plan).full_script,
        )
        context_text = pair.to_llm_context(send_data=True).text
    else:
        context_text = context.to_llm_context(send_data=True).text

    lines.append(f"- Context size: about {estimate_context_tokens(context_text)} tokens")
    if context_text:
        unsent = unsent_information(workflow, context_text)
        lines.append("- Information available in the objects but not in the context:")
        lines.extend(("  " + line) for line in unsent) if unsent else lines.append("  (none detected)")
    if show_context and context_text:
        lines += ["", "<details><summary>Context sent to the model</summary>", "", "```", context_text, "```", "", "</details>", ""]

    grounded = list(scenario.grounded)
    if workflow.get("multi_series"):
        grounded += scenario.multi_series
    questions = [("grounded", q) for q in grounded] + [("probe", q) for q in scenario.probes]
    for kind, question in questions:
        lines += [f"### [{kind}] {question}", ""]
        prompt = f"{extra_context}\n\n{question}" if extra_context else question
        if dry_run:
            lines += ["_(dry run: no LLM call)_", ""]
            continue
        started = time.perf_counter()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                answer = assistant.ask(prompt, context=context, plan=plan)
        except LLMCallError as exc:
            lines += [f"**LLM error:** {exc}", ""]
            print(f"  [{scenario.name}] LLM error: {exc.original_error}")
            continue
        elapsed = time.perf_counter() - started
        lines += [
            f"- Skills: {', '.join(answer.skills) or '(none)'}; {elapsed:.1f}s",
            "",
            answer.explanation.strip(),
            "",
        ]
        print(f"  [{scenario.name}] {kind}: {elapsed:.1f}s, skills={answer.skills}")

    lines += ["### Review checklist", ""] + [f"- [ ] {item}" for item in scenario.checklist] + [""]
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM provider string, e.g. google:gemini-3.5-flash")
    parser.add_argument("--scenarios", default=",".join(s.name for s in SCENARIOS), help="Comma-separated scenario names")
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="bike_sharing", help="Dataset to run on")
    parser.add_argument("--tail", type=int, default=2000, help="Trailing rows of the dataset to use")
    parser.add_argument("--steps", type=int, default=None, help="Forecast horizon (default depends on the dataset)")
    parser.add_argument("--send-data", action="store_true", help="Set send_data_to_llm=True on the assistant")
    parser.add_argument("--extra-context", type=Path, default=None, help="Text file prepended to every question")
    parser.add_argument("--dry-run", action="store_true", help="Build contexts only; make no LLM call")
    parser.add_argument("--no-context", action="store_true", help="Do not include the context blocks in the report")
    parser.add_argument("--out", type=Path, default=None, help="Report path (default tools/ask_context_reports/ask_context_<dataset>_<timestamp>.md)")
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_API_KEY") if args.model.startswith("google:") else None
    if not args.dry_run and args.model.startswith("google:") and not api_key:
        sys.exit("GOOGLE_API_KEY is not set. Export it or use --dry-run.")

    selected = [s for s in SCENARIOS if s.name in set(args.scenarios.split(","))]
    unknown = set(args.scenarios.split(",")) - {s.name for s in SCENARIOS}
    if unknown:
        sys.exit(f"Unknown scenarios: {sorted(unknown)}. Available: {[s.name for s in SCENARIOS]}")

    extra_context = args.extra_context.read_text() if args.extra_context else None

    spec = DATASETS[args.dataset]
    steps = args.steps or spec[2]
    data = load_data(args.dataset, args.tail)
    deterministic = ForecastingAssistant()
    workflow = build_workflow(deterministic, data, steps, spec)

    assistant = ForecastingAssistant(
        llm=args.model, api_key=api_key, send_data_to_llm=args.send_data
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = [
        f"# ask() context check ({stamp})",
        "",
        f"- Model: `{args.model}`{' (dry run)' if args.dry_run else ''}",
        f"- Data: {args.dataset}, {len(data)} rows, steps={steps}, send_data_to_llm={args.send_data}",
        f"- Extra context: {args.extra_context or 'none'}",
        "",
    ]
    for scenario in selected:
        print(f"[scenario] {scenario.name}")
        report += run_scenario(
            scenario, assistant, workflow,
            dry_run=args.dry_run, extra_context=extra_context,
            show_context=not args.no_context,
        )

    out = args.out or REPORTS_DIR / f"ask_context_{args.dataset}_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report), encoding="utf-8")
    print(f"[report] {out}")


if __name__ == "__main__":
    main()
