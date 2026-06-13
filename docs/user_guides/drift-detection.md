# Monitoring & drift detection

A model is only as good as the assumption that tomorrow looks like the data it was trained on. When that assumption breaks (a regime change, a new product, a sensor recalibration), accuracy degrades silently. **Drift detection** catches that shift so you know *when to retrain*.

skforecast-ai produces standalone `skforecast` code, and `skforecast` ships built-in drift detectors. This guide shows how to add monitoring to a deployed forecast and where the assistant fits in.

!!! note "This is a skforecast capability"
    Drift detection runs on the model you deploy (the exported `skforecast` script), not through a `ForecastingAssistant` method. The assistant's role here is explanatory: it ships a `drift-detection` skill so the [AI assistant](using-the-ai-assistant.md) can walk you through these tools in plain language.

## Two detectors, two jobs

| Detector | Speed | Use case |
| --- | --- | --- |
| `RangeDriftDetector` | Very fast | Real-time scoring, flags values outside the training range before you predict |
| `PopulationDriftDetector` | Moderate | Batch monitoring, statistical tests for distribution shifts over a window |

Both are fitted on **training data** (the reference distribution) and then evaluate new data against it.

## Real-time guardrail: `RangeDriftDetector`

Lightweight enough to run on every inference call. It answers a simple question: are the incoming values within the range the model has actually seen?

```python
from skforecast.recursive import ForecasterRecursive
from skforecast.drift_detection import RangeDriftDetector

# Train the forecaster (e.g. from the script skforecast-ai generated)
forecaster = ForecasterRecursive(estimator=estimator, lags=24)
forecaster.fit(y=y_train, exog=exog_train)

# Fit the detector on the same training data
detector = RangeDriftDetector()
detector.fit(series=y_train, exog=exog_train)

# Before each prediction, check the incoming window
flag_drift, oor_series, oor_exog = detector.predict(
    last_window=new_window, exog=new_exog, verbose=True,
)
if flag_drift:
    print("New data is outside the training range; predictions may be unreliable.")
```

## Batch monitoring: `PopulationDriftDetector`

For scheduled jobs that compare a new batch against the training distribution using statistical tests:

```python
from skforecast.drift_detection import PopulationDriftDetector

detector = PopulationDriftDetector(
    chunk_size=100,                   # or 'W' / 'M' / 'D' for time-based chunks
    threshold=3,                      # 3-sigma; raise to reduce false positives
    threshold_method="std",           # 'std' or 'quantile'
    max_out_of_range_proportion=0.1,
)
detector.fit(X=X_train)               # reference (training) distribution
results, summary = detector.predict(X=X_new)
print(summary)                        # per-feature drift summary
```

## A monitoring loop

Wire the fast detector into the prediction path and act on the signal:

```python
def predict_with_monitoring(new_window, new_exog):
    flag, _, _ = detector.predict(last_window=new_window, exog=new_exog, verbose=False)
    if flag:
        print("Drift detected; schedule a retrain.")
    return forecaster.predict(steps=10, exog=new_exog)
```

When drift fires, the natural response is to re-profile and re-fit with skforecast-ai on fresh data, then redeploy the new script, closing the loop with the [human-in-the-loop workflow](human-in-the-loop.md).

## Practical guidance

- **Fit detectors on training data, never on test/new data.** The reference must be the distribution the model learned.
- **Drift ≠ wrong.** It's a *risk signal*, not proof the model failed. Use it to prioritise retraining, paired with backtested error tracking.
- **Tune sensitivity.** Start at `threshold=3` (3-sigma) and adjust based on your false-positive tolerance.
- **Relationship to intervals.** [Prediction intervals](customizing-the-model.md#adding-prediction-intervals) quantify uncertainty *within* the training distribution; drift detection tells you when that distribution itself has moved.

## Next steps

- **[Human-in-the-loop](human-in-the-loop.md)**: re-profile and refine when drift signals a retrain.
- **[Backtesting & validation](backtesting.md)**: track error over rolling folds alongside drift.
- **[Using the AI assistant](using-the-ai-assistant.md)**: ask the assistant to explain detector choices and thresholds.
