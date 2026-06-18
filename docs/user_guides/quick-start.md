# Quick start

Install **skforecast-ai** and verify the setup works in under a minute. For a step-by-step walkthrough of your first real forecast, continue to [Your first forecast](first-forecast.md).

## Install

=== "Core"

    Core library — no API key needed, runs entirely offline:

    ```bash
    pip install skforecast-ai
    ```

=== "With LLM assistant"

    Adds the optional language-model overlay for explanations and Q&A:

    ```bash
    pip install "skforecast-ai[llm]"
    ```

=== "From source"

    For development or contributing:

    ```bash
    git clone https://github.com/JoaquinAmatRodrigo/skforecast-ai.git
    cd skforecast-ai
    pip install -e ".[dev]"
    ```

!!! note "Requirements"
    skforecast-ai requires **Python ≥ 3.10**. The deterministic pipeline runs entirely offline; only the optional LLM overlay requires network access and a provider API key.

## Smoke test

Run the snippet below. If it prints a predictions table and a metrics row, the installation is working.

```python
import pandas as pd
from skforecast_ai import ForecastingAssistant
from skforecast.datasets import load_demo_dataset

data = load_demo_dataset(verbose=False).to_frame().reset_index()
assistant = ForecastingAssistant()
result = assistant.forecast(data=data, target="y", steps=12, date_column="datetime")

print(result.predictions)
print(result.metrics)
print(result.code)
```

!!! tip "No API key required"
    The smoke test runs in deterministic mode. No LLM, no internet connection, and no configuration are needed — the entire pipeline runs locally.

## Next steps

- **[Your first forecast](first-forecast.md)**: the same call, explained step by step.
- **[The forecasting workflow](the-forecasting-workflow.md)**: inspect and override each stage of the pipeline.
- **[Using the AI assistant](using-the-ai-assistant.md)** *(optional)*: configure a language model to explain decisions and answer questions about your forecast.
