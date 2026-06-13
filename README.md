# skforecast-ai

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue" alt="Python version">
  <img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License">
  <a href="https://github.com/JoaquinAmatRodrigo/skforecast"><img src="https://img.shields.io/badge/built%20on-skforecast-orange" alt="Built on skforecast"></a>
</p>

**An AI forecasting assistant you can actually trust.** `skforecast-ai` pairs a **deterministic, rule-based forecasting engine** (built on [`skforecast`](https://github.com/JoaquinAmatRodrigo/skforecast)) with an **optional LLM reasoning layer**. Give it a time series and it profiles the data, selects a model using established best practices, evaluates it, and returns the forecast, along with the *exact, runnable* `skforecast` script that produced it.

The engine is **100% deterministic and rule-based**: the same data always yields the same result. The optional LLM is a **reasoning layer that explains decisions but never makes them**: it interprets backtesting metrics, diagnoses errors, and suggests improvements you can choose to apply, but it never alters the underlying math. No black boxes, no hallucinated numbers.

---

## ✨ Why skforecast-ai?

- 🎯 **Deterministic by design**: a transparent, rule-based engine. Same input → same output, every time. Reproducible results with no AI hallucinations.
- 🔍 **Code you can trust**: the script you see is *exactly* the code that ran (`result.code`). Inspect it, version it, or run it standalone with plain `skforecast`.
- ⚡ **Data to forecast in one call**: automatic data profiling, model and estimator selection, lag/feature engineering, and backtest evaluation.
- 🔌 **Runs locally, no API key**: the full pipeline works offline in its default deterministic mode.
- 💬 **Optional LLM overlay**: ask plain-language questions about your forecast. The model explains; it doesn't decide.
- 🏗️ **Built on skforecast**, backed by a mature ecosystem: recursive & direct forecasters, multi-series, statistical, and foundation models (zero-shot Chronos-2).

---

## 🧭 Where it fits in the AI-era forecasting stack

The forecasting landscape is crowded with "AI" tools that hand you a number and ask you to trust it. skforecast-ai takes the opposite bet: it brings the topics that actually matter in production into one transparent workflow.

- **Explainability**: every decision is a rule you can read, and the optional LLM puts it in plain language.
- **Reproducible automated reasoning**: model selection is automated, but rule-based and deterministic, not a black-box AutoML search.
- **Human-in-the-loop**: inspect the plan, ask for suggestions, override, and re-run. You stay in control of every decision.
- **Foundation models**: drop in zero-shot models like Chronos-2 for cold-start series, no training required.

See [Why skforecast-ai?](docs/user_guides/why-skforecast-ai.md) for how it compares to Nixtla/TimeGPT, Darts, sktime, AutoGluon-TS, and Prophet.

---

## 📦 Installation

```bash
pip install skforecast-ai
```

To enable the optional LLM assistant:

```bash
pip install "skforecast-ai[llm]"
```

<details>
<summary>Install from source (for development)</summary>

```bash
git clone https://github.com/JoaquinAmatRodrigo/skforecast-ai.git
cd skforecast-ai
pip install -e ".[dev]"
```
</details>

Requires Python ≥ 3.10.

---

## 🚀 Quickstart

From raw data to a validated forecast, and the code behind it, in under ten lines:

```python
import pandas as pd
from skforecast_ai import ForecastingAssistant

# Any DataFrame (or CSV path) with a value column and a date column
url = "https://raw.githubusercontent.com/JoaquinAmatRodrigo/skforecast/master/data/h2o.csv"
data = pd.read_csv(url, header=0, names=["y", "date"])

assistant = ForecastingAssistant()          # deterministic mode: no API key required
result = assistant.forecast(data, target="y", steps=12, date_column="date")

print(result.predictions)   # forecast for the next 12 steps
print(result.metrics)       # evaluation metrics: MAE / MSE / MASE
print(result.code)          # the exact skforecast script that produced this result
```

That single `forecast()` call profiled the data, chose a forecaster and estimator, generated a `skforecast` script, and executed it, and `result.code` is the literal script that ran.

👉 New here? Walk through it step by step in **[Your first forecast](docs/user_guides/first-forecast.md)**.

---

## 🧠 How it works

Every forecast flows through four transparent, inspectable stages:

```
Your data  →  profile()  →  plan()  →  generate code  →  execute
              (inspect)     (decide)    (audit)           (run)
```

1. **Profile**: inspect the data (frequency, gaps, missing values, exogenous columns).
2. **Plan**: choose the forecaster, estimator, lags, and metrics using transparent rules.
3. **Generate**: render a standalone, human-readable `skforecast` script.
4. **Execute**: run that exact script and return predictions, metrics, and the code.

The optional LLM layer reads this state to *explain* it; it never alters the result:

```python
assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")
answer = assistant.ask("Why was this model chosen?", forecast_result=result)
print(answer.explanation)
```

Read more in **[How it works & trust](docs/user_guides/how-it-works-and-trust.md)**.

---

## 📚 Documentation

| Guide | What it covers |
| --- | --- |
| [Your first forecast](docs/user_guides/first-forecast.md) | Data → forecast in a few lines (start here) |
| [The forecasting workflow](docs/user_guides/the-forecasting-workflow.md) | `profile → plan → refine_plan → forecast`, step by step |
| [How it works & trust](docs/user_guides/how-it-works-and-trust.md) | Determinism, the `exec()` fidelity guarantee, and privacy |
| [Understanding your data](docs/user_guides/understanding-your-data.md) | What profiling detects and how to read it |
| [Customizing the model](docs/user_guides/customizing-the-model.md) | Override the forecaster, estimator, horizon, or intervals |
| [Backtesting & validation](docs/user_guides/backtesting.md) | Rigorous walk-forward evaluation |
| [Using the AI assistant](docs/user_guides/using-the-ai-assistant.md) | *(optional)* Configure an LLM and ask questions |
| [Why skforecast-ai?](docs/user_guides/why-skforecast-ai.md) | How it compares to TimeGPT, Darts, sktime, AutoGluon-TS, Prophet |
| [Foundation models](docs/user_guides/foundation-forecasting.md) | Zero-shot forecasting with Chronos-2 and friends |
| [Human-in-the-loop](docs/user_guides/human-in-the-loop.md) | Forecast → ask → refine → re-run, end to end |

Browse every guide in [`docs/user_guides/`](user_guides/). The full **API reference** is generated from the docstrings in [`skforecast_ai/`](skforecast_ai/).

---

## 🤝 Contributing

Contributions are welcome, whether it's a bug report, a feature idea, or a pull request. Please see the [Contributing Guide](CONTRIBUTING.md) and our [Code of Conduct](CODE_OF_CONDUCT.md) to get started.

## 📄 License

Licensed under the Apache License 2.0 (see [LICENSE](LICENSE) for details).

Built with ❤️ on top of [skforecast](https://github.com/JoaquinAmatRodrigo/skforecast).