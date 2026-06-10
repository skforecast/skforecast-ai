# skforecast-ai

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue" alt="Python version">
  <img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License">
  <a href="https://github.com/JoaquinAmatRodrigo/skforecast"><img src="https://img.shields.io/badge/built%20on-skforecast-orange" alt="Built on skforecast"></a>
</p>

AI-powered forecasting assistant built on top of [skforecast](https://github.com/JoaquinAmatRodrigo/skforecast). 

**skforecast-ai** is a deterministic, rule-based forecasting engine with an optional LLM overlay to explain decisions, guaranteeing 100% reproducible results without AI hallucinations.

## Table of Contents
- [About The Project](#about-the-project)
- [Architecture & Logic](#architecture--logic)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Contributing](#contributing)
- [License](#license)

---

## About The Project

**skforecast-ai** automates and explains time series forecasting workflows. It acts as an expert pair-programmer that profiles your data, recommends the optimal forecasting strategy (including models, hyperparameters, and preprocessing), and generates complete, executable `skforecast` Python scripts.

### Core Philosophy
The true differentiator of `skforecast-ai` is its separation of execution and reasoning:
1. **Deterministic Core:** All forecasting logic, recommendations, and code generation are handled by rigid, testable Python rules. Results are 100% reproducible.
2. **LLM Overlay:** An optional LLM agent (`pydantic-ai`) acts as a conversational explainer. It reads the deterministic application state to answer questions, suggest improvements, or explain complex metrics in natural language, without altering the underlying math.

---

## Architecture & Logic

### 1. Component Pipeline

The internal architecture follows a strict, functional pipeline where data flows through distinct transformation stages:

- **`profiling/`**: Inspects the incoming dataset (identifying index types, frequency, NaN presence, and target distributions).
- **`recommendation/`**: The deterministic "brain". It applies business rules to select the best forecaster, estimator, and preprocessing steps based on the profile.
- **`rendering/`**: Assembles the logical Python script line-by-line depending on the chosen plan (`single_series`, `multi_series`, `foundation`, etc.).
- **`execution/`**: Dynamically compiles and executes the rendered scripts using `exec()`, guaranteeing that the code shown to the user is exactly the code that generates the `pandas` predictions.
- **`llm/` & `skills/`**: Orchestrates dynamic prompts. The *Knowledge as Code* pattern is heavily utilized here: heuristic rules are extracted into isolated Markdown files (`SKILL.md`), serving as a single source of truth for both human developers and the LLM's RAG context.

### 2. Public API: `ForecastingAssistant`

The primary entry point for users is the `ForecastingAssistant` class, which offers a clean, step-by-step API:

*   **`profile()`**: Ingests raw data and outputs a `ForecastingProfile`.
*   **`plan()`**: Refines the profile into an actionable `ForecastPlan`.
*   **`forecast_code()` / `backtest_code()`**: Generates the inspectable, production-ready Python scripts.
*   **`forecast()` / `backtest()`**: Internalizes the entire process, directly returning predictions and metrics.
*   **`ask()`**: Converses with the LLM based on the current context of the pipeline.

---

## Installation

```bash
# Clone the repository and install in editable mode with development dependencies
git clone https://github.com/JoaquinAmatRodrigo/skforecast-ai.git
cd skforecast-ai
pip install -e ".[dev]"
```

*Note: For the LLM capabilities to function, you must configure a provider (e.g., via the CLI `skforecast-ai config set` or environment variables).*

## Quick Start

Here is a quick example of how to use the fast-path API to go from data to a fully executed forecast in a few lines of code.

```python
import pandas as pd
from skforecast_ai.assistant import ForecastingAssistant

# 1. Load your data
url = 'https://raw.githubusercontent.com/JoaquinAmatRodrigo/skforecast/master/data/h2o.csv'
data = pd.read_csv(url, sep=',', header=0, names=['y', 'date'])

# 2. Initialize the Assistant (Deterministic Mode)
assistant = ForecastingAssistant()

# 3. Generate the script and execute the forecast in one step
results = assistant.forecast(
    data=data,
    target='y',
    date_column='date'
)

# View the generated Python script
print(results["rendered_code"].core)

# View the predictions DataFrame
print(results["predictions"].head())
```

---

## Contributing

Contributions are welcome! Please check out our [Contributing Guide](CONTRIBUTING.md) for more details.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
