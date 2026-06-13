# Why skforecast-ai?

Time series forecasting has a crowded toolbox: statistical libraries, deep-learning frameworks, AutoML systems, hosted foundation-model APIs. skforecast-ai is not trying to replace any of them. It occupies a specific, deliberate niche:

> **An automated, *deterministic* model-selection layer that hands you the exact, runnable `skforecast` code it used, with an optional LLM that explains the decisions but never makes them.**

If you've ever wanted AutoML-style convenience without giving up reproducibility or auditability, that's the gap this fills.

## The one-paragraph pitch

You give it a time series. It profiles the data, applies transparent rules to pick a forecaster, estimator, lags, and metric, runs a backtest, and returns predictions plus the standalone script that produced them. Every decision is a rule you can read; the same data always yields the same result; and the generated code runs on plain `skforecast` with no dependency on this library at inference time. An optional LLM layer can explain any of it in plain language and suggest improvements you choose whether to apply.

## How it compares

These are excellent tools. The table is about *fit*, not quality: what each is optimised for, and where skforecast-ai sits relative to it.

| Tool | What it's great at | How skforecast-ai differs |
| --- | --- | --- |
| **[skforecast](https://github.com/JoaquinAmatRodrigo/skforecast)** (the engine underneath) | Flexible, production-grade forecasting with scikit-learn estimators; full manual control. | skforecast-ai *automates the decisions* (forecaster, estimator, lags, metric) on top of skforecast and explains them. You graduate to raw skforecast by copying the generated code. |
| **Nixtla / TimeGPT, StatsForecast, MLForecast** | Fast statistical/ML forecasting at scale; TimeGPT is a hosted foundation model. | skforecast-ai is local-first and deterministic by default; the "AI" is an *explanation* layer, not the forecaster. You can still drop in foundation models (Chronos-2) when you want zero-shot. |
| **Darts, sktime** | Broad unified APIs across many model families. | skforecast-ai is narrower and opinionated: it *chooses for you* with documented rules and emits auditable code, rather than offering a large model catalogue to wire up yourself. |
| **AutoGluon-TS, AutoTS, auto-sklearn** | Powerful black-box AutoML search over large model/HPO spaces. | skforecast-ai's selection is **rule-based and deterministic**, not a stochastic search. It trades peak leaderboard accuracy for reproducibility, speed, transparency, and code you can read. |
| **Prophet** | Easy, robust trend/seasonality decomposition for business series. | skforecast-ai covers a wider model space (gradient boosting, multi-series global models, statistical, foundation) and gives you the underlying code and metrics rather than a single model. |
| **Raw LLM "forecast my data" prompts** | Conversational, zero setup. | skforecast-ai never lets the LLM produce numbers. Forecasts come from a deterministic engine; the LLM only explains. No hallucinated values. |

## When skforecast-ai is the right choice

- You want **automated model selection** but need the result to be **reproducible and auditable**, not a black box.
- You value the **exact code**: something you can review, version-control, and run standalone in production.
- You want **plain-language explanations** of modelling decisions for yourself, a stakeholder, or a reviewer, grounded in the engine's real rules.
- You want a **fast, trustworthy baseline** (including zero-shot [foundation models](foundation-forecasting.md)) before investing in heavy tuning.
- You want everything to **run locally**, offline, with no API key in the default path.

## When to reach for something else

- You need to **squeeze out maximum accuracy** via exhaustive AutoML/HPO search and don't need determinism → AutoGluon-TS or a dedicated HPO loop (skforecast-ai can still produce the baseline you compare against; see [features & tuning](going-further.md)).
- You want a **hosted, fully managed forecasting API** with no local compute → TimeGPT and similar services.
- You need **model families skforecast doesn't cover** (e.g. specialised hierarchical reconciliation, custom deep nets) → a broader framework like Darts or sktime.

## Next steps

- **[Your first forecast](first-forecast.md)**: see the workflow in a few lines.
- **[How it works & trust](how-it-works-and-trust.md)**: the determinism and fidelity guarantees in depth.
- **[Foundation models](foundation-forecasting.md)**: zero-shot forecasting with Chronos-2.
