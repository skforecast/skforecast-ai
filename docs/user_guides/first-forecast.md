# Your first forecast

Get **skforecast-ai** running end to end: pass in a time series and receive predictions, evaluation metrics, and the standalone Python script that produced them.

By default, the assistant runs in **deterministic mode** — no API key, network access, or configuration required. It inspects your data, picks a sensible model using transparent rules, and runs a real `skforecast` pipeline locally.

Optionally, you can attach an LLM. When you do, it acts like a senior data scientist reviewing your results: it reads every decision the pipeline made and tells you what it would change and why.

!!! note "Before you start"
    Install the package first: `pip install skforecast-ai`. See [Quick start](quick-start.md) for the one-line setup and a smoke test. New to time series forecasting? skforecast's [Introduction to forecasting](https://skforecast.org/latest/introduction-forecasting/introduction-forecasting) covers the machine-learning fundamentals (lags, multi-step prediction) this guide builds on.

---

## Load your data

This example uses a classic monthly water-demand series. Any `pandas.DataFrame` with a value column and a date column works; you can also pass a path to a CSV file directly.

```python
import pandas as pd

url = "https://raw.githubusercontent.com/skforecast/skforecast-datasets/refs/heads/main/data/h2o.csv"
data = pd.read_csv(url, sep=",", header=0, names=["y", "date"])

data.head()
```

The frame has two columns: `y` (the target to forecast) and `date` (the timestamp).

## Create the assistant

```python
from skforecast_ai import ForecastingAssistant

assistant = ForecastingAssistant()
```

With no arguments, the assistant runs the full forecasting pipeline. To add an AI reasoning layer on top, see [Using the AI assistant](using-the-ai-assistant.md).

## Run the forecast

Call `forecast()` with the data, the name of the target column, the date column, and how many steps ahead you want. Here we predict the next 12 months.

```python
results = assistant.forecast(
             data        = data,
             target      = "y",
             date_column = "date",
             steps       = 12,
         )
```

The `forecast()` method is the fastest way to generate predictions. In a single call, it executes the full pipeline (profile → plan → execute) and returns a `ForecastResult` holding the predictions, the evaluation metrics (when available), and the exact standalone **skforecast** script that produced them.

!!! info "Two modes: predict the future vs. evaluate the model"
    `forecast()` has two modes, selected by the `test_size` argument:

    + **Prediction mode** (`test_size = None`, the default): The model is trained on the entire dataset and forecasts the next `steps` time points into the future. Because there is no ground truth to compare against, no metrics are returned. If the historical data contains exogenous variables, their future values must be explicitly supplied via the `exog` argument.

    + **Evaluation mode** (`test_size` is set). The dataset is split into train and test sets, the model is trained on the training portion, and predictions for the test window are compared against the held-out actuals to compute metrics. In this mode, the test-set exogenous values are taken from the split, so `exog` must not be passed.

    For repeated, walk-forward evaluation across many points in time, use [backtesting](backtesting.md) instead of a single split.

## Explore the results

`forecast()` returns a `ForecastResult`, a lightweight container that bundles everything the assistant used and produced, so you can inspect the outputs, audit the decisions, or lift the code straight into production.

| Attribute | Type | Description |
|---|---|---|
| `predictions` | DataFrame | Forecasted values for the requested steps. When intervals (or quantiles) are requested, the bound columns are included alongside the point predictions. |
| `metrics` | DataFrame, None | Evaluation metrics (`MAE`, `MSE`, `MASE`), one row per series. `None` in prediction mode, where there is no ground truth to score against. |
| `code` | str | The exact standalone **skforecast** script that produced the forecast, deterministic and ready to run on its own. |
| `profile` | `ForecastingProfile` | The data profile behind the forecast: metadata, summary statistics, detected frequency and seasonality, and the high-level modeling decisions. |
| `plan` | `ForecastPlan` | The detailed configuration that was executed: forecaster, estimator, lags, window features, preprocessing, and interval settings. |

Displaying the object in a notebook renders a rich summary of all of the above; the raw script is also available through `results.show_code()`.

```python
# Forecasted values for the next 12 steps (the future)
results.predictions.head()
```

```python
# Full results object
results
```

```python
# The standalone Python script that was executed
results.show_code()
```


