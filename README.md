<h1 align="left">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/skforecast/skforecast-ai/blob/main/docs/img/banner-landing-page-dark-mode-skforecast-ai.png?raw=true">
    <img src="https://github.com/skforecast/skforecast-ai/blob/main/docs/img/banner-landing-page-skforecast-ai.png?raw=true" alt="skforecast-ai">
  </picture>
</h1>


| | |
| --- | --- |
| Package | ![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue) [![PyPI](https://img.shields.io/pypi/v/skforecast-ai)](https://pypi.org/project/skforecast-ai/) [![Total downloads](https://static.pepy.tech/personalized-badge/skforecast-ai?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=total%20downloads)](https://pepy.tech/projects/skforecast-ai) [![PyPI monthly downloads](https://img.shields.io/pypi/dm/skforecast-ai?color=blue&label=pypi%20downloads)](https://pypistats.org/packages/skforecast-ai) |
| Meta | [![License](https://img.shields.io/github/license/skforecast/skforecast-ai)](https://github.com/skforecast/skforecast-ai/blob/main/LICENSE) [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21338159.svg)](https://doi.org/10.5281/zenodo.21338159) |
| Testing | [![Build status](https://github.com/skforecast/skforecast-ai/actions/workflows/unit-tests.yml/badge.svg)](https://github.com/skforecast/skforecast-ai/actions/workflows/unit-tests.yml) [![codecov](https://codecov.io/gh/skforecast/skforecast-ai/branch/main/graph/badge.svg)](https://codecov.io/gh/skforecast/skforecast-ai) |
| Community | [![!discord](https://img.shields.io/static/v1?logo=discord&label=discord&message=chat&color=lightgreen)](https://discord.gg/3V52qpNkuj) [![!linkedin](https://img.shields.io/static/v1?logo=linkedin&label=LinkedIn&message=news&color=lightblue)](https://www.linkedin.com/company/skforecast/) [![Forecasting Python](https://img.shields.io/static/v1?logo=readme&logoColor=white&label=Blog&labelColor=%23333333&message=Forecasting%20Python&color=%23ffab40)](https://cienciadedatos.net/en/forecasting-python) |


## About skforecast-ai

**The forecasting assistant that shows its work.** Give skforecast-ai a time series: it profiles the data, chooses the model with deterministic rules, validates it and returns the forecast together with the [skforecast](https://skforecast.org) script that produced it. Every decision comes from a rule you can read, the same data always gives the same result, and the script runs on its own with plain skforecast. An optional LLM explains every decision; it never makes them.

<p align="center">
  <img src="https://github.com/skforecast/skforecast-ai/blob/main/docs/img/skforecast-ai-forecast-ask.png?raw=true" alt="skforecast-ai forecast of hourly bike sharing users with its 80% interval, and the ask() answer that explains the evaluation metrics" width="100%">
</p>

<sub>36-hour LightGBM forecast of hourly bike sharing users, with its 80% prediction interval against the held-out hours, and the answer of `ask()` that explains its metrics. Real skforecast-ai outputs, from the animation on [ai.skforecast.org](https://ai.skforecast.org).</sub>


## Installation

```bash
pip install skforecast-ai
```

The LLM layer is optional. To use it, install the extra (`[bedrock]` for AWS Bedrock):

```bash
pip install "skforecast-ai[llm]"
```

Requires Python 3.10 or newer. More options in the [installation guide](https://ai.skforecast.org/stable/quick-start/how-to-install.html); to install from source, see the [Contribution Guide](https://github.com/skforecast/skforecast-ai/blob/main/CONTRIBUTING.md).


## Quick example

```python
from skforecast_ai import ForecastingAssistant
from skforecast.datasets import load_demo_dataset

# Download demo dataset (monthly)
data = load_demo_dataset(verbose=False)

# Profile the data, plan the model, generate the script and run it,
# evaluated on the last 12 months. No LLM needed.
assistant = ForecastingAssistant()
result = assistant.forecast(data=data, target="y", steps=12, test_size=12)

result.predictions.head()
#                 pred
# 2007-07-01  0.851486
# 2007-08-01  1.048000
# 2007-09-01  0.998147
# 2007-10-01  1.147577
# 2007-11-01  1.110845

result.metrics
#   series       MAE       MSE      MASE      MAPE
# 0      y  0.078442  0.008933  0.802828  0.088608

print(result.code)  # the skforecast script that produced this result
```

That single call chose a `ForecasterRecursive` with a `Ridge` estimator, its lags and window features, and ran the script that `result.code` returns. `result.profile` and `result.plan` hold every decision and the rule behind it. Drop `test_size` to train on all the data and forecast the next 12 months.

<details>
<summary><b>Same pipeline from the terminal</b></summary>

```bash
# End-to-end forecast
skforecast-ai forecast data.csv --target y --date-column date --steps 12

# Only the standalone script, without running it
skforecast-ai forecast-code data.csv --target y --date-column date --steps 12 --output forecast.py
```

The CLI covers the whole pipeline, including `ask()` and the prompts of `refine_plan()` and `create_cv()`. See [Using the CLI](https://ai.skforecast.org/stable/user-guides/cli-usage.html).

</details>

<details>
<summary><b>Ask why (optional LLM)</b></summary>

```python
# pip install "skforecast-ai[llm]"
assistant = ForecastingAssistant(llm="openai:gpt-5.5")

answer = assistant.ask(
    "Is the MASE good, and why was this estimator chosen?",
    context=result,
)
```

`ask()` reads the object you pass and explains it, grounded in the skforecast agent skills. It never changes the result. The dataset is never sent: a result shares only its own predictions and metrics, with a warning. Providers, credentials and local models are covered in [Configuring the LLM](https://ai.skforecast.org/stable/user-guides/llm-configuration.html).

</details>


## Features

### A deterministic engine

- **[Data profiling](https://ai.skforecast.org/stable/user-guides/agentic-forecasting-step-by-step.html)**: frequency, missing values, exogenous and categorical variables, and the significant lags from the partial autocorrelation.
- **A plan with a rule for every decision**: forecaster and estimator, lags, window and calendar features, prediction intervals, metric and cross-validation.
- **The code you see is the code that ran**: `forecast()` and `backtest()` execute the same script that `forecast_code()` and `backtest_code()` return. Inspect it, version it or run it with plain skforecast.
- **[Model selection](https://ai.skforecast.org/stable/user-guides/agentic-forecasting.html)** with `compare()`: every candidate is backtested with the same data and cross-validation, and the ranking is a plain sort of the metric. For a single series, a seasonal naive baseline is ranked alongside them, so you also see whether a model beats the simplest reasonable forecast.
- **Reproducible**: the same input always gives the same profile, plan, script and predictions.
- **Python or terminal**: the [CLI](https://ai.skforecast.org/stable/user-guides/cli-usage.html) runs the same pipeline from a CSV file or URL.

The engine chooses among the forecasters of skforecast: recursive and direct, multi-series and multivariate, statistical (ARIMA) and foundation models.

### An optional LLM layer

- **Explains** a forecast, a backtest, a comparison, a plan or a script in plain language with `ask()`, or answers a general forecasting question.
- **Refines** lags and window features from your domain knowledge with `refine_plan(prompt=...)`.
- **Translates** a deployment scenario into a backtesting strategy with `create_cv(prompt=...)`.
- **Validated before it runs**: every LLM output is checked by a Pydantic model; if it is not valid, you get the deterministic result and a warning.
- **Any provider** through pydantic-ai: OpenAI, Anthropic, Google, Groq, AWS Bedrock, Ollama for local models, or any OpenAI-compatible endpoint.


## Methods

All methods work without an LLM except `ask()`. A prompt is always explicit: nothing is sent to an LLM unless you ask for it.

| Method | What it does | LLM |
|:--|:--|:--:|
| `profile()` | Inspects the data and recommends a forecaster and an estimator | no |
| `plan()` | Builds the plan: lags, window and calendar features, interval, metric | no |
| `refine_plan()` | Changes a plan with explicit overrides, or with a `prompt` | optional |
| `create_cv()` | Builds the cross-validation strategy, or translates a `prompt` into one | optional |
| `forecast()`, `forecast_code()` | Runs the forecast, or returns its script without running it | no |
| `backtest()`, `backtest_code()` | Runs the backtest, or returns its script without running it | no |
| `compare()` | Backtests several configurations and ranks them | no |
| `ask()` | Explains a profile, plan, script or result, or answers a question | required |


## How it works

skforecast-ai has two ways in, on the same engine. The **fast path** goes from data to a forecast or a backtest in one call. The **step-by-step path** returns each intermediate object (profile, plan, cross-validation) so you can inspect it, change it or refine it with the LLM before running anything. Both branch into forecasting and backtesting, `compare()` picks the best configuration from measured performance, and `ask()` explains any object along the way.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/skforecast/skforecast-ai/refs/heads/main/docs/img/how-it-works-dark.svg">
    <img src="https://raw.githubusercontent.com/skforecast/skforecast-ai/refs/heads/main/docs/img/how-it-works.svg" alt="How skforecast-ai works: the fast path runs profiling and planning inside forecast() or backtest(); the step-by-step path calls profile(), plan() and create_cv() so you can inspect each object. compare() ranks several configurations under the same cross-validation, and ask() explains any object at any moment." width="100%">
  </picture>
</p>

Read more in [Agentic forecasting](https://ai.skforecast.org/stable/user-guides/agentic-forecasting.html) and [Agentic forecasting step by step](https://ai.skforecast.org/stable/user-guides/agentic-forecasting-step-by-step.html).


## Documentation

The full documentation is available at **https://ai.skforecast.org**.

| Documentation | |
|:--|:--|
| [Quick start] | Install skforecast-ai, run your first forecast and ask the assistant |
| [Agentic forecasting] | The fast path: profile, forecast, backtest, compare and ask |
| [Step by step] | Every intermediate object, and how to change it |
| [Configuring the LLM] | Providers, credentials, local models and what is sent |
| [Using the CLI] | The same pipeline from the terminal |
| [API Reference] | `ForecastingAssistant`, its results, schemas and the CLI |
| [Releases] | What changed in each version |

[Quick start]: https://ai.skforecast.org/stable/quick-start/how-to-install.html
[Agentic forecasting]: https://ai.skforecast.org/stable/user-guides/agentic-forecasting.html
[Step by step]: https://ai.skforecast.org/stable/user-guides/agentic-forecasting-step-by-step.html
[Configuring the LLM]: https://ai.skforecast.org/stable/user-guides/llm-configuration.html
[Using the CLI]: https://ai.skforecast.org/stable/user-guides/cli-usage.html
[API Reference]: https://ai.skforecast.org/stable/api/assistant.html
[Releases]: https://ai.skforecast.org/stable/releases/releases.html


## Part of the skforecast family

[![Skforecast Docs](https://img.shields.io/badge/Skforecast-Documentation-f79939?logo=readthedocs)](https://skforecast.org/) [![GitHub](https://img.shields.io/badge/GitHub-skforecast-181717?logo=github)](https://github.com/skforecast/skforecast) [![Skforecast Studio](https://img.shields.io/badge/Skforecast%20Studio-Launch%20App-f79939?logo=rocket)](https://studio.skforecast.org/)

- **[skforecast](https://skforecast.org)**: the forecasting library that runs every forecast of skforecast-ai. Machine learning, statistical and foundation models, backtesting and tuning.
- **[Skforecast Studio](https://studio.skforecast.org/)**: a no-code application to build forecasting models visually, which generates production-ready Python code.


## Contributing

Bug reports, feature requests, code, tests and documentation are all welcome. Open an issue on [GitHub Issues](https://github.com/skforecast/skforecast-ai/issues) or read the [Contribution Guide](https://github.com/skforecast/skforecast-ai/blob/main/CONTRIBUTING.md) and the [Code of Conduct](https://github.com/skforecast/skforecast-ai/blob/main/CODE_OF_CONDUCT.md) to get started.

skforecast-ai is created and maintained by [Joaquín Amat Rodrigo](https://github.com/JoaquinAmatRodrigo) and [Javier Escobar Ortiz](https://github.com/JavierEscobarOrtiz), together with everyone who has contributed to it ([about the project](https://ai.skforecast.org/stable/more/about-skforecast-ai.html)).

<a href="https://github.com/skforecast/skforecast-ai/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=skforecast/skforecast-ai" alt="skforecast-ai contributors">
</a>


## Citation

If you use skforecast-ai in a scientific publication, please cite the version you used: each version has its own DOI and ready-made citations on [Zenodo](https://doi.org/10.5281/zenodo.21338159). To cite skforecast-ai in general, use the DOI that always resolves to the latest release.

**APA**:

```
Amat Rodrigo, J., & Escobar Ortiz, J. skforecast-ai [Computer software]. https://doi.org/10.5281/zenodo.21338159
```

**BibTeX**:

```bibtex
@software{skforecast-ai,
  author  = {Amat Rodrigo, Joaquin and Escobar Ortiz, Javier},
  title   = {skforecast-ai},
  license = {Apache-2.0},
  url     = {https://ai.skforecast.org/},
  doi     = {10.5281/zenodo.21338159}
}
```

The citation metadata is also in [CITATION.cff](https://github.com/skforecast/skforecast-ai/blob/main/CITATION.cff) (GitHub's "Cite this repository" button).


## Sponsorship and funding

skforecast-ai is built by the skforecast team. skforecast is free, open-source software supported by the [Sovereign Tech Fund](https://www.sovereign.tech/tech/skforecast) and by the organizations that sponsor it. If your company relies on skforecast or skforecast-ai, see **[Sponsorship and funding](https://skforecast.org/latest/more/funding.html)** for sponsorship tiers, support agreements, feature sponsorship and training.

Individuals can support the project through Open Collective, Buy Me a Coffee, GitHub Sponsors ([Joaquín Amat Rodrigo](https://github.com/sponsors/JoaquinAmatRodrigo), [Javier Escobar Ortiz](https://github.com/sponsors/JavierEscobarOrtiz)) or [PayPal](https://www.paypal.com/donate/?hosted_button_id=D2JZSWRLTZDL6).

<p>
  <a href="https://opencollective.com/skforecast"><img src="https://github.com/skforecast/skforecast-ai/blob/main/docs/img/opencollective_button.png?raw=true" alt="Support skforecast on Open Collective" height="40"></a>&nbsp;
  <a href="https://www.buymeacoffee.com/skforecast"><img src="https://github.com/skforecast/skforecast-ai/blob/main/docs/img/buymeacoffee_button.png?raw=true" alt="Buy Me a Coffee" height="40"></a>&nbsp;
  <a href="https://skforecast.org/latest/more/funding.html"><img src="https://github.com/skforecast/skforecast-ai/blob/main/docs/img/github_sponsor_button.png?raw=true" alt="Sponsor skforecast on GitHub" height="40"></a>
</p>


## License

**skforecast-ai software**: [Apache License 2.0](https://github.com/skforecast/skforecast-ai/blob/main/LICENSE). The underlying skforecast engine is distributed under its own [BSD-3-Clause License](https://github.com/skforecast/skforecast/blob/main/LICENSE).

**skforecast-ai documentation**: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)

**Trademark**: The trademark skforecast is registered with the European Union Intellectual Property Office (EUIPO) under the application number 019109684. Unauthorized use of this trademark, its logo, or any associated visual identity elements is strictly prohibited without the express consent of the owner.
