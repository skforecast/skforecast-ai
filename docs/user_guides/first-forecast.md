# Your first forecast

This is the fastest way to see **skforecast-ai** work end to end: you hand it a time series, and it hands back predictions, evaluation metrics, and the exact Python script that produced them — in about five lines of code.

No API key, no internet connection, and no configuration are required. By default the assistant runs in **deterministic mode**: it inspects your data, picks a sensible model with transparent rules, and runs a real `skforecast` pipeline locally.

!!! note "Before you start"
    Make sure the package is installed (`pip install skforecast-ai`). See [Quick start / install](quick-start.md) for the one-line setup and a minimal smoke test.

## Step 1 — Load some data

We'll use a classic monthly time series (water demand). Any `pandas.DataFrame` with a value column and a date column works; you can also pass a path to a CSV file directly.

```python
import pandas as pd

url = "https://raw.githubusercontent.com/JoaquinAmatRodrigo/skforecast/master/data/h2o.csv"
data = pd.read_csv(url, sep=",", header=0, names=["y", "date"])

data.head()
```

The frame has two columns: `y` (the value we want to forecast) and `date` (the timestamp).

## Step 2 — Create the assistant

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant()
```

With no arguments, the assistant is in deterministic mode — everything in this guide runs without an LLM.

## Step 3 — Forecast

Call `forecast()` with your data, the name of the target column, the date column, and how many steps ahead you want (`steps`). Here we predict the next 12 months.

```python
result = assistant.forecast(
    data=data,
    target="y",
    steps=12,
    date_column="date",
)
```

That single call profiles the data, chooses a forecaster and estimator, generates a `skforecast` script, and executes it.

## Step 4 — Read the results

`forecast()` returns a `ForecastResult`. You read everything off it with attribute (dot) access:

```python
# The forecasted values for the next 12 steps
print(result.predictions.head())

# Evaluation metrics — a DataFrame with columns: series, MAE, MSE, MASE
print(result.metrics)

# The exact, standalone Python script that produced the result
print(result.code)
```

| Attribute | What it holds |
| --- | --- |
| `result.predictions` | Forecasted values for the requested `steps` (a DataFrame). |
| `result.metrics` | Evaluation metrics with columns `series, MAE, MSE, MASE`. One row for a single series; one row per series otherwise. |
| `result.code` | The complete standalone `skforecast` script — the same code that was just executed. |
| `result.intervals` | Prediction intervals, if you requested them (see below). `None` otherwise. |
| `result.profile` | What the assistant learned about your data. |
| `result.plan` | The concrete modeling decisions it made. |

!!! tip "The script is the source of truth"
    `result.code` isn't a reconstruction or an approximation — it is *exactly* what ran to produce `result.predictions`. You can copy it into a `.py` file and run it yourself with no dependency on skforecast-ai. Why that guarantee holds is explained in [How it works & trust](how-it-works-and-trust.md).

## Want uncertainty bounds?

Add `interval=[lower, upper]` (percentiles) to get prediction intervals alongside the point forecast:

```python
result = assistant.forecast(
    data=data,
    target="y",
    steps=12,
    date_column="date",
    interval=[10, 90],   # an 80% prediction interval
)

print(result.intervals.head())
```

## What just happened?

The assistant didn't guess. It ran a transparent, rule-based pipeline: **profile your data → plan a model → render code → execute it.** You can inspect every decision it made along the way.

- To understand the steps and the objects passed between them, read [The forecasting workflow](the-forecasting-workflow.md).
- To see *why* a particular forecaster, estimator, or set of lags was chosen — and how to change them — read [Customizing the model](customizing-the-model.md).
- To check what the assistant detected in your data (frequency, gaps, missing values), read [Understanding your data](understanding-your-data.md).

## Next steps

- **[Customizing the model](customizing-the-model.md)** — override the forecaster, estimator, hyperparameters, or horizon.
- **[Backtesting & validation](backtesting.md)** — evaluate the model rigorously with walk-forward cross-validation.
- **[Reproducible code](reproducible-code.md)** — get the standalone script without executing it, for auditing and deployment.
- **[Using the AI assistant](using-the-ai-assistant.md)** *(optional)* — turn on an LLM to ask questions about your forecast in plain language.
