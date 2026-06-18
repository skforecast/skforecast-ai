# Your first forecast

Get **skforecast-ai** running end to end in minutes: pass in a time series and receive predictions, evaluation metrics, and the standalone Python script that produced them.

No API key, no internet connection, and no configuration required. By default, the assistant runs in **deterministic mode**: it inspects your data, picks a sensible model using transparent rules, and runs a real `skforecast` pipeline locally. When you add an LLM, it acts like a senior data scientist reviewing your results: it reads every decision the pipeline made and tells you what it would change and why.

!!! note "Before you start"
    Install the package first: `pip install skforecast-ai`. See [Quick start](quick-start.md) for the one-line setup and a smoke test.

---

## Step 1: Load your data

This example uses a classic monthly water-demand series. Any `pandas.DataFrame` with a value column and a date column works; you can also pass a path to a CSV file directly.

```python
import pandas as pd

url = "https://raw.githubusercontent.com/JoaquinAmatRodrigo/skforecast/master/data/h2o.csv"
data = pd.read_csv(url, sep=",", header=0, names=["y", "date"])

data.head()
```

The frame has two columns: `y` (the target to forecast) and `date` (the timestamp).

## Step 2: Create the assistant

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant()
```

With no arguments, the assistant runs the full forecasting pipeline. To add an AI reasoning layer on top, see [Using the AI assistant](using-the-ai-assistant.md).

## Step 3: Run the forecast

Call `forecast()` with the data, the name of the target column, the date column, and how many steps ahead you want. Here we predict the next 12 months.

```python
result = assistant.forecast(
    data=data,
    target="y",
    steps=12,
    date_column="date",
)
```

This single call profiles the data, selects a forecaster and estimator, generates a `skforecast` script, and executes it.

## Step 4: Read the results

`forecast()` returns a `ForecastResult`. Access everything via attribute access:

```python
# Forecasted values for the next 12 steps
print(result.predictions.head())

# Evaluation metrics: MAE, MSE, MASE per series
print(result.metrics)

# The complete, standalone Python script that was executed
print(result.code)
```

| Attribute | What it holds |
| --- | --- |
| `result.predictions` | Forecasted values for the requested `steps` (a `DataFrame`). |
| `result.metrics` | Evaluation metrics (`MAE`, `MSE`, `MASE`). One row per series. |
| `result.code` | The complete `skforecast` script that was executed. |
| `result.intervals` | Prediction intervals (if requested). `None` otherwise. |
| `result.profile` | What the assistant detected about your data. |
| `result.plan` | The modeling decisions it made. |

!!! tip "The script is the source of truth"
    `result.code` is not a reconstruction. It is *exactly* what ran to produce `result.predictions`. Copy it into a `.py` file and run it with no dependency on skforecast-ai. See [How it works & trust](how-it-works-and-trust.md) for details on this guarantee.

!!! info "Unlock the AI reasoning layer (optional)"
    If you have the LLM extras installed (`pip install "skforecast-ai[llm]"`), the assistant gains an AI reasoning layer: it reads `result.profile` and `result.plan` and advises you like a senior data scientist reviewing your pipeline, explaining what it would change and why.

    Use `ask()` to query it:

    ```python
    assistant = ForecastingAssistant(llm="openai:gpt-4o-mini")
    result = assistant.forecast(data, target="y", steps=12, date_column="date")

    answer = assistant.ask(
        "Why was this estimator chosen, and what could improve accuracy?",
        forecast_result=result,
    )
    print(answer.explanation)
    ```

    The LLM does not alter the forecast; the numbers are identical whether or not a model is configured. To act on a suggestion, see [Human-in-the-loop forecasting](human-in-the-loop.md).

---

## Prediction intervals (optional)

Pass `interval=[lower, upper]` (percentiles) to receive confidence bounds alongside the point forecast:

```python
result = assistant.forecast(
    data=data,
    target="y",
    steps=12,
    date_column="date",
    interval=[10, 90],  # 80% prediction interval
)

print(result.intervals.head())
```

---

## Under the hood

The assistant follows a transparent, rule-based pipeline: **profile your data → plan a model → render code → execute it.** Every decision is inspectable.

- To understand each step and the objects passed between them, see [The forecasting workflow](the-forecasting-workflow.md).
- To see why a particular forecaster, estimator, or set of lags was chosen, see [Customizing the model](customizing-the-model.md).
- To check what the assistant detected in your data (frequency, gaps, missing values), see [Understanding your data](understanding-your-data.md).

---

## Next steps

- [**Customizing the model**](customizing-the-model.md): Override the forecaster, estimator, hyperparameters, or horizon.
- [**Backtesting & validation**](backtesting.md): Evaluate the model with walk-forward cross-validation.
- [**Reproducible code**](reproducible-code.md): Get the standalone script without executing it, for auditing and deployment.
- [**Using the AI assistant**](using-the-ai-assistant.md) *(optional)*: Configure a provider and ask questions about your forecast.
- [**Human-in-the-loop forecasting**](human-in-the-loop.md) *(optional)*: Use `ask()` suggestions to drive `refine_plan()` and iterate toward a better model.
