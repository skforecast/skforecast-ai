# ask() context evaluation

`tools/ai/check_ask_context.py` sends what `ForecastingAssistant.ask()` builds
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
python tools/ai/check_ask_context.py --dry-run                     # contexts only, free
python tools/ai/check_ask_context.py --dataset bike_sharing        # single series with exog
python tools/ai/check_ask_context.py --dataset items_sales         # three series, wide format
python tools/ai/check_ask_context.py --dataset items_sales_long    # the same, long format
python tools/ai/check_ask_context.py --dataset h2o                 # monthly, ForecasterStats
python tools/ai/check_ask_context.py --scenarios profile,compare   # a subset
```

Before a release, run the four datasets: some scenarios need objects that
only some datasets produce (ForecasterStats and the default comparison
with ForecasterStats and ForecasterFoundation on `h2o`; more than 15
candidates and more than 15 categorical variables on the single series)
and are skipped on the others. The plan with decisions of the user and a
plan warning (`overrides_plan`) and the backtest script of the same data
with dates in Europe/Madrid (`time_zone_backtest_code`) run on all four
(the first on single and multi-series data, as the four are).

A full run makes about 25 to 30 calls per dataset. With `google:gemini-3.8-flash`
that is a few cents. Ad hoc reports land in this folder with a timestamped
name and are ignored by git.

## What to keep

One reviewed report per release and dataset, named
`<release>_<dataset>.md` (for example `0.3.1_items_sales.md`), saved with
`--out tools/ai/ask_context_reports/<release>_<dataset>.md`. Those are
tracked, so the next release can be compared against them question by
question. Keep only the final run on the released code, not the
intermediate iterations.

## Acceptance criteria

Tick every "Review checklist" item of the report. An answer fails the run
when it:

- quotes a number that is not in `<forecast_context>` or derives one
  (percentages, ratios, RMSE from MSE),
- interprets MASE against anything other than the one-step naive forecast
  (in particular against the baseline row of a comparison),
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
| 0.4.0 | 2026-09-30 | google:gemini-3.8-flash | bike_sharing | All checklist items pass. The model changes from `gemini-3.5-flash` to `gemini-3.8-flash`: half the price, and on the same code and prompt it had none of the minor slips 3.5 made (a derived duration, "stable predictive power over time" without per-fold metrics, a runtime guess in a probe). The first 3.5 run found that, asked whether a foundation model would be more accurate, the model pointed to the skforecast functions (`backtesting_foundation`) instead of `assistant.backtest()` and `assistant.compare()`: rule 11 of the role prompt now names them as the APIs to suggest (worded as a separate instruction, it made the model add next steps nobody asked for). The `foundation_plan` scenario uses the default model, Chronos-2, instead of TimesFM 3.0, whose non-commercial license the model overstated; the license and numeric-covariate explanations stay covered by the unit tests. The new seasonal naive baseline row is never taken as the MASE reference. |
| 0.4.0 | 2026-09-30 | google:gemini-3.8-flash | items_sales | All checklist items pass, including the new multi-series foundation checks (one model for every series, equal lengths not required) and the comparison of `ForecasterFoundation` against `ForecasterRecursiveMultiSeries`, which has no baseline row. With `gemini-3.5-flash` the plan answer said lag 2 is significant for all three items (it is not listed for item_2), and one run wrote a wrong import (`skforecast.recursive.ForecasterDirect`); `gemini-3.8-flash` quotes the lags of each series correctly. |
