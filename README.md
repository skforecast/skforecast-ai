<h1 align="left">
    <img src="docs/img/banner-landing-page-skforecast-ai.png"  style="margin-top: 0px;" alt="skforecast banner">
</h1>

![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)
[![PyPI](https://img.shields.io/pypi/v/skforecast-ai)](https://pypi.org/project/skforecast-ai/)
[![Build status](https://github.com/skforecast/skforecast-ai/actions/workflows/unit-tests.yml/badge.svg)](https://github.com/skforecast/skforecast-ai/actions/workflows/unit-tests.yml)
[![Project Status: Active](https://www.repostatus.org/badges/stable/active.svg)](https://www.repostatus.org/#active)
[![Downloads](https://static.pepy.tech/badge/skforecast-ai)](https://pepy.tech/project/skforecast-ai)
[![Downloads](https://img.shields.io/pypi/dm/skforecast-ai?style=flat-square&color=blue&label=downloads%2Fmonth)](https://pypistats.org/packages/skforecast-ai)
[![License](https://img.shields.io/github/license/skforecast/skforecast-ai)](https://github.com/skforecast/skforecast-ai/blob/main/LICENSE)
[![paypal](https://img.shields.io/static/v1?style=social&amp;label=Donate&amp;message=%E2%9D%A4&amp;logo=Paypal&amp;color&amp;link=%3curl%3e)](https://www.paypal.com/donate/?hosted_button_id=D2JZSWRLTZDL6)
[![buymeacoffee](https://img.shields.io/badge/-Buy_me_a%C2%A0coffee-gray?logo=buy-me-a-coffee)](https://www.buymeacoffee.com/skforecast)
![GitHub Sponsors](https://img.shields.io/github/sponsors/joaquinamatrodrigo?logo=github&label=Github%20sponsors&link=https%3A%2F%2Fgithub.com%2Fsponsors%2FJoaquinAmatRodrigo)
[![Open Collective](https://img.shields.io/badge/Open_Collective-2A3F54?logo=opencollective&logoColor=white)](https://opencollective.com/skforecast)
[![!linkedin](https://img.shields.io/static/v1?logo=linkedin&label=LinkedIn&message=news&color=lightblue)](https://www.linkedin.com/company/skforecast/)
[![!discord](https://img.shields.io/static/v1?logo=discord&label=discord&message=chat&color=lightgreen)](https://discord.gg/3V52qpNkuj)
[![Forecasting Python](https://img.shields.io/static/v1?logo=readme&logoColor=white&label=Blog&labelColor=%23333333&message=Forecasting%20Python&color=%23ffab40)](https://cienciadedatos.net/en/forecasting-python)
[![Skforecast Studio](https://img.shields.io/badge/Skforecast%20Studio-Launch%20App-f79939?logo=rocket)](https://studio.skforecast.org/)


**skforecast-ai** is an **AI forecasting assistant** that pairs a deterministic engine, powered by [**skforecast**](https://skforecast.org), with an **LLM reasoning layer**. Simply provide a time series, and the assistant automatically profiles the data, selects a model using established best practices, and evaluates its performance. It returns both the final forecast and the runnable skforecast script that produced it.


## Table of contents

- [Why skforecast-ai?](#-why-skforecast-ai)
- [Installation](#-installation)
- [Quickstart (Python)](#-quickstart-python)
- [Quickstart (CLI)](#-quickstart-cli)
- [How it works](#-how-it-works)
- [Documentation](#-documentation)
- [Contributing](#-contributing)
- [Citation](#-citation)
- [License](#-license)


## ✨ Why skforecast-ai?

- 🎯 **Deterministic by design**: built as a strict rule-based engine to guarantee absolute consistency, same input always means the same output.
- 🔍 **Code you can inspect**: the script you see is the code that ran. Inspect it, version it, or run it standalone with plain **skforecast**.
- ⚡ **From data to forecast in one call**: automatic data profiling, model and estimator selection, lag/feature engineering, and backtest evaluation.
- 💻 **Python or terminal**: drive the full pipeline from a few lines of Python or from the command line.
- 💬 **LLM reasoning layer**: explains the engine's decisions in plain language, helps you improve the configuration, and lets you ask for advice. This layer is entirely optional; the core forecasting pipeline can run fully offline.
- 🏗️ **Built on skforecast**: recursive & direct forecasters, multi-series, statistical, and foundation models (Chronos-2, TimesFM, Moirai, and more).


## 📦 Installation

Requires Python ≥ 3.10.

```bash
pip install skforecast-ai
```

To enable the optional LLM reasoning layer:

```bash
pip install "skforecast-ai[llm]"
```

<details>
<summary>Install from source (for development)</summary>

```bash
git clone https://github.com/skforecast/skforecast-ai.git
cd skforecast-ai
pip install -e ".[dev]"
```
</details>


## 🚀 Quickstart (Python)

From raw data to a validated forecast, and the code behind it, in a few lines:

```python
import pandas as pd
from skforecast_ai import ForecastingAssistant
from skforecast.datasets import load_demo_dataset

data = load_demo_dataset(verbose=False)
assistant = ForecastingAssistant()
result = assistant.forecast(data=data, target="y", steps=12)

print(result.predictions)   # forecast for the next 12 steps
print(result.metrics)       # evaluation metrics: MAE, MSE, MASE
print(result.code)          # the exact skforecast script that produced this result
```

That single `forecast()` call profiled the data, chose a forecaster and estimator, generated a `skforecast` script, and executed it. `result.code` is the script that ran.

The returned `ForecastResult` exposes everything the pipeline produced:

| Attribute | What it holds |
| --- | --- |
| `result.predictions` | Forecast for the requested horizon (includes interval columns when `interval` is requested) |
| `result.metrics` | Backtest evaluation metrics (MAE, MSE, MASE) |
| `result.code` | The runnable `skforecast` script that produced the result |
| `result.profile` | What profiling detected about your data |
| `result.plan` | The forecaster, estimator, lags, and metrics that were chosen |

👉 New here? Walk through it step by step in **[Your first forecast](docs/user-guides/first-forecast.md)**.


## 💻 Quickstart (CLI)

The same pipeline runs from the terminal. Point it at a CSV file or URL:

```bash
# End-to-end forecast (profile → plan → code → forecast)
skforecast-ai forecast data.csv --target y --date-column datetime --steps 12

# Just inspect the data
skforecast-ai profile data.csv --target y --date-column datetime

# Generate a standalone, runnable script without executing it
skforecast-ai forecast-code data.csv --target y --date-column datetime --steps 12 --output forecast.py
```

Run `skforecast-ai --help` or `skforecast-ai <command> --help` for inline documentation on any command.

👉 Full command reference in **[CLI usage](docs/user-guides/cli-usage.md)**.


## 🧠 How it works

Every forecast flows through four inspectable stages:

```mermaid
flowchart LR
    %% Input
    A[("Your data")]:::data -->|Raw Data| B

    %% Core Pipeline Grouping
    subgraph Engine ["Core Processing Engine"]
        direction LR
        B("`**profile()**<br/>*inspect*`"):::stage -->|Metadata| C("`**plan()**<br/>*decide*`"):::stage
        C -->|Strategy| D("`**forecast_code()**<br/>*audit*`"):::stage
    end

    %% Output
    D -->|Generated Script| E[/"`**forecast()**<br/>*run*`"/]:::output

    %% Styling (Based on uploaded skforecast architecture image)
    classDef data    fill:#ffffff,stroke:#333333,stroke-width:2px,color:#333333
    classDef stage   fill:#fff8f0,stroke:#f59e0b,stroke-width:2px,color:#333333
    classDef output  fill:#f8f9fa,stroke:#a1a1aa,stroke-width:2px,color:#333333
    
    %% Subgraph Styling
    style Engine fill:transparent,stroke:#333333,stroke-width:2px,color:#333333
```

1. **Profile** (`profile()`): inspect the data (frequency, gaps, missing values, exogenous columns).
2. **Plan** (`plan()`): choose the forecaster, estimator, lags, and metrics using transparent rules. Use `refine_plan()` to override any decision before generating code.
3. **Generate** (`forecast_code()`): render a standalone `skforecast` script.
4. **Execute** (`forecast()`): run that script and return predictions, metrics, and the code.

Need rigorous walk-forward evaluation? `backtest()` runs the same plan through time-series cross-validation and returns per-fold metrics.

The LLM reasoning layer can read each stage to *explain* decisions and *suggest improvements*:

```python
assistant = ForecastingAssistant(llm="openai:gpt-4o-mini", api_key="YOUR_API_KEY")
answer = assistant.ask("Why was this model chosen?", forecast_result=result)
print(answer.explanation)
```


## 📚 Documentation

Explore the full capabilities of **skforecast-ai** with our comprehensive documentation:

:books: **https://ai.skforecast.org**

| Documentation                           |     |
|:----------------------------------------|:----|
| :rocket: [Quick start]                  | Get started quickly with skforecast |
| :book: [Introduction to agentic forecasting]    | Basics of forecasting concepts and methodologies |
| :books: [API Reference]                 | Comprehensive reference for skforecast functions and classes |
| :memo: [Releases]                       | Keep track of major updates and changes |
| :mag: [More]                            | Discover more about skforecast and its creators |

[Introduction to agentic forecasting]: https://ai.skforecast.org/stable/user-guides/agentic-forecasting.html
[Quick start]: https://ai.skforecast.org/stable/quick-start/quick-start.html
[API Reference]: https://ai.skforecast.org/stable/api/assistant.html
[Releases]: https://ai.skforecast.org/stable/releases/releases.html
[More]: https:///ai.skforecast.or/stable/more/about-skforecast.html

## 🤝 Contributing

Contributions are welcome, whether it's a bug report, a feature idea, or a pull request. Please see the [Contributing Guide](CONTRIBUTING.md) and our [Code of Conduct](CODE_OF_CONDUCT.md) to get started.


## 📖 Citation

If you use `skforecast-ai` in your work, please cite the underlying `skforecast` library:

**Zenodo**

```
Amat Rodrigo, Joaquin, & Escobar Ortiz, Javier. (2026). skforecast (v0.23.0). Zenodo. https://doi.org/10.5281/zenodo.8382787
```

**APA**:
```
Amat Rodrigo, J., & Escobar Ortiz, J. (2026). skforecast (Version 0.23.0) [Computer software]. https://doi.org/10.5281/zenodo.8382787
```

**BibTeX**:
```
@software{skforecast,
  author  = {Amat Rodrigo, Joaquin and Escobar Ortiz, Javier},
  title   = {skforecast},
  url     = {https://skforecast.org/},
  doi     = {10.5281/zenodo.8382787}
}
```

View the [citation file](https://github.com/skforecast/skforecast/blob/master/CITATION.cff).


## 📄 License

Licensed under the Apache License 2.0 (see [LICENSE](LICENSE) for details).

Built with ❤️ on top of [skforecast](https://skforecast.org).