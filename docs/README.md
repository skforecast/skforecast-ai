<div style="margin-bottom: 20px;">
    <img src="img/banner-landing-page-skforecast-ai.png#only-light" align="left" style="margin-bottom: 30px; margin-top: 0px;">
    <img src="img/banner-landing-page-dark-mode-skforecast-ai.png#only-dark" align="left" style="margin-bottom: 30px; margin-top: 0px;">
</div>

<div style="clear: both;"></div>

![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)
[![PyPI](https://img.shields.io/pypi/v/skforecast-ai)](https://pypi.org/project/skforecast-ai/)
[![Build status](https://github.com/skforecast/skforecast-ai/actions/workflows/unit-tests.yml/badge.svg)](https://github.com/skforecast/skforecast-ai/actions/workflows/unit-tests.yml)
[![Project Status: Active](https://www.repostatus.org/badges/latest/active.svg)](https://www.repostatus.org/#active)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/skforecast-ai?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/skforecast-ai)
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
print(result.metrics)       # evaluation metrics: MAE, MSE, MASE...
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

👉 New here? Walk through it step by step in **[Your first forecast](./quick-start/first-forecast.md)**.



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

👉 Full command reference in **[CLI usage](./user-guides/cli-usage.md)**.


## 🧠 How it works

**skforecast-ai** supports two distinct workflows using the same underlying forecasting engine:

+ **The Fast Path:** Use this when you want a forecast or backtest result in a single call. The assistant profiles the data, builds the modeling plan, executes the workflow, and returns the results alongside the reproducible `skforecast` code.

+ **The Step-by-Step Path:** Use this when you want granular control to inspect or adjust intermediate decisions. You can manually create a profile, build a plan, optionally refine it with the LLM, define a validation strategy, evaluate the model, and then generate the forecast.

A useful mental model is that forecasting and validation are separate branches. Once you have a `profile` and a `plan`, you can use `forecast()` to produce future predictions directly, or `backtest()` to evaluate the model's performance on historical data.

The `ask()` method is available in both workflows. It can explain a profile, plan, validation setup, backtest result, or answer general forecasting questions, but it will never execute the workflow or modify your parameters without explicit instruction.

<div style="box-sizing:border-box; margin:16px 0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; color:#24292f; max-width:100%;">
  <div style="box-sizing:border-box; display:flex; gap:20px; flex-wrap:wrap; align-items:stretch;">

<!-- Fast path -->
<div style="box-sizing:border-box; flex:1 1 260px; min-width:0; border:1px solid #d0d7de; border-radius:12px; overflow:hidden; display:flex; flex-direction:column;">
    <div style="box-sizing:border-box; background:#0969da; color:#ffffff; padding:12px 16px; font-size:15px; font-weight:700;">Fast path: one call</div>
    <div style="box-sizing:border-box; padding:16px; background:#f6f8fa; flex:1;">
    <p style="margin:0 0 12px 0; font-size:13px;">Profiling, planning and execution happen internally.</p>
    <div style="box-sizing:border-box; background:#ffffff; border:1px solid #d0d7de; border-radius:8px; padding:10px 12px; text-align:center; font-weight:600;">data</div>
    <div style="text-align:center; color:#57606a; font-size:18px; line-height:1.4;">&#8595;</div>
    <div style="box-sizing:border-box; display:flex; gap:12px; flex-wrap:wrap;">
        <div style="box-sizing:border-box; flex:1 1 150px; min-width:0; background:#ffffff; border:1px solid #d0d7de; border-radius:8px; padding:10px;">
        <div style="font-size:11px; color:#57606a; text-transform:uppercase; letter-spacing:.5px; text-align:center; margin-bottom:6px;">Forecast</div>
        <div style="box-sizing:border-box; background:#dbeafe; border:1px solid #0969da; border-radius:8px; padding:8px; text-align:center; font-weight:700;">forecast()<br><span style="font-weight:400; font-size:12px; color:#57606a;">or forecast_code()</span></div>
        <div style="text-align:center; color:#57606a; font-size:15px; line-height:1.4;">&#8595;</div>
        <div style="text-align:center; font-size:12px; color:#24292f;">predictions + code</div>
        </div>
        <div style="box-sizing:border-box; flex:1 1 150px; min-width:0; background:#ffffff; border:1px solid #d0d7de; border-radius:8px; padding:10px;">
        <div style="font-size:11px; color:#57606a; text-transform:uppercase; letter-spacing:.5px; text-align:center; margin-bottom:6px;">Backtesting (validation)</div>
        <div style="box-sizing:border-box; background:#dbeafe; border:1px solid #0969da; border-radius:8px; padding:8px; text-align:center; font-weight:700;">create_cv()<br><span style="font-weight:400; font-size:12px; color:#57606a;">Deterministic, Agentic mode</span><br><span style="font-weight:400; font-size:12px; color:#57606a;">or pass a skforecast TimeSeriesFold object</span></div>
        <div style="text-align:center; color:#57606a; font-size:15px; line-height:1.4;">&#8595;</div>
        <div style="box-sizing:border-box; background:#dbeafe; border:1px solid #0969da; border-radius:8px; padding:8px; text-align:center; font-weight:700;">backtest()<br><span style="font-weight:400; font-size:12px; color:#57606a;">or backtest_code()</span></div>
        <div style="text-align:center; color:#57606a; font-size:15px; line-height:1.4;">&#8595;</div>
        <div style="text-align:center; font-size:12px; color:#24292f;">metrics + predictions + code</div>
        </div>
    </div>
    </div>
</div>

<!-- Step-by-step path -->
<div style="box-sizing:border-box; flex:1.6 1 340px; min-width:0; border:1px solid #d0d7de; border-radius:12px; overflow:hidden; display:flex; flex-direction:column;">
    <div style="box-sizing:border-box; background:#1a7f37; color:#ffffff; padding:12px 16px; font-size:15px; font-weight:700;">Step-by-step path: full control</div>
    <div style="box-sizing:border-box; padding:16px; background:#f6f8fa; flex:1;">
    <p style="margin:0 0 12px 0; font-size:13px;">Build a <code>profile</code> and a <code>plan</code> from your data, then branch into forecasting and backtesting.</p>
    <div style="box-sizing:border-box; background:#ffffff; border:1px solid #d0d7de; border-radius:8px; padding:8px 12px; text-align:center; font-weight:600;">data</div>
    <div style="text-align:center; color:#57606a; font-size:16px; line-height:1.4;">&#8595;</div>
    <div style="box-sizing:border-box; background:#dcfce7; border:1px solid #1a7f37; border-radius:8px; padding:8px 12px; text-align:center; font-weight:700;">profile()</div>
    <div style="text-align:center; color:#57606a; font-size:16px; line-height:1.4;">&#8595;</div>
    <div style="box-sizing:border-box; background:#dcfce7; border:1px solid #1a7f37; border-radius:8px; padding:8px 12px; text-align:center; font-weight:700;">plan()<br><span style="font-weight:400; font-size:12px; color:#57606a;">refine_plan(), optional (Deterministic or Agentic mode)</span></div>
    <div style="text-align:center; color:#57606a; font-size:16px; line-height:1.4;">&#8595;</div>
    <div style="box-sizing:border-box; display:flex; gap:12px; flex-wrap:wrap;">
        <div style="box-sizing:border-box; flex:1 1 150px; min-width:0; background:#ffffff; border:1px solid #d0d7de; border-radius:8px; padding:10px;">
        <div style="font-size:11px; color:#57606a; text-transform:uppercase; letter-spacing:.5px; text-align:center; margin-bottom:6px;">Forecast</div>
        <div style="box-sizing:border-box; background:#dcfce7; border:1px solid #1a7f37; border-radius:8px; padding:8px; text-align:center; font-weight:700;">forecast()<br><span style="font-weight:400; font-size:12px; color:#57606a;">or forecast_code()</span></div>
        <div style="text-align:center; color:#57606a; font-size:15px; line-height:1.4;">&#8595;</div>
        <div style="text-align:center; font-size:12px; color:#24292f;">predictions + code</div>
        </div>
        <div style="box-sizing:border-box; flex:1 1 150px; min-width:0; background:#ffffff; border:1px solid #d0d7de; border-radius:8px; padding:10px;">
        <div style="font-size:11px; color:#57606a; text-transform:uppercase; letter-spacing:.5px; text-align:center; margin-bottom:6px;">Backtesting (validation)</div>
        <div style="box-sizing:border-box; background:#dcfce7; border:1px solid #1a7f37; border-radius:8px; padding:8px; text-align:center; font-weight:700;">create_cv()<br><span style="font-weight:400; font-size:12px; color:#57606a;">Deterministic, Agentic mode</span><br><span style="font-weight:400; font-size:12px; color:#57606a;">or pass a skforecast TimeSeriesFold object</span></div>
        <div style="text-align:center; color:#57606a; font-size:15px; line-height:1.4;">&#8595;</div>
        <div style="box-sizing:border-box; background:#dcfce7; border:1px solid #1a7f37; border-radius:8px; padding:8px; text-align:center; font-weight:700;">backtest()<br><span style="font-weight:400; font-size:12px; color:#57606a;">or backtest_code()</span></div>
        <div style="text-align:center; color:#57606a; font-size:15px; line-height:1.4;">&#8595;</div>
        <div style="text-align:center; font-size:12px; color:#24292f;">metrics + predictions + code</div>
        </div>
    </div>
    </div>
</div>

  </div>

  <!-- ask() banner -->
  <div style="box-sizing:border-box; margin-top:16px; border:1px solid #8250df; border-radius:12px; overflow:hidden;">
    <div style="box-sizing:border-box; background:#8250df; color:#ffffff; padding:10px 16px; font-size:15px; font-weight:700;">LLM reasoning: available at any moment, in any workflow</div>
    <div style="box-sizing:border-box; padding:12px 16px; background:#faf5ff; font-size:13px;">Call <code>ask()</code> before, during or after either path. It can take a <code>profile</code>, a <code>plan</code>, a <code>forecast_result</code>, a <code>backtest_result</code>, or nothing at all (pure Q&amp;A).</div>
  </div>
</div>

Read more in **[Agentic Forecasting](./user-guides/agentic-forecasting.ipynb)**.


## 🤝 Contributing

Contributions are welcome, whether it's a bug report, a feature idea, or a pull request. Please see the [Contributing Guide](https://github.com/skforecast/skforecast-ai/blob/main/CONTRIBUTING.md) and our [Code of Conduct](https://github.com/skforecast/skforecast-ai/blob/main/CODE_OF_CONDUCT.md) to get started.


## 📖 Citation

If you use `skforecast-ai` in your work, please cite the underlying `skforecast` library:

**Zenodo**

```
Amat Rodrigo, Joaquin, & Escobar Ortiz, Javier. (2026). skforecast-ai (Version 0.1.0). Zenodo. https://doi.org/10.5281/zenodo.21338159
```

**APA**

```
Amat Rodrigo, J., & Escobar Ortiz, J. (2026). skforecast-ai (Version 0.1.0) [Computer software]. https://doi.org/10.5281/zenodo.21338159
```

**BibTeX**

```
@software{skforecast-ai,
  author  = {Amat Rodrigo, Joaquin and Escobar Ortiz, Javier},
  title   = {skforecast-ai},
  version = {0.1.0},
  month   = {7},
  year    = {2026},
  license = {Apache-2.0},
  url     = {https://ai.skforecast.org/},
  doi     = {10.5281/zenodo.21338159}
}
```

View the [citation file](https://github.com/skforecast/skforecast-ai/blob/main/CITATION.cff).


## 📄 License

Licensed under the Apache License 2.0 (see [LICENSE](https://github.com/skforecast/skforecast-ai/blob/main/LICENSE) for details).

Built with ❤️ on top of [skforecast](https://skforecast.org).