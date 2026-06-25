# Quick start

Install **skforecast-ai** and verify the setup works. For a step-by-step walkthrough of your first real forecast, continue to [Your first forecast](first-forecast.md). New to forecasting with machine learning? skforecast's [Introduction to forecasting](https://skforecast.org/latest/introduction-forecasting/introduction-forecasting) covers the fundamentals this documentation assumes.

## Install

=== "Core"

    Core library — no API key needed, runs entirely offline:

    ```bash
    pip install skforecast-ai
    ```

=== "With LLM assistant"

    Adds the optional LLM reasoning layer for explanations and Q&A:

    ```bash
    pip install "skforecast-ai[llm]"
    ```

=== "From source"

    For development or contributing:

    ```bash
    git clone https://github.com/skforecast/skforecast-ai.git
    cd skforecast-ai
    pip install -e ".[dev]"
    ```

!!! note "Requirements"
    skforecast-ai requires **Python ≥ 3.10**. The deterministic pipeline runs entirely offline; only the optional LLM reasoning layer requires network access and a provider API key.

## Smoke test

Run the snippet below. If it prints a predictions table and a metrics row, the installation is working.

```python
import pandas as pd
from skforecast_ai import ForecastingAssistant
from skforecast.datasets import load_demo_dataset

data = load_demo_dataset(verbose=False)
assistant = ForecastingAssistant(llm=None)
result = assistant.forecast(data=data, target="y", steps=12)

print(result.predictions)   # forecast for the next 12 steps
print(result.metrics)       # evaluation metrics: MAE, MSE, MASE
print(result.code)          # the skforecast script that produced this result
```

!!! tip "Runs locally by default"
    The smoke test runs in deterministic mode: no LLM, no network access, and no configuration required.

## Next steps

- **[Your first forecast](first-forecast.md)**: the same call, explained step by step.
- **[The forecasting workflow](the-forecasting-workflow.md)**: inspect and override each stage of the pipeline.
- **[Using the AI assistant](using-the-ai-assistant.md)** *(optional)*: configure a language model to explain decisions and answer questions about your forecast.
