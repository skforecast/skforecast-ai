# Quick start: install

This page covers installation and a one-minute smoke test to confirm everything works. For the guided walkthrough of your first real forecast, continue to [Your first forecast](first-forecast.md).

## Install

Core library (deterministic mode: no API key needed):

```bash
pip install skforecast-ai
```

With the optional LLM assistant:

```bash
pip install "skforecast-ai[llm]"
```

From source, for development:

```bash
git clone https://github.com/JoaquinAmatRodrigo/skforecast-ai.git
cd skforecast-ai
pip install -e ".[dev]"
```

!!! note "Requirements"
    skforecast-ai requires **Python ≥ 3.10**. The deterministic pipeline runs entirely offline; only the optional LLM overlay needs network access and a provider key.

## Smoke test

If this prints a predictions table and a metrics row, your installation works:

```python
import pandas as pd
from skforecast_ai import ForecastingAssistant

url = "https://raw.githubusercontent.com/JoaquinAmatRodrigo/skforecast/master/data/h2o.csv"
data = pd.read_csv(url, sep=",", header=0, names=["y", "date"])

assistant = ForecastingAssistant()
result = assistant.forecast(data=data, target="y", steps=12, date_column="date")

print(result.predictions.head())
print(result.metrics)
```

## Next steps

- **[Your first forecast](first-forecast.md)**: the same call, explained step by step.
- **[The forecasting workflow](the-forecasting-workflow.md)**: inspect and override each stage of the pipeline.
- **[Using the AI assistant](using-the-ai-assistant.md)** *(optional)*: turn on a language model to ask questions about your forecast.
