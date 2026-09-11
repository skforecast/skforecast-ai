# ask() context evaluation

`tools/ask_context_check.py` sends what `ForecastingAssistant.ask()` builds
for every kind of object (profile, plan, script, cross-validation strategy,
forecast, backtest, comparison) to a real LLM and writes a Markdown report
with the exact `<forecast_context>` block, the answers and a review
checklist. It is the only check of the quality of `ask()` with a real
model: the unit tests verify that the context contains what it should, not
that a model answers well with it.

It is a manual, pre-release tool. It costs money, needs network access and
its answers are not deterministic, so it is not part of the test suite.

## When to run it

Before a release, whenever one of these changed since the previous run:

- `skforecast_ai/llm/context.py` (what the model receives),
- `skforecast_ai/llm/prompts.py` (the rules it follows),
- `skforecast_ai/skills/` (synced from skforecast),
- the explanations rendered by `recommendation/explanation.py`,
  `execution/backtesting_runner.py` or `execution/comparison.py`.

## How to run it

From the repository root, inside the project conda environment, with
`GOOGLE_API_KEY` (or the key of the chosen provider) in the environment:

```bash
python tools/ask_context_check.py --dry-run                     # contexts only, free
python tools/ask_context_check.py --dataset bike_sharing        # single series with exog
python tools/ask_context_check.py --dataset items_sales         # three series, wide format
python tools/ask_context_check.py --scenarios profile,compare   # a subset
```

A full run makes about 15 calls per dataset. With `google:gemini-3.5-flash`
that is a few cents. Ad hoc reports land in this folder with a timestamped
name and are ignored by git.

## What to keep

One reviewed report per release and dataset, named
`<release>_<dataset>.md` (for example `0.3.1_items_sales.md`), saved with
`--out tools/ask_context_reports/<release>_<dataset>.md`. Those are
tracked, so the next release can be compared against them question by
question. Keep only the final run on the released code, not the
intermediate iterations.

## Acceptance criteria

Tick every "Review checklist" item of the report. An answer fails the run
when it:

- quotes a number that is not in `<forecast_context>` or derives one
  (percentages, ratios, RMSE from MSE),
- interprets MASE against anything other than the naive baseline,
- explains why a candidate won, or attributes accuracy to a feature,
- describes a trend across a truncated `<predictions>` table,
- answers a probe question with an invented value instead of saying the
  information is not available,
- reproduces the generated script when `result.code` exists.

A wrong answer whose information was missing from the context is a gap in
`llm/context.py`; a wrong answer whose information was present is a gap in
`llm/prompts.py`. Fix the library, then rerun the affected scenarios.

## Log

| Release | Date | Model | Dataset | Findings and changes |
| --- | --- | --- | --- | --- |
| 0.3.0 | 2026-09-10 | google:gemini-3.5-flash | bike_sharing | Final run on the released code, all checklist items pass. Earlier iterations in this release found the context was the bottleneck, not the model, and added to `<dataset>`: date range, target statistics, categorical exogenous columns, missing values, index irregularities; to `<profile_decision>`: PACF lags, suggested window and calendar features; a new `<script>` section for code results; and the "do not suggest reasons for the ranking" note in `<comparison_overview>`. |
| 0.3.0 | 2026-09-10 | google:gemini-3.5-flash | items_sales | All checklist items pass. Found and fixed: `compare()` ranked `ForecasterRecursiveMultiSeries` (average across series) against `ForecasterDirectMultiVariate` (one series), now rejected; the `fold` column was summarised as if it were a measurement; the `<predictions>` summary pooled all series, so a question about one series was unanswerable (per-level summary of `pred` added). Observation counts are now stated as pooled across series. Not implemented: per-fold metrics, so the evolution of the error across folds stays unanswerable. |