!!! tip "The script is the source of truth"
    `result.code` is not a reconstruction. It is *exactly* what ran to produce `result.predictions`. Copy it into a `.py` file and run it with no dependency on skforecast-ai. See [How it works & trust](how-it-works-and-trust.md) for details on this guarantee.

## Evaluate the model

To measure how well the model performs before trusting the forecast, pass `test_size`. The assistant then splits your series, trains on the earlier portion, predicts the held-out tail, and reports metrics:

```python
results = assistant.forecast(
             data        = data,
             target      = "y",
             date_column = "date",
             steps       = 12,
             test_size   = 12,   # hold out the last 12 observations as a test set
         )

# Now metrics are available: MAE, MSE, MASE per series
results.metrics
```

`test_size` accepts three forms:

| Value | Meaning |
| --- | --- |
| `int` (e.g. `12`) | The last *N* observations form the test set. |
| `float` in `(0, 1)` (e.g. `0.2`) | The last fraction of observations form the test set. |
| date string / `Timestamp` (e.g. `"2005-01-01"`) | The first timestamp of the test set (the split point). |

Once you are satisfied with the evaluation, drop `test_size` to retrain on all data and forecast the real future.

## Prediction intervals

Pass `interval=[lower, upper]` (quantiles) to receive confidence bounds alongside the point forecast:

```python
result = assistant.forecast(
             data        = data,
             target      = "y",
             date_column = "date",
             steps       = 12,
             interval    = [0.1, 0.9],  # 80% prediction interval
         )

print(result.predictions.head())
```

---

## AI reasoning layer (optional)

If you have the LLM extras installed (`pip install "skforecast-ai[llm]"`), the assistant gains an AI reasoning layer: it reads `result.profile` and `result.plan` and advises you on what it would change and why.

!!! warning "Your data stays private"
    By default, enabling an LLM does **not** send your time-series data to the model provider.
    The assistant passes only summary statistics, detected frequency,
    seasonality flags and the forecaster configuration, never the raw observations.
    To explicitly allow it, pass `send_data_to_llm=True`.
    

Use `ask()` to query it:

```python
LLM_MODEL = "google:gemini-3-flash-preview"
api_key = os.getenv("GOOGLE_API_KEY")

assistant = ForecastingAssistant(
    llm=LLM_MODEL, api_key=api_key, send_data_to_llm=False
)

# Using aws bedrock
# assistant = ForecastingAssistant(
#     llm='bedrock:eu.anthropic.claude-sonnet-4-6',
#     base_url="eu-west-1"
# )

result = assistant.forecast(
             data        = data,
             target      = "y",
             date_column = "date",
             steps       = 12,
         )

answer = assistant.ask(
    "Why was this estimator chosen, and what could improve accuracy?",
    forecast_result=result,
)
answer
```

The LLM does not alter the forecast; the numbers are identical whether or not a model is configured. To act on a suggestion, see [Human-in-the-loop forecasting](human-in-the-loop.md).

---

## Under the hood

The assistant follows a four-step rule-based pipeline — **profile → plan → render code → execute** — and every decision at each step is fully inspectable.

- To understand each step and the objects passed between them, see [The forecasting workflow](the-forecasting-workflow.md).
- To see why a particular forecaster, estimator, or set of lags was chosen, see [Customizing the model](customizing-the-model.md).
- To check what the assistant detected in your data (frequency, gaps, missing values), see [Understanding your data](understanding-your-data.md).

---

## Next steps

- [**Complete worked example**](../examples/agentic-forecasting-with-skforecast-ai.ipynb): End-to-end fast-path walkthrough on a real hourly dataset — exogenous variables, prediction intervals, `refine_plan()`, backtesting, and `ask()` for interpretation.
- [**Customizing the model**](customizing-the-model.md): Override the forecaster, estimator, hyperparameters, or horizon.
- [**Backtesting & validation**](backtesting.md): Evaluate the model with walk-forward cross-validation.
- [**Reproducible code**](reproducible-code.md): Get the standalone script without executing it, for auditing and deployment.
- [**Using the AI assistant**](using-the-ai-assistant.md) *(optional)*: Configure a provider and ask questions about your forecast.
- [**Human-in-the-loop forecasting**](human-in-the-loop.md) *(optional)*: Use `ask()` suggestions to drive `refine_plan()` and iterate toward a better model.
