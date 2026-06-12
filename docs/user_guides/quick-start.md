---
title: Quick start / install
status: draft
---

# Quick start / install

!!! note "Draft"
    This page covers installation and a minimal smoke test. For the guided walkthrough, see [Your first forecast](first-forecast.md).

## Install

Core library (deterministic mode — no API key needed):

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

Requires Python ≥ 3.10.

## Smoke test

If this prints a predictions table and a metrics row, your install works:

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

Continue with **[Your first forecast](first-forecast.md)**.

---

<!-- To expand later:
  - Supported Python versions and optional extras ([llm], [dev], [test]).
  - Verifying the install / version (skforecast_ai.__version__).
  - Pointer to LLM provider setup → using-the-ai-assistant.md.
  Seed: root README install section.
  API to cover: ForecastingAssistant(); forecast(). -->
